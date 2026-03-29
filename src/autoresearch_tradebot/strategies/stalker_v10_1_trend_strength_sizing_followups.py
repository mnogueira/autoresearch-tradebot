from __future__ import annotations

import json
from dataclasses import asdict
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
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_trend_strength_sizing_followups_20260329")


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
    comparison_tier: str = "research",
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "comparison_tier": comparison_tier,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_trend_strength_sizing",
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = str(variant["comparison_tier"])
    row["screening_method"] = "trend_strength_sizing_followup"
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def _apply_strength_overlay(
    trades: pd.DataFrame,
    dataset: V10Dataset,
    params: Any,
    baseline_strength: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    trend_eff_raw = cache["trend_efficiency_raw"]
    timestamp_to_index = pd.Series(np.arange(len(dataset.bars_m1), dtype=int), index=dataset.bars_m1.index)

    frame = trades.copy()
    signal_indices = timestamp_to_index.reindex(pd.to_datetime(frame["signal_time"])).to_numpy(dtype=float)
    signal_strength = np.zeros(len(frame), dtype=float)
    valid = np.isfinite(signal_indices)
    signal_strength[valid] = np.abs(trend_eff_raw[signal_indices[valid].astype(int)])
    multipliers = np.clip(signal_strength / float(baseline_strength), 0.5, 1.5)

    frame["signal_strength_abs"] = signal_strength
    frame["size_multiplier"] = multipliers
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["size_multiplier"]
    frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["size_multiplier"]
    metrics = calculate_metrics(frame, dataset.trade_dates)
    stats = {
        "avg_size_multiplier": round(float(np.mean(multipliers)), 4),
        "p25_size_multiplier": round(float(np.quantile(multipliers, 0.25)), 4),
        "p75_size_multiplier": round(float(np.quantile(multipliers, 0.75)), 4),
        "median_signal_strength": round(float(np.median(signal_strength)), 6),
    }
    return frame, {"metrics": metrics, "stats": stats}


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    base_strength = max(float(params.MinDirectionalTrendEfficiency15m), 1e-6)

    session_hours = {10, 11, 12, 14}
    tier2a_filter = _combine_filters(session_filter(session_hours), _make_roc_filter(dataset, 5))
    tier3_filter = tier2a_filter
    tier2a_mgmt = ManagementConfig(min_minutes_between_entries=25)
    tier3_mgmt = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    t2a_trades, t2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=tier2a_mgmt,
    )
    t3_trades, t3_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=tier3_filter,
        management=tier3_mgmt,
    )

    t2a_overlay_trades, t2a_overlay_block = _apply_strength_overlay(t2a_trades, dataset, params, base_strength)
    t3_overlay_trades, t3_overlay_block = _apply_strength_overlay(t3_trades, dataset, params, base_strength)

    variants = [
        _variant_payload(
            "tier2a_reference",
            "Tier 2A reference: 25m cooldown + ROC(5) agreement.",
            t2a_trades,
            t2a_metrics,
            trade_dates,
            {"management": asdict(tier2a_mgmt), "roc_agreement_bars": 5},
            comparison_tier="exact",
        ),
        {
            **_variant_payload(
                "tier2a_trend_strength_overlay",
                "Research-only sizing overlay: size multiplier = clip(abs(trend_efficiency_raw) / threshold, 0.5, 1.5) on Tier 2A.",
                t2a_overlay_trades,
                t2a_overlay_block["metrics"],
                trade_dates,
                {"management": asdict(tier2a_mgmt), "roc_agreement_bars": 5, "sizing_overlay": "trend_strength"},
                comparison_tier="research",
            ),
            "overlay_stats": t2a_overlay_block["stats"],
        },
        _variant_payload(
            "tier3_reference",
            "Tier 3 reference: 25m cooldown + 150m max-hold.",
            t3_trades,
            t3_metrics,
            trade_dates,
            {"management": asdict(tier3_mgmt)},
            comparison_tier="exact",
        ),
        {
            **_variant_payload(
                "tier3_trend_strength_overlay",
                "Research-only sizing overlay: size multiplier = clip(abs(trend_efficiency_raw) / threshold, 0.5, 1.5) on Tier 3.",
                t3_overlay_trades,
                t3_overlay_block["metrics"],
                trade_dates,
                {"management": asdict(tier3_mgmt), "sizing_overlay": "trend_strength"},
                comparison_tier="research",
            ),
            "overlay_stats": t3_overlay_block["stats"],
        },
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

    t2a_train_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=tier2a_filter,
        management=tier2a_mgmt,
    )
    t2a_test_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=tier2a_filter,
        management=tier2a_mgmt,
    )
    t2a_train_overlay, t2a_train_overlay_block = _apply_strength_overlay(t2a_train_trades, dataset, params, base_strength)
    t2a_test_overlay, t2a_test_overlay_block = _apply_strength_overlay(t2a_test_trades, dataset, params, base_strength)

    summary = {
        "ranked_variants": ranked,
        "tier2a_trend_strength_overlay_walkforward_70_30": {
            "train": {
                "metrics": t2a_train_overlay_block["metrics"],
                **_risk_block(t2a_train_overlay, train_dates),
            },
            "test": {
                "metrics": t2a_test_overlay_block["metrics"],
                **_risk_block(t2a_test_overlay, test_dates),
            },
        },
        "notes": [
            "This is research-only because the overlay assumes fractional sizing around a 1-contract baseline.",
            "The purpose is to estimate the remaining upside of smarter sizing within the current signal family.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [_leaderboard_row(variant, summary_path) for variant in variants]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
