from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_recent_tiers_followup_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    recent_trade_dates = dataset.trade_dates[-30:]
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    _, session_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(),
    )
    _, cooldown_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    _, full_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    summary = {
        "period": {
            "start_date": pd.Timestamp(recent_trade_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(recent_trade_dates[-1]).date().isoformat(),
            "trading_days": int(len(recent_trade_dates)),
        },
        "recent_30d_comparison": {
            "session_only": session_only_metrics,
            "session_plus_cooldown_only": cooldown_only_metrics,
            "session_plus_cooldown_plus_maxhold120": full_metrics,
        },
        "notes": [
            "This is the operator-focused recent-tape comparison for deciding whether the simpler cooldown-only refinement should be preferred over the max-hold refinement for Monday.",
            "All three variants use the same exact session winner parameters and only differ in the management overlay.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
