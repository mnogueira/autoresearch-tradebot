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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_hot_hand_followup_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    reference_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=reference_management,
    )

    _, hot_hand_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            recent_trade_pnl_lookback=10,
            min_recent_trade_pnl_brl=0.0,
        ),
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
        "reference_metrics": reference_metrics,
        "hot_hand_filter": {
            "rule": "Only allow new entries once the trailing 10 closed trades sum to a strictly positive PnL.",
            "metrics": hot_hand_metrics,
        },
        "notes": [
            "The hot-hand gate is inactive until at least 10 trades have closed.",
            "The trailing PnL filter is applied on realized closed-trade PnL only, so it never looks ahead.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(
        DEFAULT_LEADERBOARD_PATH,
        [
            candidate_row(
                name="session_winner_cooldown_30m_maxhold120_hot_hand_last10_positive",
                family="session_trade_momentum",
                metrics=hot_hand_metrics,
                notes="Exact production candidate gated by a positive trailing 10-trade realized-PnL sum.",
                artifact=summary_path,
                params={
                    "recent_trade_pnl_lookback": 10,
                    "min_recent_trade_pnl_brl": 0.0,
                    "min_minutes_between_entries": 30,
                    "max_bars_in_trade": 120,
                },
            )
        ],
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
