from __future__ import annotations

import json
from dataclasses import asdict, replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_contract_bucket_tier_compare_20260329")


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
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    entry_filter = _combine_filters(base_filter, roc5_filter)

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_trades, tier2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier2a_management,
    )
    tier3_trades, tier3_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier3_management,
    )

    rollover_daily = contract_rollover_buckets(dataset)
    buckets: dict[str, dict] = {}
    for bucket_name in ("first_3_contract_days", "mid_contract_days", "last_3_contract_days"):
        bucket_dates = rollover_daily.index[rollover_daily["rollover_bucket"] == bucket_name]
        tier2a_bucket = filter_trades_to_dates(tier2a_trades, bucket_dates)
        tier3_bucket = filter_trades_to_dates(tier3_trades, bucket_dates)
        tier2a_bucket_metrics = calculate_metrics(tier2a_bucket, bucket_dates)
        tier3_bucket_metrics = calculate_metrics(tier3_bucket, bucket_dates)
        buckets[bucket_name] = {
            "tier2a": {
                "metrics": tier2a_bucket_metrics,
                **_risk_block(tier2a_bucket, bucket_dates),
            },
            "tier3": {
                "metrics": tier3_bucket_metrics,
                **_risk_block(tier3_bucket, bucket_dates),
            },
            "delta_tier3_minus_tier2a": {
                "net_profit_brl": round(float(tier3_bucket_metrics["net_profit_brl"]) - float(tier2a_bucket_metrics["net_profit_brl"]), 2),
                "profit_factor": round(float(tier3_bucket_metrics["profit_factor"]) - float(tier2a_bucket_metrics["profit_factor"]), 4),
                "max_drawdown_pct": round(float(tier3_bucket_metrics["max_drawdown_pct"]) - float(tier2a_bucket_metrics["max_drawdown_pct"]), 2),
                "sortino_weighted_composite": round(
                    float(buckets[bucket_name]["tier3"]["sortino_weighted_composite"]) - float(buckets[bucket_name]["tier2a"]["sortino_weighted_composite"]),
                    4,
                ) if False else None,
            },
        }

    summary = {
        "tier2a_reference": {
            "metrics": tier2a_metrics,
            **_risk_block(tier2a_trades, trade_dates),
        },
        "tier3_reference": {
            "metrics": tier3_metrics,
            **_risk_block(tier3_trades, trade_dates),
        },
        "bucket_comparison": buckets,
        "params": {
            "tier2a_management": asdict(tier2a_management),
            "tier3_management": asdict(tier3_management),
            "roc_agreement_bars": 5,
            "ATR_Length": 10,
            "NumDaysToConsiderPreviousContractMARange": 2,
        },
    }

    # Fill bucket composite deltas after the structure exists.
    for bucket_name, block in summary["bucket_comparison"].items():
        block["delta_tier3_minus_tier2a"]["sortino_weighted_composite"] = round(
            float(block["tier3"]["sortino_weighted_composite"]) - float(block["tier2a"]["sortino_weighted_composite"]),
            4,
        )

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
