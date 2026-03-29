from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_advanced_atr_sizing_followups_20260329 import _weekday_date_index
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_advanced_directional_short_atr_weekday_combo_20260329")


def _apply_directional_weights(
    trades: pd.DataFrame,
    atr_weights: pd.Series | None,
    weekday_weights: pd.Series | None,
    target_direction: str = "short",
) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    frame = trades.copy()
    weights = pd.Series(1.0, index=frame.index, dtype=float)
    direction_mask = frame["direction"].astype(str).eq(str(target_direction))
    session_dates = pd.to_datetime(frame["session_date"]).dt.normalize()
    if atr_weights is not None:
        mapped = session_dates.map(atr_weights).fillna(1.0).astype(float)
        weights.loc[direction_mask] = weights.loc[direction_mask] * mapped.loc[direction_mask]
    if weekday_weights is not None:
        mapped = session_dates.map(weekday_weights).fillna(1.0).astype(float)
        weights.loc[direction_mask] = weights.loc[direction_mask] * mapped.loc[direction_mask]
    frame["combo_size_multiplier"] = weights.to_numpy(dtype=float)
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["combo_size_multiplier"]
    if "pnl_points" in frame.columns:
        frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["combo_size_multiplier"]
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

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    q67 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)
    atr_weights_070 = pd.Series(1.0, index=prior_day_atr14.index, dtype=float)
    atr_weights_070.loc[(prior_day_atr14 > q67).fillna(False)] = 0.70

    weekday_short_075 = pd.Series(1.0, index=trade_dates, dtype=float)
    weekday_short_075.loc[_weekday_date_index(trade_dates, {3, 4})] = 0.75
    weekday_short_085 = pd.Series(1.0, index=trade_dates, dtype=float)
    weekday_short_085.loc[_weekday_date_index(trade_dates, {3, 4})] = 0.85

    variants = [
        _variant_payload(
            "advanced_reference",
            "Advanced weekday-aware directional branch reference.",
            advanced_trades,
            trade_dates,
            {"short_atr_weight": 1.0, "short_weekday_weight": 1.0},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70",
            "Advanced branch with 0.70x size on top-ATR days for short trades only.",
            _apply_directional_weights(advanced_trades, atr_weights_070, None),
            trade_dates,
            {"short_atr_weight": 0.70, "short_weekday_weight": 1.0},
        ),
        _variant_payload(
            "advanced_thu_fri_short_0p75",
            "Advanced branch with 0.75x size on Thursdays and Fridays for short trades only.",
            _apply_directional_weights(advanced_trades, None, weekday_short_075),
            trade_dates,
            {"short_atr_weight": 1.0, "short_weekday_weight": 0.75},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70_thu_fri_short_0p85",
            "Advanced branch with 0.70x top-ATR short sizing plus 0.85x Thursday/Friday short sizing.",
            _apply_directional_weights(advanced_trades, atr_weights_070, weekday_short_085),
            trade_dates,
            {"short_atr_weight": 0.70, "short_weekday_weight": 0.85},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70_thu_fri_short_0p75",
            "Advanced branch with 0.70x top-ATR short sizing plus 0.75x Thursday/Friday short sizing.",
            _apply_directional_weights(advanced_trades, atr_weights_070, weekday_short_075),
            trade_dates,
            {"short_atr_weight": 0.70, "short_weekday_weight": 0.75},
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
    if best["name"] == "advanced_reference":
        best_trades = advanced_trades
    elif best["name"] == "advanced_high_atr_short_0p70":
        best_trades = _apply_directional_weights(advanced_trades, atr_weights_070, None)
    elif best["name"] == "advanced_thu_fri_short_0p75":
        best_trades = _apply_directional_weights(advanced_trades, None, weekday_short_075)
    elif best["name"] == "advanced_high_atr_short_0p70_thu_fri_short_0p85":
        best_trades = _apply_directional_weights(advanced_trades, atr_weights_070, weekday_short_085)
    else:
        best_trades = _apply_directional_weights(advanced_trades, atr_weights_070, weekday_short_075)

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
            "Research-only check for whether the advanced short-side ATR trim compounds with short-side Thursday/Friday de-risking.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
