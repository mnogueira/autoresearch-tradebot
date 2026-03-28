from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_python import run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_deployment_followups_20260328")


def apply_recent_entry_density_sizing(
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    lookback_minutes: int,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    if trades.empty:
        empty_metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return pd.DataFrame(), empty_metrics, {"lookback_minutes": int(lookback_minutes), "avg_size_multiplier": 0.0}

    frame = trades.copy()
    frame["entry_time"] = pd.to_datetime(frame["entry_time"])
    frame = frame.sort_values("entry_time").reset_index(drop=True)

    window = pd.Timedelta(minutes=int(lookback_minutes))
    recent_entries: deque[pd.Timestamp] = deque()
    size_multipliers: list[float] = []
    for entry_time in frame["entry_time"]:
        while recent_entries and recent_entries[0] < entry_time - window:
            recent_entries.popleft()
        recent_count = len(recent_entries) + 1
        size_multiplier = 1.0 / float(recent_count)
        size_multipliers.append(size_multiplier)
        recent_entries.append(entry_time)

    frame["size_multiplier"] = size_multipliers
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["size_multiplier"]
    frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["size_multiplier"]
    metrics = calculate_metrics(frame, trade_dates)
    stats = {
        "lookback_minutes": int(lookback_minutes),
        "avg_size_multiplier": round(float(frame["size_multiplier"].mean()), 4),
        "min_size_multiplier": round(float(frame["size_multiplier"].min()), 4),
        "max_size_multiplier": round(float(frame["size_multiplier"].max()), 4),
    }
    return frame, metrics, stats


def analysis_candidate_row(
    name: str,
    family: str,
    metrics: dict[str, Any],
    notes: str,
    artifact: Path,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = candidate_row(name=name, family=family, metrics=metrics, notes=notes, artifact=artifact, params=params)
    row["comparison_tier"] = "analysis"
    row["screening_method"] = "session_deployment_followup"
    return row


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    reference_trades, reference_metrics = run_backtest(
        dataset,
        params,
        dataset.trade_dates,
        entry_filter=entry_filter,
    )
    cooldown_session_trades, cooldown_session_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )
    cooldown_no_session_trades, cooldown_no_session_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=None,
        management=cooldown_management,
    )
    timed_exit_trades, timed_exit_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            profitable_trail_start_bars=15,
            profitable_trail_step_bars=10,
            profitable_trail_step_ticks=1,
        ),
    )
    sized_trades, sized_metrics, sized_stats = apply_recent_entry_density_sizing(
        trades=cooldown_session_trades,
        trade_dates=dataset.trade_dates,
        lookback_minutes=60,
    )

    train_dates, test_dates = split_dates(dataset.trade_dates, 0.7)
    _, cooldown_train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )
    _, cooldown_test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=entry_filter,
        management=cooldown_management,
    )

    summary = {
        "reference_session_winner": {
            "name": "session_winner_hours_10_11_12_14_sl0p84_tp0p30",
            "metrics": reference_metrics,
        },
        "cooldown_comparison": {
            "cooldown_30m_with_session_filter": cooldown_session_metrics,
            "cooldown_30m_without_session_filter": cooldown_no_session_metrics,
        },
        "recent_signal_density_sizing": {
            "base_variant": "cooldown_30m_with_session_filter",
            "sizing_rule": "size = 1 / recent_filled_entries_within_60m",
            "implementability_note": "Analysis-only overlay at the 1-contract baseline because it assumes fractional scaling.",
            "stats": sized_stats,
            "metrics": sized_metrics,
        },
        "time_weighted_exit": {
            "base_variant": "cooldown_30m_with_session_filter",
            "rule": "After 15 bars, if profitable, trail stop to breakeven plus 0.5 every 10 bars (tick-aligned approximation of 0.05 per bar).",
            "metrics": timed_exit_metrics,
        },
        "walkforward_70_30": {
            "base_variant": "cooldown_30m_with_session_filter",
            "train_ratio": 0.7,
            "train_metrics": cooldown_train_metrics,
            "test_metrics": cooldown_test_metrics,
        },
        "notes": [
            "The cooldown variant already includes the exact 10:00, 11:00, 12:00, and 14:00 session filter.",
            "Cooldown without the session filter is included here only to show whether the session scheduling still adds value once entries are throttled.",
            "The time-weighted exit is implemented in the exact every-tick engine with tick-size-aware stop increments.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    cooldown_session_trades.to_csv(DEFAULT_OUTPUT_DIR / "cooldown_session_trades.csv", index=False)
    timed_exit_trades.to_csv(DEFAULT_OUTPUT_DIR / "timed_exit_trades.csv", index=False)
    sized_trades.to_csv(DEFAULT_OUTPUT_DIR / "cooldown_density_sized_trades.csv", index=False)

    leaderboard_rows: list[dict[str, Any]] = [
        candidate_row(
            name="session_winner_cooldown_30m_no_session_filter",
            family="session_trade_cooldown",
            metrics=cooldown_no_session_metrics,
            notes="Exact 30-minute fill cooldown applied without the exact 10/11/12/14 session filter, for comparison against the session-filtered cooldown winner.",
            artifact=summary_path,
            params={"min_minutes_between_entries": 30, "session_filter_hours": None},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_timed_exit_profittrail",
            family="session_time_weighted_exit",
            metrics=timed_exit_metrics,
            notes="Exact cooldown variant with a profitable-trade stop ratchet: after 15 bars, trail to breakeven plus one tick every 10 bars.",
            artifact=summary_path,
            params={
                "min_minutes_between_entries": 30,
                "profitable_trail_start_bars": 15,
                "profitable_trail_step_bars": 10,
                "profitable_trail_step_ticks": 1,
            },
        ),
        analysis_candidate_row(
            name="session_winner_cooldown_30m_recent_entry_density_sizing_60m",
            family="session_position_sizing_overlay",
            metrics=sized_metrics,
            notes="Post-trade analysis overlay on the exact cooldown trade tape: size = 1 / recent filled entries within 60 minutes.",
            artifact=summary_path,
            params=sized_stats,
        ),
        candidate_row(
            name="session_winner_cooldown_30m_holdout_70_30",
            family="session_walkforward_holdout",
            metrics=cooldown_test_metrics,
            notes="Held-out last-30% exact test for the 30-minute cooldown session winner after fixing the rule on the first 70% of dates.",
            artifact=summary_path,
            params={"train_ratio": 0.7},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
