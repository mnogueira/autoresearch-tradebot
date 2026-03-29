from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_tier2a_cooldown_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    variants: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    for cooldown in (20, 22, 25, 28, 30):
        management = ManagementConfig(min_minutes_between_entries=cooldown)
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        variant = {
            "name": f"tier2a_atr10_lookback2_cooldown{cooldown}",
            "metrics": metrics,
            **_risk_block(trades, trade_dates),
            "params": {
                "management": asdict(management),
                "roc_agreement_bars": 5,
                "ATR_Length": int(params.ATR_Length),
                "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
                "RetracementLevel": float(params.RetracementLevel),
                "FilterAsPercOfContractMARange": float(params.FilterAsPercOfContractMARange),
            },
        }
        variants.append(variant)

        leaderboard_variant = {
            "name": (
                "tier2a_roc5_atr10_contractlookback2_cooldown28"
                if cooldown == 28
                else f"tier2a_roc5_atr10_contractlookback2_cooldown{cooldown}"
            ),
            "rule": (
                "Promoted Tier 2A local cooldown refinement: ROC(5) agreement, ATR_Length 10, "
                "contract lookback 2, cooldown 28m."
                if cooldown == 28
                else f"Tier 2A local cooldown variant at {cooldown} minutes."
            ),
            "metrics": metrics,
            "risk_adjusted_metrics": variant["risk_adjusted_metrics"],
            "sortino_weighted_composite": variant["sortino_weighted_composite"],
            "params": variant["params"],
        }
        row = _leaderboard_row(leaderboard_variant, summary_path)
        row["family"] = "stalker_v10_1_tier2a_cooldown_followup"
        row["screening_method"] = "tier2a_cooldown_followup"
        row["comparison_tier"] = "research_exact"
        leaderboard_rows.append(row)

    variants.sort(
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(variants, start=1):
        row["batch_rank"] = rank

    summary = {
        "variants": variants,
        "notes": [
            "Cooldown sweep on promoted Tier 2A geometry.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
