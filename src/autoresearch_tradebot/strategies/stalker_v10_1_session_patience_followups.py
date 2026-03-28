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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_patience_followups_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    base_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    patience_results: list[dict[str, object]] = []
    leaderboard_rows: list[dict[str, object]] = []
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    for retrace_fraction in (0.30, 0.40, 0.50):
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(
                min_minutes_between_entries=30,
                max_bars_in_trade=120,
                patience_pullback_fraction=float(retrace_fraction),
                patience_max_wait_bars=3,
            ),
        )
        patience_results.append(
            {
                "pullback_fraction_of_signal_bar": float(retrace_fraction),
                "max_wait_bars": 3,
                "metrics": metrics,
            }
        )
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_cooldown_30m_maxhold120_patience_{str(retrace_fraction).replace('.', 'p')}_3bars",
                family="session_patience_entry",
                metrics=metrics,
                notes=f"Exact max-hold leader with a patience entry: wait up to 3 bars for a {retrace_fraction:.2f} signal-bar pullback.",
                artifact=summary_path,
                params={"patience_pullback_fraction": float(retrace_fraction), "patience_max_wait_bars": 3},
            )
        )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "patience_pullback_grid": patience_results,
        "notes": [
            "This is an exact-engine approximation of a more patient entry: after the signal fires, wait up to 3 bars for a pullback into a fixed fraction of the signal bar range.",
            "The pullback fraction is measured from the signal bar extreme back toward the opposite side of the signal bar.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
