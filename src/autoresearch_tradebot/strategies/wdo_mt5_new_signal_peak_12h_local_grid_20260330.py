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
from .wdo_mt5_new_signal_pivot_20260330 import PivotSpec, _backtest, _fixed_sltp


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_peak_12h_local_grid_20260330")


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _signal_donchian_high_atr_12h_volume(frame: pd.DataFrame) -> pd.Series:
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
        PivotSpec(
            name="donchian20_high_atr_12_only_sl10_tp105_volume",
            description="12h-only volume-gated high-ATR Donchian, SL 1.0 / TP 1.05.",
            signal_fn=_signal_donchian_high_atr_12h_volume,
            sltp_fn=_fixed_sltp(1.0, 1.05),
            atr_col="atr14_m5",
            entry_start_hour=12,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_12_only_sl10_tp11_volume",
            description="12h-only volume-gated high-ATR Donchian, SL 1.0 / TP 1.1.",
            signal_fn=_signal_donchian_high_atr_12h_volume,
            sltp_fn=_fixed_sltp(1.0, 1.1),
            atr_col="atr14_m5",
            entry_start_hour=12,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_12_only_sl09_tp105_volume",
            description="12h-only volume-gated high-ATR Donchian, SL 0.9 / TP 1.05.",
            signal_fn=_signal_donchian_high_atr_12h_volume,
            sltp_fn=_fixed_sltp(0.9, 1.05),
            atr_col="atr14_m5",
            entry_start_hour=12,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="donchian20_high_atr_12_only_sl09_tp11_volume",
            description="12h-only volume-gated high-ATR Donchian, SL 0.9 / TP 1.1.",
            signal_fn=_signal_donchian_high_atr_12h_volume,
            sltp_fn=_fixed_sltp(0.9, 1.1),
            atr_col="atr14_m5",
            entry_start_hour=12,
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
