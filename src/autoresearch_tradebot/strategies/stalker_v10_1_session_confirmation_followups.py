from __future__ import annotations

import json

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_confirmation_followups_20260328")


def trades_per_day(metrics: dict[str, float]) -> float:
    trading_days = float(metrics.get("trading_days", 0.0) or 0.0)
    total_trades = float(metrics.get("total_trades", 0.0) or 0.0)
    if trading_days <= 0.0:
        return 0.0
    return round(total_trades / trading_days, 4)


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    reference_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)
    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=reference_management,
    )

    confirmation_management = ManagementConfig(
        min_minutes_between_entries=30,
        max_bars_in_trade=120,
        confirmation_candle_required=True,
        confirmation_wait_bars=1,
    )
    _, confirmation_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=confirmation_management,
    )

    profit_lock_management = ManagementConfig(
        min_minutes_between_entries=30,
        max_bars_in_trade=120,
        profit_lock_activation_fraction=0.75,
        profit_lock_target_fraction=0.25,
    )
    _, profit_lock_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=profit_lock_management,
    )

    _, combined_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            confirmation_candle_required=True,
            confirmation_wait_bars=1,
            profit_lock_activation_fraction=0.75,
            profit_lock_target_fraction=0.25,
        ),
    )

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m_maxhold120",
            "metrics": reference_metrics,
            "expected_trades_per_day": trades_per_day(reference_metrics),
        },
        "confirmation_candle_variant": {
            "rule": "After a valid signal, wait for the next candle to close in the same direction and then enter at the following bar open.",
            "metrics": confirmation_metrics,
            "expected_trades_per_day": trades_per_day(confirmation_metrics),
        },
        "profit_lock_variant": {
            "rule": "Once price reaches 75% of TP, move the stop to lock 25% of TP and leave the original TP in place.",
            "metrics": profit_lock_metrics,
            "expected_trades_per_day": trades_per_day(profit_lock_metrics),
        },
        "combined_confirmation_and_profit_lock": {
            "rule": "Require the confirmation candle and apply the 75%/25% profit-lock rule.",
            "metrics": combined_metrics,
            "expected_trades_per_day": trades_per_day(combined_metrics),
        },
        "notes": [
            "The confirmation candle variant is an exact-engine experiment, not a bar-prototype proxy.",
            "The profit-lock rule is intentionally static: once activated, it raises the stop to a fixed profit lock instead of turning into a continuously trailing stop.",
            "Expected trades per day are computed directly from total trades divided by trading days for each exact variant.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_confirmation_candle",
            family="session_confirmation_entry",
            metrics=confirmation_metrics,
            notes="Exact production candidate with a one-candle directional confirmation before entry.",
            artifact=summary_path,
            params={"confirmation_wait_bars": 1},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_profit_lock_75_25",
            family="session_profit_lock",
            metrics=profit_lock_metrics,
            notes="Exact production candidate with a 75% activation / 25% TP profit lock stop.",
            artifact=summary_path,
            params={"profit_lock_activation_fraction": 0.75, "profit_lock_target_fraction": 0.25},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_confirmation_profit_lock",
            family="session_confirmation_profit_lock",
            metrics=combined_metrics,
            notes="Exact production candidate with both one-candle confirmation and the 75%/25% profit lock.",
            artifact=summary_path,
            params={
                "confirmation_wait_bars": 1,
                "profit_lock_activation_fraction": 0.75,
                "profit_lock_target_fraction": 0.25,
            },
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
