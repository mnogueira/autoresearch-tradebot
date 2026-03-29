from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_discrete_strength_sizing_followups_20260329")


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


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_discrete_strength_sizing",
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = "research_sizing"
    row["screening_method"] = "discrete_strength_sizing_followup"
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def _signal_strengths(trades: pd.DataFrame, dataset: V10Dataset, params: Any) -> np.ndarray:
    cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    trend_eff_raw = cache["trend_efficiency_raw"]
    timestamp_to_index = pd.Series(np.arange(len(dataset.bars_m1), dtype=int), index=dataset.bars_m1.index)
    signal_indices = timestamp_to_index.reindex(pd.to_datetime(trades["signal_time"])).to_numpy(dtype=float)
    signal_strength = np.zeros(len(trades), dtype=float)
    valid = np.isfinite(signal_indices)
    signal_strength[valid] = np.abs(trend_eff_raw[signal_indices[valid].astype(int)])
    return signal_strength


def _apply_two_tier_overlay(
    trades: pd.DataFrame,
    dataset: V10Dataset,
    params: Any,
    low_weight: float,
    high_weight: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = trades.copy()
    strengths = _signal_strengths(frame, dataset, params)
    threshold = float(np.median(strengths)) if len(strengths) else 0.0
    weights = np.where(strengths >= threshold, float(high_weight), float(low_weight))

    frame["signal_strength_abs"] = strengths
    frame["size_multiplier"] = weights
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * weights
    if "pnl_points" in frame.columns:
        frame["pnl_points"] = frame["pnl_points"].astype(float) * weights

    metrics = calculate_metrics(frame, dataset.trade_dates)
    return frame, {
        "metrics": metrics,
        "threshold": round(threshold, 6),
        "avg_multiplier": round(float(np.mean(weights)), 4),
        "high_weight_share": round(float(np.mean(weights == float(high_weight))), 4),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    params: dict[str, Any],
    overlay_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
        "overlay_stats": overlay_stats,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))
    t2a_mgmt = ManagementConfig(min_minutes_between_entries=28)
    t3_mgmt = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    t2a_trades, t2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=t2a_mgmt,
    )
    t3_trades, t3_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=t3_mgmt,
    )

    variants: list[dict[str, Any]] = []
    for variant_name, trades, metrics, management in (
        ("tier2a_local_geometry_reference", t2a_trades, t2a_metrics, t2a_mgmt),
        ("tier3_local_geometry_reference", t3_trades, t3_metrics, t3_mgmt),
    ):
        reference = {
            "name": variant_name,
            "rule": f"Reference for {variant_name}.",
            "metrics": metrics,
            **_risk_block(trades, trade_dates),
            "params": {"management": asdict(management), "roc_agreement_bars": 5, "ATR_Length": 10, "NumDaysToConsiderPreviousContractMARange": 2},
            "overlay_stats": {},
        }
        variants.append(reference)

        for low_weight, high_weight in ((0.75, 1.25), (0.5, 1.5)):
            overlay_trades, overlay_stats = _apply_two_tier_overlay(trades, dataset, params, low_weight, high_weight)
            variants.append(
                _variant_payload(
                    name=f"{variant_name}_two_tier_{str(low_weight).replace('.', 'p')}_{str(high_weight).replace('.', 'p')}",
                    rule=f"Two-tier sizing overlay on {variant_name}: {low_weight}x below median signal strength, {high_weight}x above median.",
                    trades=overlay_trades,
                    metrics=overlay_stats["metrics"],
                    trade_dates=trade_dates,
                    params={
                        "management": asdict(management),
                        "roc_agreement_bars": 5,
                        "ATR_Length": 10,
                        "NumDaysToConsiderPreviousContractMARange": 2,
                        "sizing_overlay": {"low_weight": low_weight, "high_weight": high_weight, "split": "median_abs_trend_efficiency"},
                    },
                    overlay_stats={key: value for key, value in overlay_stats.items() if key != "metrics"},
                )
            )

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
            "These overlays are research-only because they still assume fractional or variable sizing around a one-contract baseline.",
            "The purpose is to test whether a simpler two-tier strong-vs-normal sizing rule captures the same upside as the continuous confidence overlay.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [_leaderboard_row(variant, summary_path) for variant in variants])


if __name__ == "__main__":
    main()
