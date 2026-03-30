from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Callable

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


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_pivot_20260330")
SPREAD_POINT_SIZE = 0.001


@dataclass(frozen=True)
class PivotSpec:
    name: str
    description: str
    signal_fn: Callable[[pd.DataFrame], pd.Series]
    sltp_fn: Callable[[pd.Series, int], tuple[float, float]]
    atr_col: str
    entry_start_hour: int
    last_entry_hour: int
    last_entry_minute: int = 30
    force_flat_hour: int = 17
    force_flat_minute: int = 50
    max_hold_bars: int | None = None
    entry_filter_fn: Callable[[pd.Series, int], bool] | None = None


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _fixed_sltp(sl_mult: float, tp_mult: float) -> Callable[[pd.Series, int], tuple[float, float]]:
    def _fn(_: pd.Series, __: int) -> tuple[float, float]:
        return sl_mult, tp_mult

    return _fn


def _vol_regime_sltp(low_tp: float, high_tp: float, sl_mult: float = 1.0) -> Callable[[pd.Series, int], tuple[float, float]]:
    def _fn(row: pd.Series, _: int) -> tuple[float, float]:
        is_high_vol = bool(row["daily_atr14_prior"] > row["daily_atr20_mean_prior"])
        return sl_mult, (high_tp if is_high_vol else low_tp)

    return _fn


def _spread_ticks(series: pd.Series) -> pd.Series:
    return (series * SPREAD_POINT_SIZE) / TICK_SIZE


def _first_range(frame: pd.DataFrame, end_minute: int) -> tuple[pd.Series, pd.Series]:
    session_key = frame.index.normalize()
    in_range = (frame.index.hour == 9) & (frame.index.minute < end_minute)
    grouped = frame.loc[in_range].groupby(session_key[in_range])
    range_high = grouped["High"].max()
    range_low = grouped["Low"].min()
    return frame.index.normalize().map(range_high), frame.index.normalize().map(range_low)


def _signal_low_vol_midday_revert(frame: pd.DataFrame) -> pd.Series:
    low_vol = frame["daily_atr14_prior"] <= frame["daily_atr20_mean_prior"]
    dist = frame["Close"] - frame["session_vwap"]
    atr = frame["atr14_m5"].replace(0.0, np.nan)
    long_signal = (
        low_vol
        & frame["entry_hour"].between(11, 13)
        & (dist < (-2.0 * atr))
        & (frame["rsi5_m1"] < 20)
    )
    short_signal = (
        low_vol
        & frame["entry_hour"].between(11, 13)
        & (dist > (2.0 * atr))
        & (frame["rsi5_m1"] > 80)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_donchian_high_atr(frame: pd.DataFrame, lookback: int) -> pd.Series:
    high_vol = frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]
    long_signal = (
        high_vol
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame[f"donchian_high_{lookback}"])
        & frame["entry_hour"].isin([10, 12, 13])
    )
    short_signal = (
        high_vol
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame[f"donchian_low_{lookback}"])
        & frame["entry_hour"].isin([10, 12, 13])
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_donchian(frame: pd.DataFrame, lookback: int) -> pd.Series:
    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame[f"donchian_high_{lookback}"])
        & frame["entry_hour"].isin([10, 12, 13])
    )
    short_signal = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame[f"donchian_low_{lookback}"])
        & frame["entry_hour"].isin([10, 12, 13])
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_vwap_fail_short(frame: pd.DataFrame, high_atr_only: bool = False) -> pd.Series:
    atr_gate = (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]) if high_atr_only else True
    short_signal = (
        atr_gate
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema21_m5"])
        & (frame["High"] > frame["session_vwap"])
        & (frame["Close"] < frame["session_vwap"])
        & frame["entry_hour"].isin([10, 11, 12])
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[short_signal] = -1
    return signal


def _signal_session_split(frame: pd.DataFrame) -> pd.Series:
    signal = pd.Series(0, index=frame.index, dtype=int)

    opening_long = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & frame["entry_hour"].isin([10])
    )
    opening_short = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["donchian_low_20"])
        & frame["entry_hour"].isin([10])
    )

    midday = _signal_low_vol_midday_revert(frame).where(frame["entry_hour"].between(11, 13), 0)

    late_long = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["ema9_m5"] > frame["ema21_m5"])
        & (frame["Close"] > frame["ema8_m1"])
        & (frame["Close"].shift(1) <= frame["ema8_m1"].shift(1))
        & frame["entry_hour"].isin([14, 15, 16])
    )
    late_short = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["ema9_m5"] < frame["ema21_m5"])
        & (frame["Close"] < frame["ema8_m1"])
        & (frame["Close"].shift(1) >= frame["ema8_m1"].shift(1))
        & frame["entry_hour"].isin([14, 15, 16])
    )

    signal.loc[opening_long] = 1
    signal.loc[opening_short] = -1
    signal.loc[midday[midday != 0].index] = midday[midday != 0]
    signal.loc[late_long] = 1
    signal.loc[late_short] = -1
    return signal


def _session_split_sltp(row: pd.Series, _: int) -> tuple[float, float]:
    if row["entry_hour"] == 10:
        return 1.0, 1.2
    if 11 <= row["entry_hour"] <= 13:
        return 1.0, 0.8
    return 1.0, 1.2


