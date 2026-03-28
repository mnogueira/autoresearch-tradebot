from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_macro_followups import compute_adx
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_high_adx_followups_20260328")


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active)

    return allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    daily_wdo = (
        dataset.bars_m1.assign(session_date=pd.to_datetime(dataset.bars_m1["session_date"]).dt.normalize())
        .groupby("session_date")
        .agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    )
    daily_adx = compute_adx(daily_wdo, period=14).shift(1)

    def adx_filter(threshold: float) -> Callable[[dict[str, Any]], bool]:
        def allow(context: dict[str, Any]) -> bool:
            session = pd.Timestamp(context["session_date"]).normalize()
            value = float(daily_adx.get(session, np.nan))
            return bool(np.isfinite(value) and value > float(threshold))

        return allow

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )
    _, adx25_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, adx_filter(25.0)),
        management=cooldown_management,
    )
    _, adx30_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, adx_filter(30.0)),
        management=cooldown_management,
    )

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m",
            "metrics": reference_metrics,
        },
        "adx_gt_25_variant": {
            "rule": "Prior-day daily ADX(14) must be above 25.",
            "metrics": adx25_metrics,
        },
        "adx_gt_30_variant": {
            "rule": "Prior-day daily ADX(14) must be above 30.",
            "metrics": adx30_metrics,
        },
        "notes": [
            "This isolates the regime-strength idea on the simpler cooldown-only tier instead of the max-hold variant.",
            "The filter uses only prior-day daily information, so it is feasible for live deployment if it proves worth the trade loss.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_daily_adx_gt_30",
            family="session_daily_regime",
            metrics=adx30_metrics,
            notes="Exact session+cooldown winner filtered by prior-day daily ADX(14) > 30.",
            artifact=summary_path,
            params={"daily_adx_period": 14, "daily_adx_threshold": 30.0, "min_minutes_between_entries": 30},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
