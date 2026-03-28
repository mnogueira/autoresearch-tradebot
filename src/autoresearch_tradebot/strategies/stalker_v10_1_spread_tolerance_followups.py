from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import _composite_score, _daily_pnl_from_trades, _risk_adjusted_metrics
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_python import PRICE_TICK_SIZE
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_spread_tolerance_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "sortino_ratio": float(metrics["sortino_ratio"]),
        "calmar_ratio": float(metrics["calmar_ratio"]),
        "omega_ratio": float(metrics["omega_ratio"]),
        "sortino_weighted_composite": float(_composite_score(metrics)),
    }


def _spread_sweep(
    dataset: V10Dataset,
    params,
    trade_dates: pd.Index,
    entry_filter,
    management: ManagementConfig,
    fixed_spreads: list[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spread_ticks in fixed_spreads:
        run_management = replace(management, fixed_spread_ticks=int(spread_ticks), spread_multiplier=1.0)
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=run_management,
        )
        risk = _risk_block(trades, trade_dates)
        rows.append(
            {
                "fixed_spread_ticks": int(spread_ticks),
                "metrics": metrics,
                "risk_adjusted_metrics": risk,
                "profitable": bool(float(metrics["net_profit_brl"]) > 0.0),
            }
        )
    return rows


def _max_profitable_spread(rows: list[dict[str, Any]]) -> int | None:
    profitable_ticks = [int(row["fixed_spread_ticks"]) for row in rows if bool(row["profitable"])]
    return max(profitable_ticks) if profitable_ticks else None


def _min_profit_filter_summary(trades: pd.DataFrame) -> dict[str, Any]:
    threshold_points = 2.0 * float(PRICE_TICK_SIZE)
    winning = trades.loc[trades["pnl_points"].astype(float) > 0.0].copy()
    survivors = winning.loc[winning["pnl_points"].astype(float) > threshold_points].copy()
    return {
        "threshold_ticks": 2,
        "threshold_points": round(threshold_points, 4),
        "total_trades": int(len(trades)),
        "winning_trades": int(len(winning)),
        "winning_trades_above_threshold": int(len(survivors)),
        "share_of_all_trades_pct": round((len(survivors) / len(trades)) * 100.0, 2) if len(trades) else 0.0,
        "share_of_wins_pct": round((len(survivors) / len(winning)) * 100.0, 2) if len(winning) else 0.0,
        "gross_winning_pnl_brl": round(float(winning["pnl_brl"].sum()), 2) if len(winning) else 0.0,
        "gross_winning_pnl_brl_above_threshold": round(float(survivors["pnl_brl"].sum()), 2) if len(survivors) else 0.0,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})

    cooldown_management = ManagementConfig(min_minutes_between_entries=30)
    maxhold_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)
    cooldown_spread_guard_management = ManagementConfig(min_minutes_between_entries=30, max_entry_spread_ticks=1)
    fixed_spreads = [2, 3, 4, 5]

    cooldown_trades, cooldown_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )
    maxhold_trades, maxhold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=maxhold_management,
    )
    cooldown_spread_guard_trades, cooldown_spread_guard_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=cooldown_spread_guard_management,
    )

    cooldown_tp42_params = replace(params, TP_ATRMultiplier=0.42)
    cooldown_tp48_params = replace(params, TP_ATRMultiplier=0.48)
    cooldown_tp42_trades, cooldown_tp42_metrics = run_backtest_with_management(
        dataset=dataset,
        params=cooldown_tp42_params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )
    cooldown_tp48_trades, cooldown_tp48_metrics = run_backtest_with_management(
        dataset=dataset,
        params=cooldown_tp48_params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )

    cooldown_sweep = _spread_sweep(dataset, params, trade_dates, entry_filter, cooldown_management, fixed_spreads)
    maxhold_sweep = _spread_sweep(dataset, params, trade_dates, entry_filter, maxhold_management, fixed_spreads)
    cooldown_tp42_sweep = _spread_sweep(dataset, cooldown_tp42_params, trade_dates, entry_filter, cooldown_management, fixed_spreads)
    cooldown_tp48_sweep = _spread_sweep(dataset, cooldown_tp48_params, trade_dates, entry_filter, cooldown_management, fixed_spreads)

    summary = {
        "baseline_variants": {
            "tier2_cooldown_only": {
                "metrics": cooldown_metrics,
                "risk_adjusted_metrics": _risk_block(cooldown_trades, trade_dates),
                "min_profit_filter_gt_2_ticks": _min_profit_filter_summary(cooldown_trades),
            },
            "tier3_cooldown_plus_maxhold120": {
                "metrics": maxhold_metrics,
                "risk_adjusted_metrics": _risk_block(maxhold_trades, trade_dates),
                "min_profit_filter_gt_2_ticks": _min_profit_filter_summary(maxhold_trades),
            },
            "tier2_cooldown_only_spread_guard_1tick": {
                "metrics": cooldown_spread_guard_metrics,
                "risk_adjusted_metrics": _risk_block(cooldown_spread_guard_trades, trade_dates),
                "min_profit_filter_gt_2_ticks": _min_profit_filter_summary(cooldown_spread_guard_trades),
            },
            "tier2_cooldown_tp_0p42": {
                "metrics": cooldown_tp42_metrics,
                "risk_adjusted_metrics": _risk_block(cooldown_tp42_trades, trade_dates),
                "min_profit_filter_gt_2_ticks": _min_profit_filter_summary(cooldown_tp42_trades),
            },
            "tier2_cooldown_tp_0p48": {
                "metrics": cooldown_tp48_metrics,
                "risk_adjusted_metrics": _risk_block(cooldown_tp48_trades, trade_dates),
                "min_profit_filter_gt_2_ticks": _min_profit_filter_summary(cooldown_tp48_trades),
            },
        },
        "fixed_spread_sweeps": {
            "tier2_cooldown_only": {
                "rows": cooldown_sweep,
                "max_profitable_integer_spread_ticks": _max_profitable_spread(cooldown_sweep),
            },
            "tier3_cooldown_plus_maxhold120": {
                "rows": maxhold_sweep,
                "max_profitable_integer_spread_ticks": _max_profitable_spread(maxhold_sweep),
            },
            "tier2_cooldown_tp_0p42": {
                "rows": cooldown_tp42_sweep,
                "max_profitable_integer_spread_ticks": _max_profitable_spread(cooldown_tp42_sweep),
            },
            "tier2_cooldown_tp_0p48": {
                "rows": cooldown_tp48_sweep,
                "max_profitable_integer_spread_ticks": _max_profitable_spread(cooldown_tp48_sweep),
            },
        },
        "notes": [
            "This pass measures exact-engine spread tolerance using a literal fixed spread of 2, 3, 4, or 5 ticks on every bar.",
            "Tier 2 and Tier 3 are both included because Monday operations may upgrade from the validated MT5 base into Tier 2 before ever using Tier 3.",
            "The wider TP variants are tested on the simpler cooldown stack to see whether larger targets improve spread resilience enough to matter operationally.",
            "The minimum-profit filter is diagnostic only; it shows how many winning trades exceed a gross 2-tick move before costs.",
            "The 1-tick spread guard uses the cached historical spread and is mainly a live execution safeguard; it is not expected to create new backtest alpha.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="tier2_cooldown_only_spread_guard_1tick",
            family="session_spread_guard",
            metrics=cooldown_spread_guard_metrics,
            notes="Session winner + 30m cooldown only, with an entry spread guard that blocks new trades above 1 tick. Historical tape is mostly 0-1 ticks, so this is mainly a live safeguard.",
            artifact=summary_path,
            params={"max_entry_spread_ticks": 1, "min_minutes_between_entries": 30, "max_bars_in_trade": None},
        ),
        candidate_row(
            name="tier2_cooldown_only_tp0p42",
            family="session_take_profit_extension",
            metrics=cooldown_tp42_metrics,
            notes="Session winner + 30m cooldown only, with TP widened to 0.42 ATR. Added for spread-resilience comparison.",
            artifact=summary_path,
            params={"tp_atr_multiplier": 0.42, "min_minutes_between_entries": 30, "max_bars_in_trade": None},
        ),
        candidate_row(
            name="tier2_cooldown_only_tp0p48",
            family="session_take_profit_extension",
            metrics=cooldown_tp48_metrics,
            notes="Session winner + 30m cooldown only, with TP widened to 0.48 ATR. Added for spread-resilience comparison.",
            artifact=summary_path,
            params={"tp_atr_multiplier": 0.48, "min_minutes_between_entries": 30, "max_bars_in_trade": None},
        ),
        candidate_row(
            name="tier2_cooldown_only_fixed_spread_5ticks",
            family="session_stress_test",
            metrics=next(row["metrics"] for row in cooldown_sweep if row["fixed_spread_ticks"] == 5),
            notes="Tier 2 cooldown-only exact variant under a literal fixed 5-tick spread stress.",
            artifact=summary_path,
            params={"fixed_spread_ticks": 5, "min_minutes_between_entries": 30, "max_bars_in_trade": None},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
