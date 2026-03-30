from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from ..common.paths import artifact_output_dir
from .wdo_mt5_new_signal_frontier_20260330 import (
    ROUND_TRIP_COST_BRL,
    SYMBOL,
    StrategySpec,
    TICK_SIZE,
    POINT_VALUE_BRL,
    _backtest,
    _build_feature_frame,
    _calc_metrics,
    _fetch_rates,
    _monthly_walkforward,
)


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_refine_20260330")


def _spec_dict(spec: StrategySpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    return data


def _signal_donchian(frame: pd.DataFrame, lookback: int, allowed_hours: set[int]) -> pd.Series:
    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame[f"donchian_high_{lookback}"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    short_signal = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame[f"donchian_low_{lookback}"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_vwap_fail_short(frame: pd.DataFrame, allowed_hours: set[int], high_atr_only: bool) -> pd.Series:
    atr_gate = (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]) if high_atr_only else True
    short_signal = (
        atr_gate
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema21_m5"])
        & (frame["High"] > frame["session_vwap"])
        & (frame["Close"] < frame["session_vwap"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[short_signal] = -1
    return signal


def _signal_low_vol_afternoon_strict(frame: pd.DataFrame) -> pd.Series:
    low_vol = frame["daily_atr14_prior"] <= frame["daily_atr20_mean_prior"]
    dist = frame["Close"] - frame["session_vwap"]
    atr = frame["atr14_m5"]
    long_signal = low_vol & frame["entry_hour"].between(14, 16) & (dist < (-2.0 * atr)) & (frame["rsi5_m1"] < 20)
    short_signal = low_vol & frame["entry_hour"].between(14, 16) & (dist > (2.0 * atr)) & (frame["rsi5_m1"] > 80)
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


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
        StrategySpec(
            name="donchian20_tp12",
            description="Donchian-20 with tighter 1.2 ATR target.",
            signal_fn=lambda f: _signal_donchian(f, 20, {10, 12, 13}),
            sl_mult=1.0,
            tp_mult=1.2,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
        StrategySpec(
            name="donchian30_tp12",
            description="Donchian-30 with tighter 1.2 ATR target.",
            signal_fn=lambda f: _signal_donchian(f, 30, {10, 12, 13}),
            sl_mult=1.0,
            tp_mult=1.2,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
        StrategySpec(
            name="vwap_fail_short_tp10",
            description="VWAP failed-breakout short, hours 10/11/12, tighter 1.0 ATR target.",
            signal_fn=lambda f: _signal_vwap_fail_short(f, {10, 11, 12}, False),
            sl_mult=1.0,
            tp_mult=1.0,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        StrategySpec(
            name="vwap_fail_short_10_11_tp12",
            description="VWAP failed-breakout short, only 10/11h, 1.2 ATR target.",
            signal_fn=lambda f: _signal_vwap_fail_short(f, {10, 11}, False),
            sl_mult=1.0,
            tp_mult=1.2,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=11,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        StrategySpec(
            name="vwap_fail_short_high_atr_tp12",
            description="VWAP failed-breakout short only on high-ATR days.",
            signal_fn=lambda f: _signal_vwap_fail_short(f, {10, 11, 12}, True),
            sl_mult=1.0,
            tp_mult=1.2,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        StrategySpec(
            name="low_vol_afternoon_strict_tp08",
            description="Stricter low-vol afternoon mean reversion with 0.8 ATR target.",
            signal_fn=_signal_low_vol_afternoon_strict,
            sl_mult=1.0,
            tp_mult=0.8,
            atr_col="atr14_m5",
            entry_start_hour=14,
            last_entry_hour=16,
            last_entry_minute=30,
            max_hold_bars=30,
        ),
    ]

    ranked_rows: list[dict[str, object]] = []
    detailed: list[dict[str, object]] = []
    base_summary = {
        "symbol": SYMBOL,
        "cost_model": {
            "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
            "tick_size": TICK_SIZE,
            "point_value_brl": POINT_VALUE_BRL,
        },
    }
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
        partial_summary = {
            **base_summary,
            "ranked_variants": partial_ranked,
            "variants": detailed,
        }
        (OUTPUT_DIR / "summary.json").write_text(json.dumps(partial_summary, indent=2), encoding="utf-8")

    ranked_rows = sorted(
        ranked_rows,
        key=lambda row: (
            float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
            -float(row["max_drawdown_pct"]),
            float(row["net_profit_brl"]),
        ),
        reverse=True,
    )
    summary = {
        **base_summary,
        "ranked_variants": ranked_rows,
        "variants": detailed,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
