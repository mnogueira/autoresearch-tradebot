from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from ..common.paths import artifact_output_dir
from .wdo_mt5_new_signal_expansion_20260330 import _extend_features
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
from .wdo_mt5_new_signal_pivot_20260330 import PivotSpec, _backtest, _fixed_sltp


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_rsi10_refine_20260330")


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _signal_rsi_divergence(
    frame: pd.DataFrame,
    *,
    high_atr_only: bool,
    first_half_hour_only: bool,
) -> pd.Series:
    atr_gate = (frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]) if high_atr_only else True
    minute_gate = (frame["entry_minute"] <= 30) if first_half_hour_only else True
    bullish_div = (
        atr_gate
        & minute_gate
        & (frame["Low"] < frame["m1_low_10"])
        & (frame["rsi14_m1"] > frame["rsi14_low_10"])
        & (frame["ema9_m5"] > frame["ema21_m5"])
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["entry_hour"] == 10)
    )
    bearish_div = (
        atr_gate
        & minute_gate
        & (frame["High"] > frame["m1_high_10"])
        & (frame["rsi14_m1"] < frame["rsi14_high_10"])
        & (frame["ema9_m5"] < frame["ema21_m5"])
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["entry_hour"] == 10)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[bullish_div] = 1
    signal.loc[bearish_div] = -1
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

    frame = _extend_features(_build_feature_frame(m1, m5, m15), m5)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    recent_90 = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]
    volume_gate = lambda row, _: bool(row["Volume"] > (1.5 * row["vol_avg20_m1"])) if pd.notna(row["vol_avg20_m1"]) else False

    specs = [
        PivotSpec(
            name="rsi_divergence_10h_tp08",
            description="10h RSI divergence with 0.8 ATR target.",
            signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=False, first_half_hour_only=False),
            sltp_fn=_fixed_sltp(1.0, 0.8),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="rsi_divergence_10h_high_atr_tp10",
            description="10h RSI divergence gated to high-ATR days.",
            signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=True, first_half_hour_only=False),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="rsi_divergence_10h_high_atr_tp08",
            description="10h RSI divergence gated to high-ATR days with 0.8 ATR target.",
            signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=True, first_half_hour_only=False),
            sltp_fn=_fixed_sltp(1.0, 0.8),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="rsi_divergence_10h_high_atr_tp10_first30",
            description="10h RSI divergence on high-ATR days, first half-hour only.",
            signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=True, first_half_hour_only=True),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=30,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="rsi_divergence_10h_high_atr_tp10_volume",
            description="10h RSI divergence on high-ATR days with 1.5x volume gate.",
            signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=True, first_half_hour_only=False),
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
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

    ranked_rows = sorted(
        ranked_rows,
        key=lambda row: (
            float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
            -float(row["max_drawdown_pct"]),
            float(row["net_profit_brl"]),
        ),
        reverse=True,
    )
    summary = {**base_summary, "ranked_variants": ranked_rows, "variants": detailed}
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
