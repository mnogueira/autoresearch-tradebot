from __future__ import annotations

import json
from dataclasses import asdict, replace

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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_tier2a_roc_window_ultralocal_followups_20260329")


def _combine_filters(*filters):
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(entry_filter(context)) for entry_filter in active)

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
    management = ManagementConfig(min_minutes_between_entries=28)
    base_filter = session_filter({10, 11, 12, 14})

    variants = []
    best_variant = None
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    for roc_bars in (4, 5, 6):
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=_combine_filters(base_filter, _make_roc_filter(dataset, roc_bars)),
            management=management,
        )
        risk = _risk_block(trades, trade_dates)
        variant = {
            "name": f"tier2a_atr10_lookback2_roc{roc_bars}_cooldown28",
            "rule": f"Strengthened Tier 2A with ROC({roc_bars}) directional agreement.",
            "metrics": metrics,
            "risk_adjusted_metrics": risk["risk_adjusted_metrics"],
            "sortino_weighted_composite": risk["sortino_weighted_composite"],
            "params": {
                "management": asdict(management),
                "roc_agreement_bars": roc_bars,
                "ATR_Length": 10,
                "NumDaysToConsiderPreviousContractMARange": 2,
            },
        }
        variants.append(variant)
        if best_variant is None or float(variant["sortino_weighted_composite"]) > float(best_variant["sortino_weighted_composite"]):
            best_variant = variant

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
        "variants": ranked,
        "best_variant": best_variant,
        "notes": [
            "Ultra-local ROC agreement window sweep around the promoted ROC(5) window on strengthened Tier 2A.",
            "This batch checks whether ROC(4) or ROC(6) can beat the established ROC(5) local optimum.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if best_variant is not None:
        row = _leaderboard_row(best_variant, summary_path)
        row["family"] = "stalker_v10_1_tier2a_roc_window_ultralocal_followup"
        row["screening_method"] = "tier2a_roc_window_ultralocal_followup"
        row["comparison_tier"] = "research_exact"
        update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
