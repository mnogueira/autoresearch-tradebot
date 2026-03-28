from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import V101Params, _ensure_signal_strength_cache, run_backtest
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_confidence_weekday_followups_20260328")


def _weekday_metrics(trades: pd.DataFrame, trade_dates: pd.Index) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    session_dates = pd.to_datetime(trades["session_date"])
    labels = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
    }
    for weekday in range(5):
        mask = session_dates.dt.dayofweek.eq(weekday)
        weekday_trades = trades.loc[mask].copy()
        weekday_dates = pd.Index(sorted(pd.to_datetime(weekday_trades["session_date"]).unique()))
        if len(weekday_dates) == 0:
            metrics = calculate_metrics(pd.DataFrame(), pd.Index([trade_dates[0]]))
        else:
            metrics = calculate_metrics(weekday_trades, weekday_dates)
        rows.append(
            {
                "weekday": int(weekday),
                "label": labels[int(weekday)],
                "metrics": metrics,
            }
        )
    return rows


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_metrics,
        "sortino_weighted_composite": _composite_score(risk_metrics),
    }


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _allowed_weekdays_filter(allowed_weekdays: set[int]) -> Callable[[dict[str, Any]], bool]:
    allowed = {int(value) for value in allowed_weekdays}
    return lambda context: int(context["weekday"]) in allowed


def _strong_signal_filter(
    trend_eff_raw: np.ndarray,
    min_abs_strength: float,
) -> Callable[[dict[str, Any]], bool]:
    threshold = float(min_abs_strength)

    def _filter(context: dict[str, Any]) -> bool:
        dataset_index = int(context["dataset_index"])
        return abs(float(trend_eff_raw[dataset_index])) >= threshold

    return _filter


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})

    trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    trend_eff_raw = strength_cache["trend_efficiency_raw"]
    timestamp_to_index = pd.Series(np.arange(len(dataset.bars_m1), dtype=int), index=dataset.bars_m1.index)

    confidence_trades = trades.copy()
    confidence_trades["signal_time"] = pd.to_datetime(confidence_trades["signal_time"])
    signal_indices = timestamp_to_index.reindex(confidence_trades["signal_time"]).to_numpy(dtype=float)
    signal_strength = np.zeros(len(confidence_trades), dtype=float)
    valid = np.isfinite(signal_indices)
    signal_strength[valid] = np.abs(trend_eff_raw[signal_indices[valid].astype(int)])
    baseline_strength = max(float(params.MinDirectionalTrendEfficiency15m), 1e-6)
    multipliers = np.clip(signal_strength / baseline_strength, 0.5, 1.5)
    confidence_trades["signal_strength_abs"] = signal_strength
    confidence_trades["size_multiplier"] = multipliers
    confidence_trades["pnl_brl"] = confidence_trades["pnl_brl"].astype(float) * confidence_trades["size_multiplier"]
    confidence_trades["pnl_points"] = confidence_trades["pnl_points"].astype(float) * confidence_trades["size_multiplier"]
    confidence_metrics = calculate_metrics(confidence_trades, dataset.trade_dates)
    strong_signal_threshold = float(np.quantile(signal_strength, 0.75))

    strong_signal_trades, strong_signal_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(
            entry_filter,
            _strong_signal_filter(trend_eff_raw=trend_eff_raw, min_abs_strength=strong_signal_threshold),
        ),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    strong_days_trades, strong_days_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(entry_filter, _allowed_weekdays_filter({0, 2, 3})),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    session_ratio_params = V101Params(
        **{
            **asdict(params),
            "SL_ATRMultiplier": 0.60,
            "TP_ATRMultiplier": 0.42,
        }
    )
    session_ratio_trades, session_ratio_metrics = run_backtest(
        dataset=dataset,
        params=session_ratio_params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
        "reference_metrics": reference_metrics,
        "reference_risk_adjusted": _risk_block(trades, dataset.trade_dates),
        "confidence_weighted_overlay": {
            "rule": "Research-only linear sizing overlay: size multiplier = clip(abs(trend_efficiency_raw) / 0.333333, 0.5, 1.5).",
            "metrics": confidence_metrics,
            **_risk_block(confidence_trades, dataset.trade_dates),
            "multiplier_stats": {
                "mean": round(float(confidence_trades["size_multiplier"].mean()), 4),
                "median": round(float(confidence_trades["size_multiplier"].median()), 4),
                "p25": round(float(confidence_trades["size_multiplier"].quantile(0.25)), 4),
                "p75": round(float(confidence_trades["size_multiplier"].quantile(0.75)), 4),
                "min": round(float(confidence_trades["size_multiplier"].min()), 4),
                "max": round(float(confidence_trades["size_multiplier"].max()), 4),
            },
        },
        "strong_signal_gate_top_quartile": {
            "rule": "Only enter when absolute trend-efficiency at the signal timestamp is at or above the 75th percentile of executed-signal strengths.",
            "threshold_abs_trend_efficiency": round(strong_signal_threshold, 6),
            "metrics": strong_signal_metrics,
            **_risk_block(strong_signal_trades, dataset.trade_dates),
        },
        "skip_tuesday_friday_followup": {
            "rule": "Production candidate but skip Tuesday and Friday entries entirely; Monday, Wednesday, Thursday only.",
            "metrics": strong_days_metrics,
            **_risk_block(strong_days_trades, dataset.trade_dates),
        },
        "session_winner_sltp_followup": {
            "rule": "Session-winner exact variant with tighter stop / wider target ratio: SL 0.60 ATR, TP 0.42 ATR.",
            "metrics": session_ratio_metrics,
            **_risk_block(session_ratio_trades, dataset.trade_dates),
        },
        "weekday_breakdown": _weekday_metrics(trades, dataset.trade_dates),
        "notes": [
            "The confidence-weighted overlay is a research approximation, not a live-ready MT5 implementation. It assumes exact path exits are unchanged and only scales realized trade PnL by signal strength.",
            "Weekday metrics are computed on the final exact production candidate: session hours 10/11/12/14, 30-minute cooldown, 120 M1-bar max hold, SL 0.84, TP 0.30.",
            "The strong-signal gate and weekday skip follow-ups are exact entry filters on top of the production candidate.",
            "The SL 0.60 / TP 0.42 test is run on the plain session-winner family, not on the cooldown/max-hold production overlay, because the request was to test that ratio on the session winner itself.",
        ],
    }
    output_path = DEFAULT_OUTPUT_DIR / "summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
