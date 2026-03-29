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
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_hybrid_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _direction_filter(allowed_direction: int | None) -> Callable[[dict[str, Any]], bool] | None:
    if allowed_direction is None:
        return None
    allowed = int(allowed_direction)
    return lambda context: int(context["direction"]) == allowed


def _run_variant(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    management: ManagementConfig,
    direction: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _make_roc_filter(dataset, 5),
        _direction_filter(direction),
    )
    return run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )


def _combined_trades(*trade_frames: pd.DataFrame) -> pd.DataFrame:
    active = [frame for frame in trade_frames if frame is not None and not frame.empty]
    if not active:
        return pd.DataFrame()
    combined = pd.concat(active, ignore_index=True)
    if "entry_time" in combined.columns:
        combined = combined.sort_values(["session_date", "entry_time", "direction"], kind="stable").reset_index(drop=True)
    return combined


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    params: dict[str, Any],
) -> dict[str, Any]:
    metrics = calculate_metrics(trades, trade_dates)
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_full, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=None)
    tier2a_long_full, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    tier2a_short_full, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=-1)

    tier3_full, _ = _run_variant(dataset, trade_dates, tier3_management, direction=None)
    tier3_long_full, _ = _run_variant(dataset, trade_dates, tier3_management, direction=1)
    tier3_short_full, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)

    variants: list[dict[str, Any]] = [
        _variant_payload(
            "tier2a_reference",
            "Strengthened Tier 2A reference with both directions.",
            tier2a_full,
            trade_dates,
            {"management": asdict(tier2a_management), "direction": "both"},
        ),
        _variant_payload(
            "tier2a_long_only",
            "Strengthened Tier 2A using only long entries.",
            tier2a_long_full,
            trade_dates,
            {"management": asdict(tier2a_management), "direction": "long_only"},
        ),
        _variant_payload(
            "tier2a_short_only",
            "Strengthened Tier 2A using only short entries.",
            tier2a_short_full,
            trade_dates,
            {"management": asdict(tier2a_management), "direction": "short_only"},
        ),
        _variant_payload(
            "tier3_reference",
            "Strengthened Tier 3 reference with both directions.",
            tier3_full,
            trade_dates,
            {"management": asdict(tier3_management), "direction": "both"},
        ),
        _variant_payload(
            "tier3_long_only",
            "Strengthened Tier 3 using only long entries.",
            tier3_long_full,
            trade_dates,
            {"management": asdict(tier3_management), "direction": "long_only"},
        ),
        _variant_payload(
            "tier3_short_only",
            "Strengthened Tier 3 using only short entries.",
            tier3_short_full,
            trade_dates,
            {"management": asdict(tier3_management), "direction": "short_only"},
        ),
    ]

    hybrid_l2s3_full = _combined_trades(tier2a_long_full, tier3_short_full)
    hybrid_l3s2_full = _combined_trades(tier3_long_full, tier2a_short_full)
    variants.extend(
        [
            _variant_payload(
                "hybrid_tier2a_long_tier3_short",
                "Use strengthened Tier 2A longs and strengthened Tier 3 shorts.",
                hybrid_l2s3_full,
                trade_dates,
                {
                    "long_branch": {"management": asdict(tier2a_management), "direction": "long_only"},
                    "short_branch": {"management": asdict(tier3_management), "direction": "short_only"},
                },
            ),
            _variant_payload(
                "hybrid_tier3_long_tier2a_short",
                "Use strengthened Tier 3 longs and strengthened Tier 2A shorts.",
                hybrid_l3s2_full,
                trade_dates,
                {
                    "long_branch": {"management": asdict(tier3_management), "direction": "long_only"},
                    "short_branch": {"management": asdict(tier2a_management), "direction": "short_only"},
                },
            ),
        ]
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

    best_hybrid_name = variants[0]["name"]
    best_hybrid_train = {}
    best_hybrid_test = {}
    best_hybrid_recent60 = {}

    if best_hybrid_name == "hybrid_tier2a_long_tier3_short":
        train_long, _ = _run_variant(dataset, train_dates, tier2a_management, direction=1)
        train_short, _ = _run_variant(dataset, train_dates, tier3_management, direction=-1)
        test_long, _ = _run_variant(dataset, test_dates, tier2a_management, direction=1)
        test_short, _ = _run_variant(dataset, test_dates, tier3_management, direction=-1)
        recent_long = filter_trades_to_dates(tier2a_long_full, recent_60)
        recent_short = filter_trades_to_dates(tier3_short_full, recent_60)
        train_trades = _combined_trades(train_long, train_short)
        test_trades = _combined_trades(test_long, test_short)
        recent_trades = _combined_trades(recent_long, recent_short)
        best_hybrid_train = _variant_payload(
            "hybrid_tier2a_long_tier3_short_train",
            "Walk-forward train slice for the hybrid long/short split.",
            train_trades,
            train_dates,
            {},
        )
        best_hybrid_test = _variant_payload(
            "hybrid_tier2a_long_tier3_short_test",
            "Walk-forward test slice for the hybrid long/short split.",
            test_trades,
            test_dates,
            {},
        )
        best_hybrid_recent60 = _variant_payload(
            "hybrid_tier2a_long_tier3_short_recent60",
            "Recent 60-trading-day slice for the hybrid long/short split.",
            recent_trades,
            recent_60,
            {},
        )
    elif best_hybrid_name == "hybrid_tier3_long_tier2a_short":
        train_long, _ = _run_variant(dataset, train_dates, tier3_management, direction=1)
        train_short, _ = _run_variant(dataset, train_dates, tier2a_management, direction=-1)
        test_long, _ = _run_variant(dataset, test_dates, tier3_management, direction=1)
        test_short, _ = _run_variant(dataset, test_dates, tier2a_management, direction=-1)
        recent_long = filter_trades_to_dates(tier3_long_full, recent_60)
        recent_short = filter_trades_to_dates(tier2a_short_full, recent_60)
        train_trades = _combined_trades(train_long, train_short)
        test_trades = _combined_trades(test_long, test_short)
        recent_trades = _combined_trades(recent_long, recent_short)
        best_hybrid_train = _variant_payload(
            "hybrid_tier3_long_tier2a_short_train",
            "Walk-forward train slice for the hybrid long/short split.",
            train_trades,
            train_dates,
            {},
        )
        best_hybrid_test = _variant_payload(
            "hybrid_tier3_long_tier2a_short_test",
            "Walk-forward test slice for the hybrid long/short split.",
            test_trades,
            test_dates,
            {},
        )
        best_hybrid_recent60 = _variant_payload(
            "hybrid_tier3_long_tier2a_short_recent60",
            "Recent 60-trading-day slice for the hybrid long/short split.",
            recent_trades,
            recent_60,
            {},
        )

    summary = {
        "variants": variants,
        "best_hybrid_walkforward": {
            "train": best_hybrid_train,
            "test": best_hybrid_test,
            "recent_60d": best_hybrid_recent60,
        },
        "notes": [
            "Directional asymmetry scout on strengthened Tier 2A and Tier 3.",
            "Hybrid sleeves combine the stronger long branch from one tier with the stronger short branch from the other tier.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
