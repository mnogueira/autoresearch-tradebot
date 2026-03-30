from __future__ import annotations

import json
from dataclasses import asdict
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
    _atr,
    _build_feature_frame,
    _calc_metrics,
    _ema,
    _fetch_rates,
    _monthly_walkforward,
    _round_to_tick,
    _rsi,
)
from .wdo_mt5_new_signal_pivot_20260330 import PivotSpec, _backtest, _fixed_sltp


OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_expansion_20260330")


def _spec_dict(spec: PivotSpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    data.pop("sltp_fn", None)
    data.pop("entry_filter_fn", None)
    return data


def _extend_features(frame: pd.DataFrame, m5: pd.DataFrame) -> pd.DataFrame:
    extended = frame.copy()
    extended["rsi14_m1"] = _rsi(extended["Close"], 14)
    extended["m1_low_10"] = extended["Low"].rolling(10, min_periods=10).min().shift(1)
    extended["m1_high_10"] = extended["High"].rolling(10, min_periods=10).max().shift(1)
    extended["rsi14_low_10"] = extended["rsi14_m1"].rolling(10, min_periods=10).min().shift(1)
    extended["rsi14_high_10"] = extended["rsi14_m1"].rolling(10, min_periods=10).max().shift(1)
    extended["vwap_dist_atr"] = (extended["Close"] - extended["session_vwap"]) / extended["atr14_m5"].replace(0.0, np.nan)

    m5_feat = m5.copy()
    m5_feat["bb_mid_20"] = m5_feat["Close"].rolling(20, min_periods=20).mean()
    m5_std = m5_feat["Close"].rolling(20, min_periods=20).std(ddof=0)
    m5_feat["bb_upper_20"] = m5_feat["bb_mid_20"] + (2.0 * m5_std)
    m5_feat["bb_lower_20"] = m5_feat["bb_mid_20"] - (2.0 * m5_std)
    m5_feat["bb_width_20"] = (m5_feat["bb_upper_20"] - m5_feat["bb_lower_20"]) / m5_feat["bb_mid_20"].replace(0.0, np.nan)
    m5_feat["bb_width_q30"] = m5_feat["bb_width_20"].rolling(60, min_periods=30).quantile(0.30)
    m5_feat["bb_width_q20"] = m5_feat["bb_width_20"].rolling(60, min_periods=30).quantile(0.20)

    for col in ["bb_upper_20", "bb_lower_20", "bb_width_20", "bb_width_q30", "bb_width_q20"]:
        extended[col] = m5_feat[col].reindex(extended.index, method="ffill")
    return extended


def _high_vol(frame: pd.DataFrame) -> pd.Series:
    return frame["daily_atr14_prior"] > frame["daily_atr20_mean_prior"]


def _low_vol(frame: pd.DataFrame) -> pd.Series:
    return frame["daily_atr14_prior"] <= frame["daily_atr20_mean_prior"]


def _signal_12h_donchian_volume(frame: pd.DataFrame) -> pd.Series:
    vol_gate = frame["Volume"] > (1.5 * frame["vol_avg20_m1"])
    long_signal = (
        _high_vol(frame)
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & (frame["entry_hour"] == 12)
    )
    short_signal = (
        _high_vol(frame)
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["donchian_low_20"])
        & (frame["entry_hour"] == 12)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_10h_donchian_volume(frame: pd.DataFrame) -> pd.Series:
    vol_gate = frame["Volume"] > (1.5 * frame["vol_avg20_m1"])
    long_signal = (
        _high_vol(frame)
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["donchian_high_20"])
        & (frame["entry_hour"] == 10)
    )
    short_signal = (
        _high_vol(frame)
        & vol_gate.fillna(False)
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["donchian_low_20"])
        & (frame["entry_hour"] == 10)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_afternoon_vwap_revert(frame: pd.DataFrame) -> pd.Series:
    quiet = _low_vol(frame)
    long_signal = (
        quiet
        & frame["entry_hour"].between(14, 16)
        & (frame["vwap_dist_atr"] <= -1.25)
        & (frame["rsi5_m1"] <= 18)
    )
    short_signal = (
        quiet
        & frame["entry_hour"].between(14, 16)
        & (frame["vwap_dist_atr"] >= 1.25)
        & (frame["rsi5_m1"] >= 82)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_m5_bb_squeeze_breakout(frame: pd.DataFrame) -> pd.Series:
    squeeze = frame["bb_width_20"] <= frame["bb_width_q30"]
    long_signal = (
        squeeze.fillna(False)
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["bb_upper_20"])
        & frame["entry_hour"].isin([10, 12])
    )
    short_signal = (
        squeeze.fillna(False)
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["bb_lower_20"])
        & frame["entry_hour"].isin([10, 12])
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_rsi_divergence_10h(frame: pd.DataFrame) -> pd.Series:
    bullish_div = (
        (frame["Low"] < frame["m1_low_10"])
        & (frame["rsi14_m1"] > frame["rsi14_low_10"])
        & (frame["ema9_m5"] > frame["ema21_m5"])
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["entry_hour"] == 10)
    )
    bearish_div = (
        (frame["High"] > frame["m1_high_10"])
        & (frame["rsi14_m1"] < frame["rsi14_high_10"])
        & (frame["ema9_m5"] < frame["ema21_m5"])
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["entry_hour"] == 10)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[bullish_div] = 1
    signal.loc[bearish_div] = -1
    return signal


