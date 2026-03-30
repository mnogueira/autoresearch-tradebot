from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .wdo_mt5_new_signal_frontier_20260330 import (
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    SYMBOL,
    TICK_SIZE,
    _build_feature_frame,
    _calc_metrics,
    _fetch_rates,
    _monthly_walkforward,
    _round_to_tick,
)


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_peak_12h_trailing_20260330")


@dataclass(frozen=True)
class TrailingSpec:
    name: str
    description: str
    tp_mult: float
    trigger_mult: float
    lock_mult: float


def _signal_12h_volume(frame: pd.DataFrame) -> pd.Series:
    high_vol = frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]
    vol_gate = frame["Volume"] > (1.5 * frame["vol_avg20_m1"])
    long_signal = (
        high_vol
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & (frame["entry_hour"] == 12)
    )
    short_signal = (
        high_vol
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["donchian_low_20"])
        & (frame["entry_hour"] == 12)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _backtest(frame: pd.DataFrame, spec: TrailingSpec) -> pd.DataFrame:
    signal = _signal_12h_volume(frame).fillna(0).astype(int)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    cutoff = 17 * 60 + 50
    idx = frame.index

    trades: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    position: dict[str, object] | None = None

    for i in range(len(frame)):
        ts = idx[i]
        bar = frame.iloc[i]
        minute_of_day = ts.hour * 60 + ts.minute

        if position is not None:
            if minute_of_day >= cutoff:
                exit_price = _round_to_tick(float(bar["Open"]))
                pnl_points = (exit_price - float(position["entry_price"])) * int(position["direction"])
                trades.append(
                    {
                        "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                        "entry_time": str(position["entry_time"]),
                        "exit_time": str(ts),
                        "direction": "long" if int(position["direction"]) == 1 else "short",
                        "entry_price": float(position["entry_price"]),
                        "exit_price": exit_price,
                        "pnl_points": round(pnl_points, 2),
                        "pnl_brl": round((pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL, 2),
                        "exit_reason": "time_cutoff",
                    }
                )
                position = None
            else:
                direction = int(position["direction"])
                stop_price = float(position["stop_price"])
                target_price = float(position["target_price"])
                entry_price = float(position["entry_price"])
                atr_value = float(position["atr_value"])
                open_price = _round_to_tick(float(bar["Open"]))
                high_price = _round_to_tick(float(bar["High"]))
                low_price = _round_to_tick(float(bar["Low"]))
                exit_price = None
                exit_reason = None

                if direction == 1:
                    if open_price <= stop_price:
                        exit_price, exit_reason = open_price, "stop_gap_open"
                    elif open_price >= target_price:
                        exit_price, exit_reason = open_price, "target_gap_open"
                    elif low_price <= stop_price and high_price >= target_price:
                        exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                    elif low_price <= stop_price:
                        exit_price, exit_reason = stop_price, "stop_loss"
                    elif high_price >= target_price:
                        exit_price, exit_reason = target_price, "take_profit"
                else:
                    if open_price >= stop_price:
                        exit_price, exit_reason = open_price, "stop_gap_open"
                    elif open_price <= target_price:
                        exit_price, exit_reason = open_price, "target_gap_open"
                    elif high_price >= stop_price and low_price <= target_price:
                        exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                    elif high_price >= stop_price:
                        exit_price, exit_reason = stop_price, "stop_loss"
                    elif low_price <= target_price:
                        exit_price, exit_reason = target_price, "take_profit"

                if exit_price is None:
                    if direction == 1 and high_price >= (entry_price + spec.trigger_mult * atr_value):
                        locked_stop = _round_to_tick(entry_price + spec.lock_mult * atr_value)
                        position["stop_price"] = max(stop_price, locked_stop)
                    elif direction == -1 and low_price <= (entry_price - spec.trigger_mult * atr_value):
                        locked_stop = _round_to_tick(entry_price - spec.lock_mult * atr_value)
                        position["stop_price"] = min(stop_price, locked_stop)

                if exit_price is not None:
                    pnl_points = (float(exit_price) - entry_price) * direction
                    trades.append(
                        {
                            "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                            "entry_time": str(position["entry_time"]),
                            "exit_time": str(ts),
                            "direction": "long" if direction == 1 else "short",
                            "entry_price": entry_price,
                            "exit_price": float(exit_price),
                            "pnl_points": round(pnl_points, 2),
                            "pnl_brl": round((pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL, 2),
                            "exit_reason": exit_reason,
                        }
                    )
                    position = None

        if position is None and pending is not None:
            open_price = _round_to_tick(float(bar["Open"]))
            direction = int(pending["direction"])
            position = {
                "session_date": pending["session_date"],
                "entry_time": ts,
                "entry_index": i,
                "direction": direction,
                "entry_price": open_price,
                "stop_price": pending["stop_price"],
                "target_price": pending["target_price"],
                "atr_value": pending["atr_value"],
            }
            pending = None

        if position is None and pending is None and i < len(frame) - 1:
            if ts.hour != 12:
                continue
            direction = int(signal.iloc[i])
            if direction == 0:
                continue
            atr_value = float(bar["atr14_m5"]) if pd.notna(bar["atr14_m5"]) else np.nan
            if not np.isfinite(atr_value) or atr_value <= 0.0:
                continue
            next_open = _round_to_tick(float(frame.iloc[i + 1]["Open"]))
            if direction == 1:
                stop_price = _round_to_tick(next_open - atr_value)
                target_price = _round_to_tick(next_open + (spec.tp_mult * atr_value))
            else:
                stop_price = _round_to_tick(next_open + atr_value)
                target_price = _round_to_tick(next_open - (spec.tp_mult * atr_value))
            pending = {
                "session_date": ts.normalize(),
                "direction": direction,
                "stop_price": stop_price,
                "target_price": target_price,
                "atr_value": atr_value,
            }

    return pd.DataFrame(trades)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        end = datetime.now()
        start = end - timedelta(days=365)
        m1 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M1, start, end)
        m5 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M5, start, end)
        m15 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M15, start, end)
    finally:
        mt5.shutdown()

    frame = _build_feature_frame(m1, m5, m15)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    recent_90 = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]

    specs = [
        TrailingSpec(
            name="trail_to_be_after_half_atr",
            description="Move stop to breakeven after +0.5 ATR excursion, keep 1.0 ATR target.",
            tp_mult=1.0,
            trigger_mult=0.5,
            lock_mult=0.0,
        ),
        TrailingSpec(
            name="trail_to_quarter_after_half_atr",
            description="Lock +0.25 ATR after +0.5 ATR excursion, keep 1.0 ATR target.",
            tp_mult=1.0,
            trigger_mult=0.5,
            lock_mult=0.25,
        ),
        TrailingSpec(
            name="trail_to_half_after_half_atr",
            description="Lock +0.5 ATR after +0.5 ATR excursion, keep 1.0 ATR target.",
            tp_mult=1.0,
            trigger_mult=0.5,
            lock_mult=0.5,
        ),
    ]

    base_summary = {
        "symbol": SYMBOL,
        "cost_model": {
            "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
            "tick_size": TICK_SIZE,
            "point_value_brl": POINT_VALUE_BRL,
        },
    }
    ranked_rows: list[dict[str, object]] = []
    detailed: list[dict[str, object]] = []

    for spec in specs:
        trades = _backtest(frame, spec)
        metrics = _calc_metrics(trades, trade_dates)
        walkforward = _monthly_walkforward(trades, trade_dates)
        recent_trades = trades.loc[trades["session_date"].isin(pd.Index(recent_90).strftime("%Y-%m-%d"))].reset_index(drop=True)
        recent_metrics = _calc_metrics(recent_trades, recent_90)
        ranked_rows.append(
            {
                "name": spec.name,
                "net_profit_brl": metrics["net_profit_brl"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "total_trades": metrics["total_trades"],
                "recent_jan_mar_net_profit_brl": recent_metrics["net_profit_brl"],
                "wf_passed_folds": walkforward["passed_folds"],
                "wf_total_folds": walkforward["total_folds"],
            }
        )
        detailed.append(
            {
                "name": spec.name,
                "description": spec.description,
                "metrics": metrics,
                "walkforward_3m_train_1m_test_1m_step": walkforward,
                "recent_jan_mar_2026": recent_metrics,
            }
        )
        trades.to_csv(OUTPUT_DIR / f"{spec.name}_trades.csv", index=False)
        partial_ranked = sorted(
            ranked_rows,
            key=lambda row: (
                float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
                -float(row["max_drawdown_pct"]),
                float(row["net_profit_brl"]),
            ),
            reverse=True,
        )
        (OUTPUT_DIR / "summary.json").write_text(
            json.dumps(
                {
                    **base_summary,
                    "ranked_variants": partial_ranked,
                    "variants": detailed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
