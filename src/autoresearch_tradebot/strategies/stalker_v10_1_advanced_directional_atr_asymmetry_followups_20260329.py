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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_advanced_directional_atr_asymmetry_followups_20260329")


def _apply_asymmetric_directional_weights(
    trades: pd.DataFrame,
    high_atr_short_weight: float | None,
    low_atr_long_weight: float | None,
    high_mask: pd.Series,
    low_mask: pd.Series,
) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    frame = trades.copy()
    session_dates = pd.to_datetime(frame["session_date"]).dt.normalize()
    weights = pd.Series(1.0, index=frame.index, dtype=float)
    is_long = frame["direction"].astype(str).eq("long")
    is_short = frame["direction"].astype(str).eq("short")

    if high_atr_short_weight is not None:
        mapped_high = session_dates.map(high_mask).fillna(False).astype(bool)
        weights.loc[is_short & mapped_high] = float(high_atr_short_weight)

    if low_atr_long_weight is not None:
        mapped_low = session_dates.map(low_mask).fillna(False).astype(bool)
        weights.loc[is_long & mapped_low] = weights.loc[is_long & mapped_low] * float(low_atr_long_weight)

    frame["asym_atr_size_multiplier"] = weights.to_numpy(dtype=float)
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["asym_atr_size_multiplier"]
    if "pnl_points" in frame.columns:
        frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["asym_atr_size_multiplier"]
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
    high_q67 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)
    low_q33 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.3333)
    high_mask = prior_day_atr14 > high_q67
    low_mask = prior_day_atr14 < low_q33

    variants = [
        _variant_payload(
            "advanced_reference",
            "Advanced weekday-aware directional branch reference.",
            advanced_trades,
            trade_dates,
            {"high_atr_short_weight": None, "low_atr_long_weight": None},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70",
            "Advanced branch with 0.70x size on top-ATR days for short trades only.",
            _apply_asymmetric_directional_weights(advanced_trades, 0.70, None, high_mask, low_mask),
            trade_dates,
            {"high_atr_short_weight": 0.70, "low_atr_long_weight": None},
        ),
        _variant_payload(
            "advanced_low_atr_long_1p10",
            "Advanced branch with 1.10x size on low-ATR days for long trades only.",
            _apply_asymmetric_directional_weights(advanced_trades, None, 1.10, high_mask, low_mask),
            trade_dates,
            {"high_atr_short_weight": None, "low_atr_long_weight": 1.10},
        ),
        _variant_payload(
            "advanced_low_atr_long_1p25",
            "Advanced branch with 1.25x size on low-ATR days for long trades only.",
            _apply_asymmetric_directional_weights(advanced_trades, None, 1.25, high_mask, low_mask),
            trade_dates,
            {"high_atr_short_weight": None, "low_atr_long_weight": 1.25},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70_low_atr_long_1p10",
            "Advanced branch with 0.70x top-ATR short sizing and 1.10x low-ATR long sizing.",
            _apply_asymmetric_directional_weights(advanced_trades, 0.70, 1.10, high_mask, low_mask),
            trade_dates,
            {"high_atr_short_weight": 0.70, "low_atr_long_weight": 1.10},
        ),
        _variant_payload(
            "advanced_high_atr_short_0p70_low_atr_long_1p25",
            "Advanced branch with 0.70x top-ATR short sizing and 1.25x low-ATR long sizing.",
            _apply_asymmetric_directional_weights(advanced_trades, 0.70, 1.25, high_mask, low_mask),
            trade_dates,
            {"high_atr_short_weight": 0.70, "low_atr_long_weight": 1.25},
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
    best_trades = _apply_asymmetric_directional_weights(
        advanced_trades,
        best["params"]["high_atr_short_weight"],
        best["params"]["low_atr_long_weight"],
        high_mask,
        low_mask,
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
            "Research-only asymmetry check: can a low-ATR long boost add to the new short-side ATR trim ceiling?",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
