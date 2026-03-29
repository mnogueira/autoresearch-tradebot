from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_core_geometry_followups_20260329")


def _combine_filters(*filters):
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _variant_payload(
    name: str,
    params_block: dict[str, Any],
    trades,
    metrics: dict[str, Any],
    trade_dates,
) -> dict[str, Any]:
    return {
        "name": name,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params_block,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_core_geometry_followup",
        metrics=dict(variant["metrics"]),
        notes="Exact Tier 2A core-geometry sweep on RetracementLevel and FilterAsPercOfContractMARange.",
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = "research_exact"
    row["screening_method"] = "core_geometry_followup"
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    entry_filter = _combine_filters(base_filter, roc5_filter)
    management = ManagementConfig(min_minutes_between_entries=25)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    variants_to_run = [
        ("tier2a_baseline", base_params),
        (
            "tier2a_retracement_0p20",
            replace(base_params, RetracementLevel=0.20),
        ),
        (
            "tier2a_retracement_0p30",
            replace(base_params, RetracementLevel=0.30),
        ),
        (
            "tier2a_contractrange_0p25",
            replace(base_params, FilterAsPercOfContractMARange=0.25),
        ),
        (
            "tier2a_contractrange_0p35",
            replace(base_params, FilterAsPercOfContractMARange=0.35),
        ),
        (
            "tier2a_retracement_0p20_contractrange_0p25",
            replace(base_params, RetracementLevel=0.20, FilterAsPercOfContractMARange=0.25),
        ),
        (
            "tier2a_retracement_0p30_contractrange_0p35",
            replace(base_params, RetracementLevel=0.30, FilterAsPercOfContractMARange=0.35),
        ),
    ]

    ranked_variants: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    for name, params in variants_to_run:
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        variant = _variant_payload(
            name=name,
            params_block={
                "management": asdict(management),
                "roc_agreement_bars": 5,
                "RetracementLevel": float(params.RetracementLevel),
                "FilterAsPercOfContractMARange": float(params.FilterAsPercOfContractMARange),
            },
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
        )
        ranked_variants.append(variant)
        leaderboard_rows.append(_leaderboard_row(variant, summary_path))

    ranked_variants.sort(
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked_variants, start=1):
        row["batch_rank"] = rank

    summary = {
        "notes": [
            "This batch targets the remaining under-explored core geometry knobs on the simpler ROC-enhanced Tier 2A line.",
            "If no variant beats the current Tier 2A composite materially, the current signal family is likely at its local parameter ceiling.",
        ],
        "variants_ranked": ranked_variants,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
