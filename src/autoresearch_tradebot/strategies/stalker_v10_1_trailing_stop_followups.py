from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_trailing_stop_followups_20260328")


def _risk_block(trades, trade_dates) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    trailing_trades, trailing_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            atr_trailing_activation_fraction=0.5,
            atr_trailing_distance_mult=2.0,
        ),
    )

    summary = {
        "reference_tier2_cooldown_only": {
            "metrics": reference_metrics,
            **_risk_block(reference_trades, dataset.trade_dates),
        },
        "atr_trailing_after_half_target_2x_atr": {
            "metrics": trailing_metrics,
            **_risk_block(trailing_trades, dataset.trade_dates),
            "rule": "After price reaches 50% of TP distance, trail the stop by 2.0 x entry ATR14.",
        },
        "notes": [
            "This is an exact every-tick rerun of Tier 2 with an ATR-based trailing stop that stays inactive until half the target has been reached.",
            "The baseline remains the plain session winner plus 30-minute cooldown only.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
