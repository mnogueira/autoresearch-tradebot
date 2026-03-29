from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _combine_runs
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_contract_weekday_switch_followups_20260329")


def _weekday_dates(trade_dates: pd.Index, weekdays: set[int]) -> pd.Index:
    allowed = {int(value) for value in weekdays}
    return pd.Index([value for value in trade_dates if pd.Timestamp(value).dayofweek in allowed])


def _combine_variant(
    tier2a_trades: pd.DataFrame,
    tier3_trades: pd.DataFrame,
    trade_dates: pd.Index,
    tier2a_dates: pd.Index,
) -> tuple[pd.DataFrame, dict]:
    tier3_dates = pd.Index(trade_dates.difference(tier2a_dates))
    tier2a_branch = filter_trades_to_dates(tier2a_trades, tier2a_dates)
    tier3_branch = filter_trades_to_dates(tier3_trades, tier3_dates)
    return _combine_runs([tier2a_branch, tier3_branch], trade_dates)


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
    tier3_full, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier3_management,
    )

    rollover_daily = contract_rollover_buckets(dataset)
    last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] <= 0])
    friday_dates = _weekday_dates(trade_dates, {4})
    thursday_friday_dates = _weekday_dates(trade_dates, {3, 4})

    candidates = [
        (
            "tier2a_last1_fri_else_tier3",
            "Use strengthened Tier 2A on the last 1 contract day and on Fridays, strengthened Tier 3 otherwise.",
            last1_dates.union(friday_dates),
        ),
        (
            "tier2a_fri_else_tier3",
            "Use strengthened Tier 2A on Fridays, strengthened Tier 3 otherwise.",
            friday_dates,
        ),
        (
            "tier2a_last1_thu_fri_else_tier3",
            "Use strengthened Tier 2A on the last 1 contract day and on Thursdays/Fridays, strengthened Tier 3 otherwise.",
            last1_dates.union(thursday_friday_dates),
        ),
    ]

    variants: list[dict] = []
    for name, rule, tier2a_dates in candidates:
        combined_trades, combined_metrics = _combine_variant(
            tier2a_trades=tier2a_full,
            tier3_trades=tier3_full,
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
                    "tier3_management": asdict(tier3_management),
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
            "tier3": {
                "metrics": calculate_metrics(tier3_full, trade_dates),
                **_risk_block(tier3_full, trade_dates),
            },
        },
        "variants": variants,
        "notes": [
            "This batch checks whether the Friday-aware improvement can be captured on the simpler Tier 2A versus Tier 3 switch, without direction-specific sleeve routing.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
