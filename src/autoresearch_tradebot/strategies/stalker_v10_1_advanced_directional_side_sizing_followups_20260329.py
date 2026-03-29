from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_advanced_atr_sizing_followups_20260329 import _weekday_date_index
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_runs
from .stalker_v10_1_directional_contract_switch_followups_20260329 import _combine_filters
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_advanced_directional_side_sizing_followups_20260329")


def _apply_side_weights(trades: pd.DataFrame, long_weight: float = 1.0, short_weight: float = 1.0) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    frame = trades.copy()
    weights = pd.Series(1.0, index=frame.index, dtype=float)
    weights.loc[frame["direction"].astype(str).eq("long")] = float(long_weight)
    weights.loc[frame["direction"].astype(str).eq("short")] = float(short_weight)
    frame["side_size_multiplier"] = weights.to_numpy(dtype=float)
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["side_size_multiplier"]
    if "pnl_points" in frame.columns:
        frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["side_size_multiplier"]
    return frame


def _variant_payload(name: str, rule: str, trades: pd.DataFrame, trade_dates: pd.Index, params: dict) -> dict:
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
    friday_dates = _weekday_date_index(trade_dates, {4})
    tier2a_dates = last1_dates.union(friday_dates)
    hybrid_dates = pd.Index(trade_dates.difference(tier2a_dates))

    tier2a_branch = filter_trades_to_dates(tier2a_full, tier2a_dates)
    hybrid_branch = filter_trades_to_dates(directional_hybrid_full, hybrid_dates)
    advanced_trades, _ = _combine_runs([tier2a_branch, hybrid_branch], trade_dates)

    variants = [
        _variant_payload(
            "advanced_reference",
            "Advanced weekday-aware directional branch reference.",
            advanced_trades,
            trade_dates,
            {"long_weight": 1.0, "short_weight": 1.0},
        ),
        _variant_payload(
            "advanced_short_0p90",
            "Advanced branch with 0.90x size on all short trades.",
            _apply_side_weights(advanced_trades, short_weight=0.90),
            trade_dates,
            {"long_weight": 1.0, "short_weight": 0.90},
        ),
        _variant_payload(
            "advanced_short_0p80",
            "Advanced branch with 0.80x size on all short trades.",
            _apply_side_weights(advanced_trades, short_weight=0.80),
            trade_dates,
            {"long_weight": 1.0, "short_weight": 0.80},
        ),
        _variant_payload(
            "advanced_long_1p10",
            "Advanced branch with 1.10x size on all long trades.",
            _apply_side_weights(advanced_trades, long_weight=1.10),
            trade_dates,
            {"long_weight": 1.10, "short_weight": 1.0},
        ),
        _variant_payload(
            "advanced_long_1p05_short_0p90",
            "Advanced branch with 1.05x size on longs and 0.90x size on shorts.",
            _apply_side_weights(advanced_trades, long_weight=1.05, short_weight=0.90),
            trade_dates,
            {"long_weight": 1.05, "short_weight": 0.90},
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

    best = ranked[0]
    best_trades = _apply_side_weights(
        advanced_trades,
        long_weight=float(best["params"]["long_weight"]),
        short_weight=float(best["params"]["short_weight"]),
    )

    summary = {
        "ranked_variants": ranked,
        "walkforward_70_30_best": {
            "train_metrics": calculate_metrics(filter_trades_to_dates(best_trades, train_dates), train_dates),
            "train_risk": _risk_block(filter_trades_to_dates(best_trades, train_dates), train_dates),
            "test_metrics": calculate_metrics(filter_trades_to_dates(best_trades, test_dates), test_dates),
            "test_risk": _risk_block(filter_trades_to_dates(best_trades, test_dates), test_dates),
        },
        "recent_60d_best": {
            "metrics": calculate_metrics(filter_trades_to_dates(best_trades, recent_60), recent_60),
            **_risk_block(filter_trades_to_dates(best_trades, recent_60), recent_60),
        },
        "notes": [
            "Research-only check for whether the advanced edge is mostly about de-risking shorts globally rather than only in high-ATR conditions.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
