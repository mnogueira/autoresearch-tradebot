from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
from ta.momentum import RSIIndicator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_optimization_screening import make_rsi_confirmation_filter
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_rsi_agreement_followups_20260329")


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
    management = ManagementConfig(min_minutes_between_entries=28)

    close = dataset.bars_m1["Close"].astype(float)
    rsi_arrays = {
        "rsi7": RSIIndicator(close=close, window=7).rsi().shift(1).to_numpy(dtype=float),
        "rsi14": RSIIndicator(close=close, window=14).rsi().shift(1).to_numpy(dtype=float),
    }
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)

    variants: list[dict] = []
    best_variant: dict | None = None
    best_summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    for name, rsi_array in rsi_arrays.items():
        for threshold in (50.0, 55.0, 60.0):
            entry_filter = _combine_filters(base_filter, roc5_filter, make_rsi_confirmation_filter(rsi_array, threshold))
            trades, metrics = run_backtest_with_management(
                dataset=dataset,
                params=params,
                trade_dates=trade_dates,
                entry_filter=entry_filter,
                management=management,
            )
            variant = {
                "name": f"tier2a_{name}_confirm_{int(threshold)}",
                "rule": f"Strengthened Tier 2A with {name.upper()} directional confirmation at threshold {int(threshold)}.",
                "metrics": metrics,
                **_risk_block(trades, trade_dates),
                "params": {
                    "rsi_period": int(name.replace('rsi', '')),
                    "rsi_threshold": float(threshold),
                    "roc_agreement_bars": 5,
                    "ATR_Length": 10,
                    "NumDaysToConsiderPreviousContractMARange": 2,
                    "min_minutes_between_entries": 28,
                },
            }
            variants.append(variant)
            if best_variant is None or float(variant["sortino_weighted_composite"]) > float(best_variant["sortino_weighted_composite"]):
                best_variant = variant

    summary = {
        "reference_tier2a": {
            "metrics": {
                "name": "strengthened_tier2a_reference",
            }
        },
        "variants": variants,
        "best_variant": best_variant,
    }

    # Fill the exact strengthened Tier 2A reference for comparison.
    reference_filter = _combine_filters(base_filter, roc5_filter)
    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=reference_filter,
        management=management,
    )
    summary["reference_tier2a"] = {
        "metrics": reference_metrics,
        **_risk_block(reference_trades, trade_dates),
    }

    best_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if best_variant is not None:
        row = _leaderboard_row(best_variant, best_summary_path)
        row["family"] = "stalker_v10_1_rsi_agreement_followup"
        row["screening_method"] = "rsi_agreement_followup"
        row["comparison_tier"] = "research_exact"
        update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
