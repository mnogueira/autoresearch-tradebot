from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any, Callable

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_static_weekday_filter_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _weekday_filter(dataset: V10Dataset, allowed_weekdays: set[int]) -> Callable[[dict[str, Any]], bool]:
    allowed = {int(value) for value in allowed_weekdays}
    session_dates = pd.to_datetime(dataset.bars_m1["session_date"]).to_numpy()

    def _allow(context: dict[str, Any]) -> bool:
        trade_date = pd.Timestamp(session_dates[int(context["dataset_index"])])
        return int(trade_date.dayofweek) in allowed

    return _allow


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
    base_session = session_filter({10, 11, 12, 14})
    roc5 = _make_roc_filter(dataset, 5)
    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    weekday_sets = {
        "skip_friday": {0, 1, 2, 3},
    }
    candidates = [
        (
            "tier2a_skip_friday",
            "Strengthened Tier 2A but skip Friday entirely.",
            _combine_filters(base_session, roc5, _weekday_filter(dataset, weekday_sets["skip_friday"])),
            tier2a_management,
            weekday_sets["skip_friday"],
        ),
        (
            "tier3_skip_friday",
            "Strengthened Tier 3 but skip Friday entirely.",
            _combine_filters(base_session, roc5, _weekday_filter(dataset, weekday_sets["skip_friday"])),
            tier3_management,
            weekday_sets["skip_friday"],
        ),
    ]

    variants: list[dict[str, Any]] = []
    for name, rule, entry_filter, management, allowed_weekdays in candidates:
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        variant = {
            "name": name,
            "rule": rule,
            "metrics": metrics,
            **_risk_block(trades, trade_dates),
            "recent_60d": {
                "metrics": calculate_metrics(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_60))].reset_index(drop=True),
                    recent_60,
                ),
                **_risk_block(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_60))].reset_index(drop=True),
                    recent_60,
                ),
            },
            "recent_30d": {
                "metrics": calculate_metrics(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_30))].reset_index(drop=True),
                    recent_30,
                ),
                **_risk_block(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_30))].reset_index(drop=True),
                    recent_30,
                ),
            },
            "recent_10d": {
                "metrics": calculate_metrics(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_10))].reset_index(drop=True),
                    recent_10,
                ),
                **_risk_block(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(recent_10))].reset_index(drop=True),
                    recent_10,
                ),
            },
            "walkforward_70_30": {
                "train_metrics": calculate_metrics(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(train_dates))].reset_index(drop=True),
                    train_dates,
                ),
                "train_risk": _risk_block(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(train_dates))].reset_index(drop=True),
                    train_dates,
                ),
                "test_metrics": calculate_metrics(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(test_dates))].reset_index(drop=True),
                    test_dates,
                ),
                "test_risk": _risk_block(
                    trades.loc[pd.to_datetime(trades["session_date"]).isin(pd.to_datetime(test_dates))].reset_index(drop=True),
                    test_dates,
                ),
            },
            "params": {
                "management": asdict(management),
                "ATR_Length": int(params.ATR_Length),
                "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
                "roc_agreement_bars": 5,
                "allowed_weekdays": sorted(int(value) for value in allowed_weekdays),
            },
        }
        variants.append(variant)

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
            "This narrowed batch checks whether the recent Friday softness can be captured by a simple static Friday skip on the strengthened static tiers, without directional or contract-cycle routing.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
