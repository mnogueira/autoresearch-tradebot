from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_followup_screening import build_session_vwap_prev_array
from .stalker_v10_1_python import PRICE_TICK_SIZE
from .stalker_v10_1_recent_softness_analysis import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

VWAP_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_vwap_distance_tier2a_20260329")
ATR_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_atr_exclusion_tier2a_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    params: dict[str, Any],
    comparison_tier: str = "exact",
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "comparison_tier": comparison_tier,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path, family: str, method: str) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family=family,
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = str(variant["comparison_tier"])
    row["screening_method"] = method
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def _distance_filter(distance_ticks: np.ndarray, min_distance_ticks: float) -> Callable[[dict[str, Any]], bool]:
    threshold = float(min_distance_ticks)

    def _allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(distance_ticks[idx])
        return np.isfinite(value) and value >= threshold

    return _allow


def _atr_regime_filter(
    prior_day_atr14: pd.Series,
    q33: pd.Series,
    q67: pd.Series,
    allowed_regimes: set[str],
) -> Callable[[dict[str, Any]], bool]:
    allowed = set(allowed_regimes)

    def _allow(context: dict[str, Any]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        atr_value = float(prior_day_atr14.get(session, np.nan))
        low = float(q33.get(session, np.nan))
        high = float(q67.get(session, np.nan))
        if not (np.isfinite(atr_value) and np.isfinite(low) and np.isfinite(high)):
            return False
        if atr_value <= low:
            regime = "low"
        elif atr_value <= high:
            regime = "medium"
        else:
            regime = "high"
        return regime in allowed

    return _allow


def _reference_context() -> tuple[V10Dataset, pd.Index, Callable[[dict[str, Any]], bool] | None, ManagementConfig]:
    dataset = V10Dataset.from_disk(locate_data_file(None))
    session_hours = {10, 11, 12, 14}
    tier2a_filter = _combine_filters(session_filter(session_hours), _make_roc_filter(dataset, 5))
    management = ManagementConfig(min_minutes_between_entries=25)
    return dataset, dataset.trade_dates, tier2a_filter, management


def run_vwap_mode() -> None:
    output_dir = VWAP_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"

    dataset, trade_dates, tier2a_filter, management = _reference_context()
    params = session_winner_params()

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=management,
    )

    timestamp_to_index = pd.Series(np.arange(len(dataset.bars_m1), dtype=int), index=dataset.bars_m1.index)
    previous_close = dataset.bars_m1.groupby("session_date")["Close"].shift(1)
    vwap_prev = pd.Series(build_session_vwap_prev_array(dataset), index=dataset.bars_m1.index)
    distance_ticks_series = ((previous_close - vwap_prev).abs() / float(PRICE_TICK_SIZE)).astype(float)
    distance_ticks = distance_ticks_series.to_numpy(dtype=float)

    reference_signal_times = pd.to_datetime(reference_trades["signal_time"])
    reference_signal_indices = timestamp_to_index.reindex(reference_signal_times).to_numpy(dtype=float)
    valid_signal_indices = np.isfinite(reference_signal_indices)
    executed_signal_distances = distance_ticks[reference_signal_indices[valid_signal_indices].astype(int)]
    executed_signal_distances = executed_signal_distances[np.isfinite(executed_signal_distances)]
    median_distance = float(np.quantile(executed_signal_distances, 0.50))
    upper_quartile_distance = float(np.quantile(executed_signal_distances, 0.75))
    baseline_distance = max(float(np.median(executed_signal_distances)), 1e-6)

    overlay_trades = reference_trades.copy()
    overlay_signal_indices = timestamp_to_index.reindex(pd.to_datetime(overlay_trades["signal_time"])).to_numpy(dtype=float)
    overlay_distances = np.zeros(len(overlay_trades), dtype=float)
    valid_overlay = np.isfinite(overlay_signal_indices)
    overlay_distances[valid_overlay] = distance_ticks[overlay_signal_indices[valid_overlay].astype(int)]
    multipliers = np.clip(overlay_distances / baseline_distance, 0.5, 1.5)
    overlay_trades["distance_ticks"] = overlay_distances
    overlay_trades["size_multiplier"] = multipliers
    overlay_trades["pnl_brl"] = overlay_trades["pnl_brl"].astype(float) * overlay_trades["size_multiplier"]
    overlay_trades["pnl_points"] = overlay_trades["pnl_points"].astype(float) * overlay_trades["size_multiplier"]
    overlay_metrics = calculate_metrics(overlay_trades, trade_dates)

    top_half_trades, top_half_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(tier2a_filter, _distance_filter(distance_ticks, median_distance)),
        management=management,
    )
    top_quartile_trades, top_quartile_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(tier2a_filter, _distance_filter(distance_ticks, upper_quartile_distance)),
        management=management,
    )

    variants = [
        _variant_payload(
            "tier2a_reference",
            "Tier 2A reference: session hours + 25m cooldown + ROC(5) agreement.",
            reference_trades,
            reference_metrics,
            trade_dates,
            {"management": "25m cooldown", "roc_agreement_bars": 5},
        ),
        {
            **_variant_payload(
                "tier2a_vwap_distance_overlay",
                "Research-only sizing overlay: scale size by absolute prior-close distance from session VWAP at the signal timestamp.",
                overlay_trades,
                overlay_metrics,
                trade_dates,
                {"overlay": "clip(abs(prev_close - session_vwap) / median_distance, 0.5, 1.5)"},
                comparison_tier="research",
            ),
            "overlay_stats": {
                "median_distance_ticks": round(baseline_distance, 4),
                "avg_size_multiplier": round(float(np.mean(multipliers)), 4),
                "p25_size_multiplier": round(float(np.quantile(multipliers, 0.25)), 4),
                "p75_size_multiplier": round(float(np.quantile(multipliers, 0.75)), 4),
            },
        },
        _variant_payload(
            "tier2a_vwap_distance_top_half",
            "Require the signal timestamp to be at or above the median absolute distance from session VWAP among executed Tier 2A signals.",
            top_half_trades,
            top_half_metrics,
            trade_dates,
            {"vwap_distance_threshold_ticks": round(median_distance, 4), "threshold_quantile": 0.50},
        ),
        _variant_payload(
            "tier2a_vwap_distance_top_quartile",
            "Require the signal timestamp to be at or above the 75th percentile absolute distance from session VWAP among executed Tier 2A signals.",
            top_quartile_trades,
            top_quartile_metrics,
            trade_dates,
            {"vwap_distance_threshold_ticks": round(upper_quartile_distance, 4), "threshold_quantile": 0.75},
        ),
    ]

    ranked = sorted(
        variants,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["batch_rank"] = rank

    summary = {
        "ranked_variants": ranked,
        "notes": [
            "Tier 2A is the reference line because it is the cleaner post-Monday upgrade path.",
            "VWAP-distance sizing is research-only because it assumes fractional sizing.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        _leaderboard_row(variant, summary_path, "stalker_v10_1_vwap_frontier", "vwap_distance_followup")
        for variant in variants
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


def run_atr_mode() -> None:
    output_dir = ATR_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"

    dataset, trade_dates, tier2a_filter, management = _reference_context()
    params = session_winner_params()

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=management,
    )

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    q33 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.3333)
    q67 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)

    exclude_high_trades, exclude_high_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(tier2a_filter, _atr_regime_filter(prior_day_atr14, q33, q67, {"low", "medium"})),
        management=management,
    )
    low_only_trades, low_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(tier2a_filter, _atr_regime_filter(prior_day_atr14, q33, q67, {"low"})),
        management=management,
    )

    variants = [
        _variant_payload(
            "tier2a_reference",
            "Tier 2A reference: session hours + 25m cooldown + ROC(5) agreement.",
            reference_trades,
            reference_metrics,
            trade_dates,
            {"management": "25m cooldown", "roc_agreement_bars": 5},
        ),
        _variant_payload(
            "tier2a_exclude_high_atr_regime",
            "Run Tier 2A only on low and medium prior-day ATR14 regimes; exclude the top 33% ATR days.",
            exclude_high_trades,
            exclude_high_metrics,
            trade_dates,
            {"atr_regimes": ["low", "medium"], "atr_percentile_window_days": 60},
        ),
        _variant_payload(
            "tier2a_low_atr_only",
            "Run Tier 2A only on the bottom 33% of prior-day ATR14 regimes.",
            low_only_trades,
            low_only_metrics,
            trade_dates,
            {"atr_regimes": ["low"], "atr_percentile_window_days": 60},
        ),
    ]

    ranked = sorted(
        variants,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["batch_rank"] = rank

    summary = {
        "ranked_variants": ranked,
        "notes": [
            "Tier 2A is the reference line because it is the cleaner post-Monday upgrade path.",
            "ATR regime gates use prior-day ATR14 percentile over a trailing 60-session distribution.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        _leaderboard_row(variant, summary_path, "stalker_v10_1_atr_frontier", "atr_exclusion_followup")
        for variant in variants
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("vwap", "atr"), required=True)
    args = parser.parse_args()

    if args.mode == "vwap":
        run_vwap_mode()
    else:
        run_atr_mode()


if __name__ == "__main__":
    main()