def _signal_ensemble(frame: pd.DataFrame) -> pd.Series:
    signal = pd.Series(0, index=frame.index, dtype=int)

    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & frame["entry_hour"].isin([10, 12, 13])
    )
    short_signal = (
        (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"])
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema21_m5"])
        & (frame["High"] > frame["session_vwap"])
        & (frame["Close"] < frame["session_vwap"])
        & frame["entry_hour"].isin([10, 11, 12])
    )

    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_orb(frame: pd.DataFrame, range_high: pd.Series, range_low: pd.Series, minutes: int) -> pd.Series:
    allow_after_hour = 9
    allow_after_minute = minutes
    after_range = (frame["entry_hour"] > allow_after_hour) | (
        (frame["entry_hour"] == allow_after_hour) & (frame["entry_minute"] >= allow_after_minute)
    )
    long_signal = (
        after_range
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > range_high)
        & frame["entry_hour"].between(10, 14)
    )
    short_signal = (
        after_range
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < range_low)
        & frame["entry_hour"].between(10, 14)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _backtest(frame: pd.DataFrame, spec: PivotSpec) -> pd.DataFrame:
    signal = spec.signal_fn(frame).fillna(0).astype(int)
    cutoff = spec.force_flat_hour * 60 + spec.force_flat_minute
    last_entry_cutoff = spec.last_entry_hour * 60 + spec.last_entry_minute
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
                if exit_price is None and spec.max_hold_bars is not None and i - int(position["entry_index"]) >= spec.max_hold_bars:
                    exit_price, exit_reason = _round_to_tick(float(bar["Close"])), "max_hold"
                if exit_price is not None:
                    pnl_points = (float(exit_price) - float(position["entry_price"])) * direction
                    trades.append(
                        {
                            "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                            "entry_time": str(position["entry_time"]),
                            "exit_time": str(ts),
                            "direction": "long" if direction == 1 else "short",
                            "entry_price": float(position["entry_price"]),
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
            }
            pending = None

        if position is None and pending is None and i < len(frame) - 1:
            if minute_of_day < (spec.entry_start_hour * 60) or minute_of_day > last_entry_cutoff:
                continue
            direction = int(signal.iloc[i])
            if direction == 0:
                continue
            if spec.entry_filter_fn is not None and not spec.entry_filter_fn(bar, direction):
                continue
            atr_value = float(bar[spec.atr_col]) if pd.notna(bar[spec.atr_col]) else np.nan
            if not np.isfinite(atr_value) or atr_value <= 0.0:
                continue
            next_open = _round_to_tick(float(frame.iloc[i + 1]["Open"]))
            sl_mult, tp_mult = spec.sltp_fn(bar, direction)
            if direction == 1:
                stop_price = _round_to_tick(next_open - (sl_mult * atr_value))
                target_price = _round_to_tick(next_open + (tp_mult * atr_value))
            else:
                stop_price = _round_to_tick(next_open + (sl_mult * atr_value))
                target_price = _round_to_tick(next_open - (tp_mult * atr_value))
            pending = {
                "session_date": ts.normalize(),
                "direction": direction,
                "stop_price": stop_price,
                "target_price": target_price,
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
    frame["spread_ticks"] = _spread_ticks(frame["Spread"]).fillna(99.0)
    range15_high, range15_low = _first_range(frame, 15)
    frame["orb15_high"] = range15_high
    frame["orb15_low"] = range15_low

    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    recent_90 = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]

    specs = [
        PivotSpec(
            name="session_split_hybrid",
            description="10h Donchian breakout, 11-13h low-vol mean reversion, 14-16h MTF pullback.",
            signal_fn=_signal_session_split,
            sltp_fn=_session_split_sltp,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=16,
            last_entry_minute=30,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="donchian20_high_atr_tp12",
            description="Donchian-20 only on high daily ATR regime, tighter 1.2 ATR target.",
            signal_fn=lambda f: _signal_donchian_high_atr(f, 20),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
        PivotSpec(
            name="spread_gate_donchian20_tp12",
            description="Donchian-20 with 1-tick spread gate.",
            signal_fn=lambda f: _signal_donchian(f, 20),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
            entry_filter_fn=lambda row, _: bool(row["spread_ticks"] <= 1.0),
        ),
        PivotSpec(
            name="low_vol_midday_mean_revert_tp08",
            description="Low-vol 11-13h VWAP mean reversion with 0.8 ATR target.",
            signal_fn=_signal_low_vol_midday_revert,
            sltp_fn=_fixed_sltp(1.0, 0.8),
            atr_col="atr14_m5",
            entry_start_hour=11,
            last_entry_hour=13,
            last_entry_minute=59,
            max_hold_bars=30,
        ),
        PivotSpec(
            name="ensemble_donchian_long_vwap_short",
            description="Longs from Donchian breakout, shorts from high-ATR VWAP failed breakout.",
            signal_fn=_signal_ensemble,
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=13,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="ensemble_vol_regime_tp",
            description="Same ensemble with higher target on high-vol days.",
            signal_fn=_signal_ensemble,
            sltp_fn=_vol_regime_sltp(low_tp=1.0, high_tp=1.5, sl_mult=1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=13,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="orb15_trend_filtered",
            description="Breakout of first 15-minute range aligned with M15 trend.",
            signal_fn=lambda f: _signal_orb(f, f["orb15_high"], f["orb15_low"], 15),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
            max_hold_bars=60,
        ),
    ]

    base_summary = {
        "symbol": SYMBOL,
        "cost_model": {
            "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
            "tick_size": TICK_SIZE,
            "point_value_brl": POINT_VALUE_BRL,
        },
        "spread_units": {
            "raw_mt5_spread_point_size": SPREAD_POINT_SIZE,
            "tick_size": TICK_SIZE,
            "spread_ticks_formula": "Spread * 0.001 / 0.5",
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
                "params": _spec_dict(spec),
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
