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
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_trend_window_sweep_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    management = ManagementConfig(min_minutes_between_entries=30)

    windows = [5, 10, 15, 20, 25]
    results: dict[str, dict[str, object]] = {}
    leaderboard_rows: list[dict[str, object]] = []

    for window in windows:
        params = replace(base_params, TrendEfficiencyWindowMinutes=int(window))
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        key = f"trend_window_{window}m"
        results[key] = {
            "window_minutes": int(window),
            "params": {
                "TrendEfficiencyWindowMinutes": int(window),
                "min_minutes_between_entries": 30,
                "allowed_hours": [10, 11, 12, 14],
                "SkipShortWednesday": True,
                "SkipShortHour13": True,
                "SL_ATRMultiplier": float(params.SL_ATRMultiplier),
                "TP_ATRMultiplier": float(params.TP_ATRMultiplier),
            },
            "metrics": metrics,
        }
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_cooldown_30m_trend_window_{window}m",
                family="session_trade_cooldown_trend_window",
                metrics=metrics,
                notes=(
                    "Exact session+cooldown winner with TrendEfficiencyWindowMinutes "
                    f"set to {window}."
                ),
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"TrendEfficiencyWindowMinutes": int(window), "min_minutes_between_entries": 30},
            )
        )

    best_key, best_payload = max(
        results.items(),
        key=lambda item: float(item[1]["metrics"]["on_tester_value"]),
    )
    summary = {
        "reference_variant": "session_winner_cooldown_30m",
        "results": results,
        "best_variant": {
            "name": best_key,
            "window_minutes": int(best_payload["window_minutes"]),
            "metrics": best_payload["metrics"],
        },
        "notes": [
            "This sweep keeps the current exact session winner intact and only changes TrendEfficiencyWindowMinutes.",
            "All variants use the same session filter, cooldown, short-Wednesday filter, short-hour-13 filter, and SL/TP.",
            "Ranking is based on the exact on_tester_value from the every-tick parity engine.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
