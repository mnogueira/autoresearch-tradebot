from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

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
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_rollover_tier_switch_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _combine_runs(trade_frames: list[pd.DataFrame], trade_dates: pd.Index) -> tuple[pd.DataFrame, dict]:
    non_empty = [frame for frame in trade_frames if not frame.empty]
    if not non_empty:
        empty = pd.DataFrame(columns=["session_date", "entry_time", "exit_time", "signal_time", "pnl_brl", "pnl_points"])
        return empty, calculate_metrics(empty, trade_dates)
    combined = pd.concat(non_empty, ignore_index=True)
    sort_columns = [column for column in ("entry_time", "exit_time", "signal_time") if column in combined.columns]
    if sort_columns:
        combined = combined.sort_values(sort_columns).reset_index(drop=True)
    return combined, calculate_metrics(combined, trade_dates)


def _date_set(index: pd.Index) -> set[str]:
    return {pd.Timestamp(value).date().isoformat() for value in index}


def _date_filter(date_set: set[str]):
    def _allow(context):
        return pd.Timestamp(context["session_date"]).date().isoformat() in date_set

    return _allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    entry_filter = _combine_filters(base_filter, roc5_filter)

    rollover_daily = contract_rollover_buckets(dataset)
    rollover_dates = pd.Index(rollover_daily.index[rollover_daily["rollover_bucket"] == "last_3_contract_days"])
    normal_dates = pd.Index(rollover_daily.index[rollover_daily["rollover_bucket"] != "last_3_contract_days"])

    tier2a_all_trades, tier2a_all_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier2a_management,
    )
    tier3_all_trades, tier3_all_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier3_management,
    )

    tier2a_rollover_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(entry_filter, _date_filter(_date_set(rollover_dates))),
        management=tier2a_management,
    )
    tier3_normal_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=_combine_filters(entry_filter, _date_filter(_date_set(normal_dates))),
        management=tier3_management,
    )
    switched_trades, switched_metrics = _combine_runs([tier2a_rollover_trades, tier3_normal_trades], trade_dates)

    train_switched = filter_trades_to_dates(switched_trades, train_dates)
    test_switched = filter_trades_to_dates(switched_trades, test_dates)
    recent_switched = filter_trades_to_dates(switched_trades, recent_60)

    summary = {
        "tier2a_reference": {
            "metrics": tier2a_all_metrics,
            **_risk_block(tier2a_all_trades, trade_dates),
        },
        "tier3_reference": {
            "metrics": tier3_all_metrics,
            **_risk_block(tier3_all_trades, trade_dates),
        },
        "rollover_tier_switch": {
            "rule": "Use strengthened Tier 2A in the last 3 contract days and strengthened Tier 3 on all other days.",
            "metrics": switched_metrics,
            **_risk_block(switched_trades, trade_dates),
        },
        "walkforward_70_30": {
            "train_metrics": calculate_metrics(train_switched, train_dates),
            "train_risk": _risk_block(train_switched, train_dates),
            "test_metrics": calculate_metrics(test_switched, test_dates),
            "test_risk": _risk_block(test_switched, test_dates),
        },
        "recent_60d": {
            "metrics": calculate_metrics(recent_switched, recent_60),
            **_risk_block(recent_switched, recent_60),
        },
        "params": {
            "tier2a_management": asdict(tier2a_management),
            "tier3_management": asdict(tier3_management),
            "roc_agreement_bars": 5,
            "ATR_Length": 10,
            "NumDaysToConsiderPreviousContractMARange": 2,
            "switch_rule": "tier2a_on_last3_contract_days_else_tier3",
        },
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_variant = {
        "name": "tier2a_rollover_tail_else_tier3_local_geometry",
        "rule": "Use strengthened Tier 2A in the last 3 contract days and strengthened Tier 3 on all other days.",
        "metrics": switched_metrics,
        "risk_adjusted_metrics": summary["rollover_tier_switch"]["risk_adjusted_metrics"],
        "sortino_weighted_composite": summary["rollover_tier_switch"]["sortino_weighted_composite"],
        "params": summary["params"],
    }
    row = _leaderboard_row(leaderboard_variant, summary_path)
    row["family"] = "stalker_v10_1_rollover_tier_switch_followup"
    row["screening_method"] = "rollover_tier_switch_followup"
    row["comparison_tier"] = "research_exact"
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
