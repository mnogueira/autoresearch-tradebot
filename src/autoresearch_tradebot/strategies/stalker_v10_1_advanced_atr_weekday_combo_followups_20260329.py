from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_advanced_atr_sizing_followups_20260329 import _weekday_date_index
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_atr_regime_sizing_followups_20260329 import _apply_session_weights
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_runs
from .stalker_v10_1_directional_contract_switch_followups_20260329 import _combine_filters
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_advanced_atr_weekday_combo_followups_20260329")


def _variant_payload(name: str, rule: str, trades: pd.DataFrame, trade_dates: pd.Index, params: dict) -> dict:
    metrics = calculate_metrics(trades, trade_dates)
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _build_advanced_trades(dataset: V10Dataset, trade_dates: pd.Index) -> tuple[pd.DataFrame, ManagementConfig, ManagementConfig]:
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
    return advanced_trades, tier2a_management, tier3_management


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    advanced_trades, tier2a_management, tier3_management = _build_advanced_trades(dataset, trade_dates)

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    high_cut = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)
    high_atr_mask = prior_day_atr14 > high_cut
    thu_fri_dates = _weekday_date_index(trade_dates, {3, 4})

    variant_specs = [
        ("advanced_high_atr_0p75_reference", "Advanced branch with 0.75x size on top-ATR days.", 0.75, None),
        (
            "advanced_high_atr_0p75_thu_fri_0p75_union",
            "Advanced branch with 0.75x size when either top-ATR or Thu/Fri applies.",
            0.75,
            0.75,
        ),
        (
            "advanced_high_atr_0p75_thu_fri_0p85_mul",
            "Advanced branch with 0.75x on top-ATR days and an extra 0.85x multiplier on Thu/Fri.",
            0.75,
            0.85,
        ),
        (
            "advanced_high_atr_0p75_thu_fri_0p75_mul",
            "Advanced branch with 0.75x on top-ATR days and an extra 0.75x multiplier on Thu/Fri.",
            0.75,
            0.75,
        ),
    ]

    ranked = []
    for name, rule, atr_weight, weekday_weight in variant_specs:
        session_weights = pd.Series(1.0, index=trade_dates, dtype=float)
        session_weights.loc[high_atr_mask.fillna(False)] = float(atr_weight)
        if weekday_weight is not None:
            if name.endswith("_union"):
                union_idx = pd.Index(pd.Index(prior_day_atr14.index[high_atr_mask.fillna(False)]).union(thu_fri_dates))
                session_weights.loc[union_idx] = float(min(atr_weight, weekday_weight))
            else:
                session_weights.loc[thu_fri_dates] = session_weights.loc[thu_fri_dates] * float(weekday_weight)
        weighted_trades = _apply_session_weights(advanced_trades, session_weights)
        ranked.append(
            _variant_payload(
                name,
                rule,
                weighted_trades,
                trade_dates,
                {
                    "tier2a_management": asdict(tier2a_management),
                    "tier3_short_management": asdict(tier3_management),
                    "switch_dates": {"last_contract_day": True, "friday": True},
                    "roc_agreement_bars": 5,
                    "ATR_Length": 10,
                    "NumDaysToConsiderPreviousContractMARange": 2,
                    "atr_weekday_sizing": {
                        "top_atr_weight": atr_weight,
                        "thu_fri_weight": weekday_weight,
                    },
                },
            )
        )

    ranked.sort(
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
    best_weights = pd.Series(1.0, index=trade_dates, dtype=float)
    best_weights.loc[high_atr_mask.fillna(False)] = float(best["params"]["atr_weekday_sizing"]["top_atr_weight"])
    weekday_weight = best["params"]["atr_weekday_sizing"]["thu_fri_weight"]
    if weekday_weight is not None:
        if best["name"].endswith("_union"):
            union_idx = pd.Index(pd.Index(prior_day_atr14.index[high_atr_mask.fillna(False)]).union(thu_fri_dates))
            best_weights.loc[union_idx] = float(min(best["params"]["atr_weekday_sizing"]["top_atr_weight"], weekday_weight))
        else:
            best_weights.loc[thu_fri_dates] = best_weights.loc[thu_fri_dates] * float(weekday_weight)
    best_trades = _apply_session_weights(advanced_trades, best_weights)

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
            "Research-only ATR-plus-weekday sizing overlay on the strongest advanced weekday-aware directional branch.",
            "Purpose: check whether the best ATR trim and the softer Thu/Fri tape stack cleanly.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(
        DEFAULT_LEADERBOARD_PATH,
        [_leaderboard_row(variant, summary_path) for variant in ranked],
    )


if __name__ == "__main__":
    main()
