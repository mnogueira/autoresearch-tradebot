from __future__ import annotations

import json

from dataclasses import replace
from pathlib import Path

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_maxhold_followups_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    maxhold_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=maxhold_management,
    )

    train_dates, test_dates = split_dates(dataset.trade_dates, 0.7)
    _, train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=train_dates,
        entry_filter=base_filter,
        management=maxhold_management,
    )
    _, test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=test_dates,
        entry_filter=base_filter,
        management=maxhold_management,
    )

    _, volatility_hold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=600,
            loss_exit_atr_mult=0.5,
        ),
    )

    _, target_trail_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            trail_after_target_fraction=0.5,
            trail_lock_target_fraction=0.5,
        ),
    )

    max_quality_params = replace(
        base_params,
        SkipWednesday=True,
        SkipShortWednesday=False,
        SkipHour13=True,
        SkipShortHour13=False,
    )
    _, max_quality_v2_metrics = run_backtest_with_management(
        dataset=dataset,
        params=max_quality_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=maxhold_management,
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "walkforward_70_30": {
            "base_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
            "train_ratio": 0.7,
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
        },
        "volatility_based_max_hold_proxy": {
            "rule": "Approximate volatility-based holding logic: hard exit after 600 M1 bars or earlier if unrealized loss exceeds 0.5 ATR at entry.",
            "metrics": volatility_hold_metrics,
        },
        "half_target_trailing_variant": {
            "rule": "With the 120-bar max hold, once price reaches 50% of TP, ratchet the stop from the 50% TP floor and trail half of any additional gains.",
            "metrics": target_trail_metrics,
        },
        "maximum_quality_v2": {
            "rule": "Session filter 10/11/12/14 + 30-minute cooldown + 120 M1 max hold + full Wednesday skip + full 13:00 skip.",
            "metrics": max_quality_v2_metrics,
        },
        "notes": [
            "The walk-forward uses the same exact 70/30 split style as the earlier cooldown deployment follow-up, but on the new 120-bar max-hold leader.",
            "The volatility-based hold is a pragmatic proxy, not a fully new theory of exits: it combines an ATR-normalized loss exit with a much looser age limit.",
            "The half-target trailing variant is a ratcheting stop approximation designed to test whether the max-hold winner benefits from letting profits breathe after mid-target confirmation.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_time_exit_120m1bars_half_target_trail",
            family="session_time_exit",
            metrics=target_trail_metrics,
            notes="Exact session+cooldown+120m max-hold winner with a half-target stop ratchet/trail.",
            artifact=summary_path,
            params={"max_bars_in_trade": 120, "trail_after_target_fraction": 0.5, "trail_lock_target_fraction": 0.5},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_atr_loss_0p5_age_600m1bars",
            family="session_volatility_hold",
            metrics=volatility_hold_metrics,
            notes="Exact session+cooldown winner with ATR-normalized loss exit at 0.5 ATR and a 600-bar max hold.",
            artifact=summary_path,
            params={"loss_exit_atr_mult": 0.5, "max_bars_in_trade": 600},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_full_wednesday_skip_maxhold120",
            family="session_max_quality_timing",
            metrics=max_quality_v2_metrics,
            notes="Exact maximum-quality v2: session filter, 30m cooldown, 120m max hold, full Wednesday skip, full 13h skip.",
            artifact=summary_path,
            params={"skip_wednesday_all_sides": True, "skip_hour13_all_sides": True, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
