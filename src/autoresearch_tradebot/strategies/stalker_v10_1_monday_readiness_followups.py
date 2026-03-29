from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Callable

import numpy as np
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
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_monday_readiness_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, float]:
    metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    def _finite(value: float) -> float:
        numeric = float(value)
        return numeric if np.isfinite(numeric) else 0.0
    return {
        "sortino_ratio": _finite(metrics["sortino_ratio"]),
        "calmar_ratio": _finite(metrics["calmar_ratio"]),
        "omega_ratio": _finite(metrics["omega_ratio"]),
        "sortino_weighted_composite": _finite(_composite_score(metrics)),
    }


def _entry_filter_from_mask(mask: np.ndarray) -> Callable[[dict[str, Any]], bool]:
    def _filter(entry_context: dict[str, Any]) -> bool:
        dataset_index = int(entry_context["dataset_index"])
        if dataset_index < 0 or dataset_index >= len(mask):
            return False
        return bool(mask[dataset_index])

    return _filter


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    bars = dataset.bars_m1
    trade_dates = dataset.trade_dates
    recent_5d_dates = trade_dates[-5:]

    base_params = session_winner_params()
    session_hours = {10, 11, 12, 14}
    base_filter = session_filter(session_hours)
    cooldown_only = ManagementConfig(min_minutes_between_entries=30)
    cooldown_maxhold = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)
    spread_guard_cooldown = ManagementConfig(min_minutes_between_entries=30, max_entry_spread_ticks=1)

    baseline_trades, baseline_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=cooldown_only,
    )
    spread_guard_trades, spread_guard_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=spread_guard_cooldown,
    )
    maxhold_recent_trades, maxhold_recent_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=recent_5d_dates,
        entry_filter=base_filter,
        management=cooldown_maxhold,
    )
    cooldown_recent_trades, cooldown_recent_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=recent_5d_dates,
        entry_filter=base_filter,
        management=cooldown_only,
    )

    atr_current = pd.Series(dataset.get_atr_current(base_params.ATR_Length), index=bars.index, dtype=float)
    atr_mean_20 = atr_current.rolling(20, min_periods=20).mean().shift(1)
    atr_current_values = atr_current.to_numpy(dtype=float)
    atr_mean_values = atr_mean_20.to_numpy(dtype=float)
    atr_expansion_mask = (
        atr_current_values > (1.5 * atr_mean_values)
    ) & np.isfinite(atr_current_values) & np.isfinite(atr_mean_values)
    vol_breakout_params = replace(
        base_params,
        ApplyTrendEfficiencyFilterToLongs=False,
        ApplyTrendEfficiencyFilterToShorts=False,
    )
    vol_breakout_trades, vol_breakout_metrics = run_backtest_with_management(
        dataset=dataset,
        params=vol_breakout_params,
        trade_dates=trade_dates,
        entry_filter=lambda ctx: base_filter(ctx) and _entry_filter_from_mask(atr_expansion_mask)(ctx),
        management=cooldown_only,
    )

    first_trade_trades, first_trade_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=lambda ctx: base_filter(ctx) and int(ctx["next_trade_number"]) == 1,
        management=cooldown_only,
    )

    ema50 = bars["Close"].ewm(span=50, adjust=False).mean().shift(1).to_numpy(dtype=float)
    close_values = bars["Close"].to_numpy(dtype=float)

    def ema50_filter(entry_context: dict[str, Any]) -> bool:
        if not base_filter(entry_context):
            return False
        dataset_index = int(entry_context["dataset_index"])
        direction = int(entry_context["direction"])
        price = float(close_values[dataset_index])
        ema_value = float(ema50[dataset_index])
        if not np.isfinite(price) or not np.isfinite(ema_value):
            return False
        return (direction == 1 and price > ema_value) or (direction == -1 and price < ema_value)

    ema50_trades, ema50_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=ema50_filter,
        management=cooldown_only,
    )

    summary = {
        "baseline_session_cooldown": {
            "metrics": baseline_metrics,
            "risk_adjusted_metrics": _risk_block(baseline_trades, trade_dates),
        },
        "spread_guard_1tick_session_cooldown": {
            "metrics": spread_guard_metrics,
            "risk_adjusted_metrics": _risk_block(spread_guard_trades, trade_dates),
            "notes": [
                "Historical spread never exceeded 1 tick at entry, so this is expected to tie the baseline.",
            ],
        },
        "volatility_breakout_session_cooldown": {
            "metrics": vol_breakout_metrics,
            "risk_adjusted_metrics": _risk_block(vol_breakout_trades, trade_dates),
            "notes": [
                "Replaces the trend-efficiency gate with ATR expansion > 1.5x its trailing 20-bar average.",
            ],
        },
        "first_trade_of_day_session_cooldown": {
            "metrics": first_trade_metrics,
            "risk_adjusted_metrics": _risk_block(first_trade_trades, trade_dates),
        },
        "ema50_direction_filter_session_cooldown": {
            "metrics": ema50_metrics,
            "risk_adjusted_metrics": _risk_block(ema50_trades, trade_dates),
            "notes": [
                "Only trade long above the lagged EMA50 and short below it.",
            ],
        },
        "recent_5d": {
            "start_date": pd.Timestamp(recent_5d_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(recent_5d_dates[-1]).date().isoformat(),
            "session_cooldown_only": {
                "metrics": cooldown_recent_metrics,
                "risk_adjusted_metrics": _risk_block(cooldown_recent_trades, recent_5d_dates),
            },
            "session_cooldown_maxhold120": {
                "metrics": maxhold_recent_metrics,
                "risk_adjusted_metrics": _risk_block(maxhold_recent_trades, recent_5d_dates),
            },
        },
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_cooldown_volatility_breakout_atr_expansion_1p5x",
            family="session_signal_family",
            metrics=vol_breakout_metrics,
            notes="Session + cooldown using ATR expansion > 1.5x its 20-bar average instead of the trend-efficiency gate.",
            artifact=summary_path,
            params={"atr_expansion_multiple": 1.5, "atr_mean_window": 20, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_first_trade_of_day",
            family="session_trade_frequency",
            metrics=first_trade_metrics,
            notes="Session + cooldown taking only the first qualified trade of each day.",
            artifact=summary_path,
            params={"first_trade_only": True, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_ema50_direction_filter",
            family="session_trend_filter",
            metrics=ema50_metrics,
            notes="Session + cooldown with a lagged EMA50 direction filter: long above EMA50, short below EMA50.",
            artifact=summary_path,
            params={"ema_period": 50, "min_minutes_between_entries": 30},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
