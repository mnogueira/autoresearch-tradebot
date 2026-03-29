from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_followups import combine_entry_filters, combine_runs, regime_day_filter, split_trade_dates_by_adx
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_regime_tier2a_horizon_followups_20260329")


def _payload(name: str, rule: str, trades: pd.DataFrame, metrics: dict[str, Any], trade_dates: pd.Index, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_regime_tier2a_horizon_followup",
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = "research_exact"
    row["screening_method"] = "regime_tier2a_horizon_followup"
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
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_dates = trade_dates[-60:]
    base_params = session_winner_params()
    horizon_params = replace(base_params, ATR_Length=14, NumDaysToConsiderPreviousContractMARange=3)
    base_filter = session_filter({10, 11, 12, 14})
    management = ManagementConfig(min_minutes_between_entries=25)
    trend_dates, range_dates, _ = split_trade_dates_by_adx(dataset, threshold=25.0)
    trend_day_set = {pd.Timestamp(value).date().isoformat() for value in trend_dates}
    range_day_set = {pd.Timestamp(value).date().isoformat() for value in range_dates}
    roc5_filter = _make_roc_filter(dataset, 5)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    tier2_trades, tier2_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=management,
    )
    tier2a_horizon_trades, tier2a_horizon_metrics = run_backtest_with_management(
        dataset=dataset,
        params=horizon_params,
        trade_dates=trade_dates,
        entry_filter=combine_entry_filters(base_filter, roc5_filter),
        management=management,
    )
    range_tier2_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=management,
    )
    trend_tier2a_horizon_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=horizon_params,
        trade_dates=trade_dates,
        entry_filter=combine_entry_filters(base_filter, roc5_filter, regime_day_filter(trend_day_set)),
        management=management,
    )
    regime_switch_trades, regime_switch_metrics = combine_runs(
        [range_tier2_trades, trend_tier2a_horizon_trades],
        trade_dates,
    )

    variants = [
        _payload(
            "tier2_reference",
            "Current Tier 2 baseline.",
            tier2_trades,
            tier2_metrics,
            trade_dates,
            {"management": asdict(management), "entry_hours": [10, 11, 12, 14]},
        ),
        _payload(
            "tier2a_horizon_reference",
            "Current strongest Tier 2A upgrade: ROC(5) agreement plus ATR_Length 14 and contract lookback 3.",
            tier2a_horizon_trades,
            tier2a_horizon_metrics,
            trade_dates,
            {
                "management": asdict(management),
                "entry_hours": [10, 11, 12, 14],
                "roc_agreement_bars": 5,
                "ATR_Length": 14,
                "NumDaysToConsiderPreviousContractMARange": 3,
            },
        ),
        _payload(
            "tier2_range_tier2a_horizon_trend_switch",
            "Use Tier 2 on prior-day ADX<=25 range days and Tier 2A horizon variant on prior-day ADX>25 trend days.",
            regime_switch_trades,
            regime_switch_metrics,
            trade_dates,
            {
                "management": asdict(management),
                "range_mode": "tier2",
                "trend_mode": "tier2a_horizon_reference",
                "adx_threshold": 25.0,
                "roc_agreement_bars": 5,
                "ATR_Length": 14,
                "NumDaysToConsiderPreviousContractMARange": 3,
            },
        ),
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

    best_variant = ranked[0]
    trade_map = {
        "tier2_reference": tier2_trades,
        "tier2a_horizon_reference": tier2a_horizon_trades,
        "tier2_range_tier2a_horizon_trend_switch": regime_switch_trades,
    }
    best_trades = trade_map[str(best_variant["name"])]
    train_trades = filter_trades_to_dates(best_trades, train_dates)
    test_trades = filter_trades_to_dates(best_trades, test_dates)
    recent_trades = filter_trades_to_dates(best_trades, recent_dates)

    summary = {
        "variants": ranked,
        "best_variant_walkforward_70_30": {
            "variant_name": str(best_variant["name"]),
            "train_metrics": calculate_metrics(train_trades, train_dates),
            "train_risk": _risk_block(train_trades, train_dates),
            "test_metrics": calculate_metrics(test_trades, test_dates),
            "test_risk": _risk_block(test_trades, test_dates),
        },
        "best_variant_recent_60d": {
            "variant_name": str(best_variant["name"]),
            "metrics": calculate_metrics(recent_trades, recent_dates),
            **_risk_block(recent_trades, recent_dates),
        },
        "notes": [
            "This batch checks whether the stronger ATR14/lookback3 ROC upgrade should only be used in trend days while plain Tier 2 handles range days.",
            "If the regime switch is only a tie, the simpler always-on Tier 2A horizon variant is the better operational choice.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [_leaderboard_row(variant, summary_path) for variant in variants])


if __name__ == "__main__":
    main()
