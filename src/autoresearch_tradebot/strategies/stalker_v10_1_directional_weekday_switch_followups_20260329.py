from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_runs, _date_filter, _date_set
from .stalker_v10_1_directional_contract_switch_followups_20260329 import _combine_filters
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_weekday_switch_followups_20260329")


def _weekday_date_index(trade_dates: pd.Index, weekdays: set[int]) -> pd.Index:
    allowed = {int(value) for value in weekdays}
    return pd.Index([value for value in trade_dates if pd.Timestamp(value).dayofweek in allowed])


def _combine_trade_sets(
    tier2a_trades: pd.DataFrame,
    directional_trades: pd.DataFrame,
    trade_dates: pd.Index,
    tier2a_dates: pd.Index,
) -> tuple[pd.DataFrame, dict]:
    directional_dates = pd.Index(trade_dates.difference(tier2a_dates))
    tier2a_branch = filter_trades_to_dates(tier2a_trades, tier2a_dates)
    directional_branch = filter_trades_to_dates(directional_trades, directional_dates)
    return _combine_runs([tier2a_branch, directional_branch], trade_dates)


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
    last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] <= 0])
    thursday_dates = _weekday_date_index(trade_dates, {3})
    friday_dates = _weekday_date_index(trade_dates, {4})
    thursday_friday_dates = _weekday_date_index(trade_dates, {3, 4})

    candidates = [
        (
            "tier2a_thu_fri_else_directional_hybrid",
            "Use strengthened Tier 2A on Thursdays and Fridays, directional hybrid on Monday-Wednesday.",
            thursday_friday_dates,
        ),
        (
            "tier2a_fri_else_directional_hybrid",
            "Use strengthened Tier 2A on Fridays, directional hybrid otherwise.",
            friday_dates,
        ),
        (
            "tier2a_thu_else_directional_hybrid",
            "Use strengthened Tier 2A on Thursdays, directional hybrid otherwise.",
            thursday_dates,
        ),
        (
            "tier2a_last1_thu_fri_else_directional_hybrid",
            "Use strengthened Tier 2A on the last 1 contract day and on Thursdays/Fridays, directional hybrid otherwise.",
            last1_dates.union(thursday_friday_dates),
        ),
        (
            "tier2a_last1_fri_else_directional_hybrid",
            "Use strengthened Tier 2A on the last 1 contract day and Fridays, directional hybrid otherwise.",
            last1_dates.union(friday_dates),
        ),
    ]

    variants: list[dict] = []
    for name, rule, tier2a_dates in candidates:
        combined_trades, combined_metrics = _combine_trade_sets(
            tier2a_trades=tier2a_full,
            directional_trades=directional_hybrid_full,
            trade_dates=trade_dates,
            tier2a_dates=tier2a_dates,
        )
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
                "params": {
                    "tier2a_management": asdict(tier2a_management),
                    "directional_hybrid": {
                        "long_branch_management": asdict(tier2a_management),
                        "short_branch_management": asdict(tier3_management),
                    },
                    "tier2a_weekdays": sorted({pd.Timestamp(value).day_name() for value in tier2a_dates}),
                    "tier2a_dates_count": int(len(pd.Index(tier2a_dates).unique())),
                    "ATR_Length": int(params.ATR_Length),
                    "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
                    "roc_agreement_bars": 5,
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
        "variants": variants,
        "notes": [
            "This batch checks whether the directional hybrid's recent Thursday/Friday softness is best handled by routing those days back to the simpler strengthened Tier 2A.",
            "Variants also include the strongest last-1-contract-day switch because that was already helpful in the directional branch.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
