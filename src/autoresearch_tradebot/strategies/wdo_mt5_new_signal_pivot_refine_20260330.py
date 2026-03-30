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
from .wdo_mt5_new_signal_pivot_20260330 import (
    PivotSpec,
    _backtest,
    _fixed_sltp,
)


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_pivot_refine_20260330")


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _signal_donchian_high_atr_hours(frame: pd.DataFrame, allowed_hours: set[int], require_m5: bool) -> pd.Series:
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
    if require_m5:
        long_signal &= frame["ema9_m5"] > frame["ema21_m5"]
        short_signal &= frame["ema9_m5"] < frame["ema21_m5"]
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_ensemble_hours(frame: pd.DataFrame, long_hours: set[int], short_hours: set[int]) -> pd.Series:
    signal = pd.Series(0, index=frame.index, dtype=int)
    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & frame["entry_hour"].isin(sorted(long_hours))
    )
    short_signal = (
        (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"])
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema21_m5"])
        & (frame["High"] > frame["session_vwap"])
        & (frame["Close"] < frame["session_vwap"])
        & frame["entry_hour"].isin(sorted(short_hours))
    )
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

    volume_gate = lambda row, _: bool(row["Volume"] > (1.5 * row["vol_avg20_m1"])) if pd.notna(row["vol_avg20_m1"]) else False

    specs = [
        PivotSpec(
            name="donchian20_high_atr_10_12_tp12",
            description="High-ATR Donchian restricted to 10h and 12h.",
            signal_fn=lambda f: _signal_donchian_high_atr_hours(f, {10, 12}, False),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_10_12_tp10",
            description="High-ATR Donchian 10h/12h with tighter 1.0 ATR target.",
            signal_fn=lambda f: _signal_donchian_high_atr_hours(f, {10, 12}, False),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_10_12_m5_tp12",
            description="High-ATR Donchian 10h/12h with M5 EMA agreement.",
            signal_fn=lambda f: _signal_donchian_high_atr_hours(f, {10, 12}, True),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_10_12_volume_tp12",
            description="High-ATR Donchian 10h/12h with 1.5x volume gate.",
            signal_fn=lambda f: _signal_donchian_high_atr_hours(f, {10, 12}, False),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            entry_filter_fn=volume_gate,
        ),
        PivotSpec(
            name="ensemble_vol_regime_10_11_12",
            description="Ensemble with 13h removed.",
            signal_fn=lambda f: _signal_ensemble_hours(f, {10, 12}, {10, 11, 12}),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="ensemble_vol_regime_10_11_12_dynamic_tp",
            description="13h removed ensemble with wider high-vol target.",
            signal_fn=lambda f: _signal_ensemble_hours(f, {10, 12}, {10, 11, 12}),
            sltp_fn=lambda row, _: (1.0, 1.5 if row["daily_atr14_prior"] > row["daily_atr20_mean_prior"] else 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="ensemble_vol_regime_10_11_12_volume",
            description="13h removed ensemble plus 1.5x volume gate.",
            signal_fn=lambda f: _signal_ensemble_hours(f, {10, 12}, {10, 11, 12}),
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=45,
            entry_filter_fn=volume_gate,
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