def _portfolio_metrics(
    components: list[tuple[str, pd.DataFrame]],
    trade_dates: pd.Index,
    recent_dates: pd.Index,
    weights: list[float],
) -> dict[str, object]:
    combined_daily = pd.Series(0.0, index=pd.Index(pd.to_datetime(trade_dates)))
    recent_daily = pd.Series(0.0, index=pd.Index(pd.to_datetime(recent_dates)))
    component_summaries: list[dict[str, object]] = []
    for (name, trades), weight in zip(components, weights, strict=True):
        if trades.empty:
            daily = pd.Series(0.0, index=combined_daily.index)
            daily_recent = pd.Series(0.0, index=recent_daily.index)
        else:
            grouped = trades.assign(session_date=pd.to_datetime(trades["session_date"])).groupby("session_date")["pnl_brl"].sum()
            daily = grouped.reindex(combined_daily.index, fill_value=0.0) * weight
            daily_recent = grouped.reindex(recent_daily.index, fill_value=0.0) * weight
        combined_daily = combined_daily.add(daily, fill_value=0.0)
        recent_daily = recent_daily.add(daily_recent, fill_value=0.0)
        component_summaries.append({"name": name, "weight": weight, "net_profit_brl": round(float(daily.sum()), 2)})

    pseudo_trades = pd.DataFrame({"session_date": combined_daily.index.strftime("%Y-%m-%d"), "pnl_brl": combined_daily.values})
    pseudo_trades = pseudo_trades.loc[pseudo_trades["pnl_brl"] != 0.0].reset_index(drop=True)
    recent_pseudo = pd.DataFrame({"session_date": recent_daily.index.strftime("%Y-%m-%d"), "pnl_brl": recent_daily.values})
    recent_pseudo = recent_pseudo.loc[recent_pseudo["pnl_brl"] != 0.0].reset_index(drop=True)
    metrics = _calc_metrics(pseudo_trades, trade_dates)
    recent_metrics = _calc_metrics(recent_pseudo, recent_dates)
    return {"metrics": metrics, "recent_jan_mar_2026": recent_metrics, "components": component_summaries}


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

    specs = [
        PivotSpec(
            name="donchian20_high_atr_10_only_tp10_volume",
            description="10h-only high-ATR Donchian with 1.5x volume gate.",
            signal_fn=_signal_10h_donchian_volume,
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="afternoon_vwap_revert_lowvol_tp08",
            description="14h-16h low-vol VWAP mean reversion with 0.8 ATR target.",
            signal_fn=_signal_afternoon_vwap_revert,
            sltp_fn=_fixed_sltp(1.0, 0.8),
            atr_col="atr14_m5",
            entry_start_hour=14,
            last_entry_hour=16,
            last_entry_minute=30,
            max_hold_bars=30,
        ),
        PivotSpec(
            name="m5_bollinger_squeeze_breakout_tp12",
            description="M5 Bollinger squeeze breakout with M15 trend filter.",
            signal_fn=_signal_m5_bb_squeeze_breakout,
            sltp_fn=_fixed_sltp(1.0, 1.2),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
        ),
        PivotSpec(
            name="rsi_divergence_10h_m5trend_tp10",
            description="10h RSI divergence on M1 with M5/M15 trend confirmation.",
            signal_fn=_signal_rsi_divergence_10h,
            sltp_fn=_fixed_sltp(1.0, 1.0),
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=10,
            last_entry_minute=59,
            max_hold_bars=45,
        ),
        PivotSpec(
            name="donchian20_high_atr_12_only_tp10_volume_ref",
            description="Reference 12h winner.",
            signal_fn=_signal_12h_donchian_volume,
            sltp_fn=_fixed_sltp(1.0, 1.0),
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
    trade_map: dict[str, pd.DataFrame] = {}

    for spec in specs:
        trades = _backtest(frame, spec)
        trade_map[spec.name] = trades
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

    sleeve_components = [
        ("10h_rsi", trade_map["rsi_divergence_10h_m5trend_tp10"]),
        ("12h_donchian", trade_map["donchian20_high_atr_12_only_tp10_volume_ref"]),
        ("afternoon_revert", trade_map["afternoon_vwap_revert_lowvol_tp08"]),
    ]
    portfolios = {
        "equal_weight_10h_rsi_12h_afternoon": _portfolio_metrics(
            sleeve_components,
            trade_dates,
            recent_90,
            [1 / 3, 1 / 3, 1 / 3],
        ),
        "weight_80_20_0": _portfolio_metrics(
            sleeve_components,
            trade_dates,
            recent_90,
            [0.2, 0.8, 0.0],
        ),
        "weight_75_25_0": _portfolio_metrics(
            sleeve_components,
            trade_dates,
            recent_90,
            [0.25, 0.75, 0.0],
        ),
        "weight_70_20_10": _portfolio_metrics(
            sleeve_components,
            trade_dates,
            recent_90,
            [0.2, 0.7, 0.1],
        ),
    }

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
        "portfolios": portfolios,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
