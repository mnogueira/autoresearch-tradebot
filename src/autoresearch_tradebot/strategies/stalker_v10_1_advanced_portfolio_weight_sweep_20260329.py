from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_advanced_portfolio_blend_followups_20260329 import _weekday_date_index
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
from .stalker_v10_1_local_geometry_portfolio_followups_20260329 import _equal_weight_portfolio, _scaled_sleeve
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_advanced_portfolio_weight_sweep_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _weighted_portfolio(tier2a_trades: pd.DataFrame, advanced_trades: pd.DataFrame, advanced_weight: float) -> pd.DataFrame:
    tier2a_weight = 1.0 - float(advanced_weight)
    sleeves = [
        _scaled_sleeve(tier2a_trades, tier2a_weight, "strengthened_tier2a"),
        _scaled_sleeve(advanced_trades, float(advanced_weight), "advanced_weekday_directional"),
    ]
    combined = pd.concat(sleeves, ignore_index=True)
    sort_columns = [column for column in ("entry_time", "exit_time", "signal_time") if column in combined.columns]
    if sort_columns:
        combined = combined.sort_values(sort_columns).reset_index(drop=True)
    return combined


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
    base_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))
    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_trades, tier2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=tier2a_management,
    )
    tier2a_long, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    tier3_short, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)
    directional_hybrid = _combined_trades(tier2a_long, tier3_short)
    rollover_daily = contract_rollover_buckets(dataset)
    last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] <= 0])
    friday_dates = _weekday_date_index(trade_dates, {4})
    advanced_dates = pd.Index(last1_dates.union(friday_dates))
    advanced_other_dates = pd.Index(trade_dates.difference(advanced_dates))
    advanced_trades = pd.concat(
        [
            filter_trades_to_dates(tier2a_trades, advanced_dates),
            filter_trades_to_dates(directional_hybrid, advanced_other_dates),
        ],
        ignore_index=True,
    )
    sort_columns = [column for column in ("entry_time", "exit_time", "signal_time") if column in advanced_trades.columns]
    if sort_columns:
        advanced_trades = advanced_trades.sort_values(sort_columns).reset_index(drop=True)
    advanced_metrics = calculate_metrics(advanced_trades, trade_dates)

    variants = []
    for advanced_weight in (0.25, 0.33, 0.5, 0.67, 0.75):
        portfolio_trades = _weighted_portfolio(tier2a_trades, advanced_trades, advanced_weight)
        train_portfolio = filter_trades_to_dates(portfolio_trades, train_dates)
        test_portfolio = filter_trades_to_dates(portfolio_trades, test_dates)
        recent_portfolio = filter_trades_to_dates(portfolio_trades, recent_60)
        variants.append(
            {
                "name": f"advanced_weight_{advanced_weight:.2f}",
                "metrics": calculate_metrics(portfolio_trades, trade_dates),
                **_risk_block(portfolio_trades, trade_dates),
                "walkforward_70_30": {
                    "train_metrics": calculate_metrics(train_portfolio, train_dates),
                    "train_risk": _risk_block(train_portfolio, train_dates),
                    "test_metrics": calculate_metrics(test_portfolio, test_dates),
                    "test_risk": _risk_block(test_portfolio, test_dates),
                },
                "recent_60d": {
                    "metrics": calculate_metrics(recent_portfolio, recent_60),
                    **_risk_block(recent_portfolio, recent_60),
                },
                "weights": {
                    "strengthened_tier2a": round(1.0 - float(advanced_weight), 2),
                    "advanced_weekday_directional": round(float(advanced_weight), 2),
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
            "tier2a_reference": {
                "metrics": tier2a_metrics,
                **_risk_block(tier2a_trades, trade_dates),
            },
            "advanced_weekday_directional_reference": {
                "metrics": advanced_metrics,
                **_risk_block(advanced_trades, trade_dates),
            },
        },
        "variants": variants,
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
