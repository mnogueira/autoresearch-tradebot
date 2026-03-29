from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_runs, _date_filter, _date_set
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_contract_switch_followups_20260329")


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
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    tier2a_full, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier2a_management,
    )
    tier2a_long_full, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    tier3_short_full, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)
    directional_hybrid_full = _combined_trades(tier2a_long_full, tier3_short_full)

    rollover_daily = contract_rollover_buckets(dataset)
    first3_dates = pd.Index(rollover_daily.index[rollover_daily["contract_day_number"] <= 3])
    last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] <= 0])
    last3_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] <= 2])

    candidates = [
        ("tier2a_last1_else_directional_hybrid", "Use full strengthened Tier 2A on the last 1 contract day and the directional hybrid otherwise.", last1_dates),
        ("tier2a_last3_else_directional_hybrid", "Use full strengthened Tier 2A on the last 3 contract days and the directional hybrid otherwise.", last3_dates),
        ("tier2a_first3_last1_else_directional_hybrid", "Use full strengthened Tier 2A on the first 3 and last 1 contract days and the directional hybrid otherwise.", first3_dates.union(last1_dates)),
    ]

    variants = []
    for name, rule, tier2a_dates in candidates:
        hybrid_dates = pd.Index(trade_dates.difference(tier2a_dates))
        tier2a_branch = filter_trades_to_dates(tier2a_full, tier2a_dates)
        hybrid_branch = filter_trades_to_dates(directional_hybrid_full, hybrid_dates)
        combined_trades, combined_metrics = _combine_runs([tier2a_branch, hybrid_branch], trade_dates)
        variants.append(
            {
                "name": name,
                "rule": rule,
                "metrics": combined_metrics,
                **_risk_block(combined_trades, trade_dates),
                "recent_60d": {
                    "metrics": calculate_metrics(filter_trades_to_dates(combined_trades, recent_60), recent_60),
                    **_risk_block(filter_trades_to_dates(combined_trades, recent_60), recent_60),
                },
                "recent_30d": {
                    "metrics": calculate_metrics(filter_trades_to_dates(combined_trades, recent_30), recent_30),
                    **_risk_block(filter_trades_to_dates(combined_trades, recent_30), recent_30),
                },
                "recent_10d": {
                    "metrics": calculate_metrics(filter_trades_to_dates(combined_trades, recent_10), recent_10),
                    **_risk_block(filter_trades_to_dates(combined_trades, recent_10), recent_10),
                },
                "walkforward_70_30": {
                    "train_metrics": calculate_metrics(filter_trades_to_dates(combined_trades, train_dates), train_dates),
                    "train_risk": _risk_block(filter_trades_to_dates(combined_trades, train_dates), train_dates),
                    "test_metrics": calculate_metrics(filter_trades_to_dates(combined_trades, test_dates), test_dates),
                    "test_risk": _risk_block(filter_trades_to_dates(combined_trades, test_dates), test_dates),
                },
            }
        )

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
        "references": {
            "tier2a": {
                "metrics": calculate_metrics(tier2a_full, trade_dates),
                **_risk_block(tier2a_full, trade_dates),
            },
            "directional_hybrid": {
                "metrics": calculate_metrics(directional_hybrid_full, trade_dates),
                **_risk_block(directional_hybrid_full, trade_dates),
            },
        },
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
