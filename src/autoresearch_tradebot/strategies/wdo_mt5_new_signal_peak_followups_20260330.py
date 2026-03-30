from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta

import MetaTrader5 as mt5
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
)
from .wdo_mt5_new_signal_pivot_20260330 import PivotSpec, _backtest, _fixed_sltp, _spread_ticks


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_peak_followups_20260330")


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _signal_donchian_high_atr(frame: pd.DataFrame, allowed_hours: set[int]) -> pd.Series:
    high_vol = frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]
    long_signal = (
        high_vol
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    short_signal = (
        high_vol
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["donchian_low_20"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_m5_crossover(frame: pd.DataFrame, allowed_hours: set[int], high_atr_only: bool) -> pd.Series:
    atr_gate = (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]) if high_atr_only else True
    cross_up = (frame["ema9_m5"] > frame["ema21_m5"]) & (frame["ema9_m5"].shift(1) <= frame["ema21_m5"].shift(1))
    cross_down = (frame["ema9_m5"] < frame["ema21_m5"]) & (frame["ema9_m5"].shift(1) >= frame["ema21_m5"].shift(1))
    long_signal = (
        atr_gate
        & cross_up
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["ema8_m1"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
    short_signal = (
        atr_gate
        & cross_down
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema8_m1"])
        & frame["entry_hour"].isin(sorted(allowed_hours))
    )
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
    frame["spread_ticks"] = _spread_ticks(frame["Spread"]).fillna(99.0)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    recent_90 = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]

    specs = [
        PivotSpec(
            name="donchian20_high_atr_10_12_tp10_spread1",
            description="Current Donchian winner with explicit <=1 tick spread gate.",
            signal_fn=lambda f: _signal_donchian_high_atr(f, {10, 12}),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            entry_filter_fn=lambda row, _: bool(row["spread_ticks"] <= 1.0),
        ),
        PivotSpec(
            name="donchian20_high_atr_10_12_tp08",
            description="Current Donchian winner with tighter 0.8 ATR target.",
            signal_fn=lambda f: _signal_donchian_high_atr(f, {10, 12}),
            sltp_fn=_fixed_sltp(1.0, 0.8),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="m5_crossover_high_atr_10_12_tp10",
            description="M5 EMA crossover with M15 trend and M1 timing on high-ATR days.",
            signal_fn=lambda f: _signal_m5_crossover(f, {10, 12}, True),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="m5_crossover_high_atr_10_12_tp12",
            description="M5 EMA crossover high-ATR variant with 1.2 ATR target.",
            signal_fn=lambda f: _signal_m5_crossover(f, {10, 12}, True),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
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
