from __future__ import annotations

import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import numpy as np
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
)
from .wdo_mt5_new_signal_peak_12h_refine_20260330 import _signal_donchian_high_atr_12h
from .wdo_mt5_new_signal_pivot_20260330 import PivotSpec, _backtest, _fixed_sltp
from .wdo_mt5_new_signal_rsi10_refine_20260330 import _signal_rsi_divergence


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_portfolio_20260330")


def _calc_daily_metrics(daily_pnl: pd.Series, trade_dates: pd.Index) -> dict[str, float | int | str]:
    daily = daily_pnl.reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0).astype(float)
    active = daily[daily != 0.0]
    wins = daily[daily > 0.0]
    losses = daily[daily < 0.0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.abs().sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    equity = 10000.0 + daily.cumsum()
    peaks = equity.cummax()
    dd = ((peaks - equity) / peaks.replace(0.0, np.nan) * 100.0).max()
    return {
        "start_date": pd.Timestamp(trade_dates[0]).date().isoformat(),
        "end_date": pd.Timestamp(trade_dates[-1]).date().isoformat(),
        "trading_days": int(len(trade_dates)),
        "active_days": int((daily != 0.0).sum()),
        "positive_days": int((daily > 0.0).sum()),
        "net_profit_brl": round(float(daily.sum()), 2),
        "profit_factor": round(float(pf), 4) if np.isfinite(pf) else float("inf"),
        "max_drawdown_pct": round(float(dd), 2),
        "avg_active_day_brl": round(float(active.mean()), 2) if not active.empty else 0.0,
    }


def _daily_from_trades(trades: pd.DataFrame, trade_dates: pd.Index) -> pd.Series:
    if trades.empty:
        return pd.Series(0.0, index=pd.Index(pd.to_datetime(trade_dates)))
    return (
        trades.assign(session_date=pd.to_datetime(trades["session_date"]))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
        .astype(float)
    )


def _portfolio_walkforward(daily_pnl: pd.Series, trade_dates: pd.Index) -> dict[str, object]:
    months = pd.Index(sorted(pd.to_datetime(trade_dates).to_period("M").unique()))
    folds: list[dict[str, object]] = []
    for i in range(3, len(months)):
        train_months = months[i - 3 : i]
        test_month = months[i]
        train_dates = pd.Index([d for d in pd.to_datetime(trade_dates) if d.to_period("M") in set(train_months)])
        test_dates = pd.Index([d for d in pd.to_datetime(trade_dates) if d.to_period("M") == test_month])
        if len(test_dates) == 0:
            continue
        train_metrics = _calc_daily_metrics(daily_pnl.reindex(train_dates, fill_value=0.0), train_dates)
        test_metrics = _calc_daily_metrics(daily_pnl.reindex(test_dates, fill_value=0.0), test_dates)
        folds.append(
            {
                "train_months": [str(x) for x in train_months],
                "test_month": str(test_month),
                "train_metrics": train_metrics,
                "test_metrics": test_metrics,
                "pass": bool(test_metrics["net_profit_brl"] > 0 and float(test_metrics["profit_factor"]) > 1.0),
            }
        )
    return {
        "total_folds": len(folds),
        "passed_folds": int(sum(1 for fold in folds if fold["pass"])),
        "folds": folds,
    }


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

    winner_12h = PivotSpec(
        name="donchian20_high_atr_12_only_tp10_volume",
        description="12h high-ATR Donchian with 1.5x M1 volume gate.",
        signal_fn=lambda f: _signal_donchian_high_atr_12h(f, False),
        sltp_fn=_fixed_sltp(1.0, 1.0),
        atr_col="atr14_m5",
        entry_start_hour=12,
        last_entry_hour=12,
        last_entry_minute=59,
        entry_filter_fn=lambda row, _: bool(row["Volume"] > (1.5 * row["vol_avg20_m1"])) if pd.notna(row["vol_avg20_m1"]) else False,
    )
    sleeve_10h = PivotSpec(
        name="rsi_divergence_10h_high_atr_tp08",
        description="10h RSI divergence on high-ATR days with 0.8 ATR target.",
        signal_fn=lambda f: _signal_rsi_divergence(f, high_atr_only=True, first_half_hour_only=False),
        sltp_fn=_fixed_sltp(1.0, 0.8),
        atr_col="atr14_m5",
        entry_start_hour=10,
        last_entry_hour=10,
        last_entry_minute=59,
        max_hold_bars=45,
    )

    trades_12h = _backtest(frame, winner_12h)
    trades_10h = _backtest(frame, sleeve_10h)
    daily_12h = _daily_from_trades(trades_12h, trade_dates)
    daily_10h = _daily_from_trades(trades_10h, trade_dates)

    weights = [
        {"name": "portfolio_80_20", "w12": 0.80, "w10": 0.20},
        {"name": "portfolio_75_25", "w12": 0.75, "w10": 0.25},
        {"name": "portfolio_70_30", "w12": 0.70, "w10": 0.30},
        {"name": "portfolio_60_40", "w12": 0.60, "w10": 0.40},
        {"name": "portfolio_50_50", "w12": 0.50, "w10": 0.50},
    ]

    ranked: list[dict[str, object]] = []
    detailed: list[dict[str, object]] = []
    for weight in weights:
        daily_portfolio = (daily_12h * weight["w12"]) + (daily_10h * weight["w10"])
        metrics = _calc_daily_metrics(daily_portfolio, trade_dates)
        recent_metrics = _calc_daily_metrics(daily_portfolio.reindex(recent_90, fill_value=0.0), recent_90)
        wf = _portfolio_walkforward(daily_portfolio, trade_dates)
        ranked.append(
            {
                "name": weight["name"],
                "weight_12h": weight["w12"],
                "weight_10h": weight["w10"],
                "net_profit_brl": metrics["net_profit_brl"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "recent_jan_mar_net_profit_brl": recent_metrics["net_profit_brl"],
                "wf_passed_folds": wf["passed_folds"],
                "wf_total_folds": wf["total_folds"],
            }
        )
        detailed.append(
            {
                "name": weight["name"],
                "weights": {"donchian12h": weight["w12"], "rsi10h": weight["w10"]},
                "metrics": metrics,
                "recent_jan_mar_2026": recent_metrics,
                "walkforward_3m_train_1m_test_1m_step": wf,
            }
        )

    ranked = sorted(
        ranked,
        key=lambda row: (
            float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
            -float(row["max_drawdown_pct"]),
            float(row["net_profit_brl"]),
        ),
        reverse=True,
    )

    summary = {
        "symbol": SYMBOL,
        "cost_model": {
            "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
            "tick_size": TICK_SIZE,
            "point_value_brl": POINT_VALUE_BRL,
        },
        "reference_standalone_12h": {
            "metrics": _calc_metrics(trades_12h, trade_dates),
            "recent_jan_mar_2026": _calc_metrics(
                trades_12h.loc[trades_12h["session_date"].isin(pd.Index(recent_90).strftime("%Y-%m-%d"))].reset_index(drop=True),
                recent_90,
            ),
        },
        "reference_old_m1_combo": {
            "full_sample_corrected_cost": {"net_profit_brl": 3317.0, "profit_factor": 1.1334, "max_drawdown_pct": 8.07},
            "recent_jan_mar_2026": {"net_profit_brl": 410.0, "profit_factor": 1.5640, "max_drawdown_pct": 1.75},
        },
        "ranked_portfolios": ranked,
        "portfolios": detailed,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
