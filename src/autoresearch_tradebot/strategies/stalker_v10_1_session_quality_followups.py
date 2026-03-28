from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_quality_followups_20260328")
STRUCTURE_REFERENCE_PATH = Path(
    "artifacts/outputs/stalker_v10_1_session_structure_followups_20260328/summary.json"
)


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active)

    return allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    cooldown_30m = ManagementConfig(min_minutes_between_entries=30)

    bars = dataset.bars_m1
    session_key = bars["session_date"]
    strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(base_params.TrendEfficiencyWindowMinutes),
        volume_window=int(base_params.VolumeWindowMinutes),
        relative_volume_lookback=int(base_params.RelativeVolumeLookbackDays),
    )
    trend_eff = pd.Series(strength_cache["trend_efficiency_raw"], index=bars.index)
    trend_q75_100 = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(100, min_periods=40).quantile(0.75)
    )
    trend_q25_100 = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(100, min_periods=40).quantile(0.25)
    )
    trend_array = trend_eff.to_numpy(dtype=float)
    trend_q75_100_array = trend_q75_100.to_numpy(dtype=float)
    trend_q25_100_array = trend_q25_100.to_numpy(dtype=float)

    def rolling_strength_filter_100(context: dict[str, Any]) -> bool:
        index = int(context["dataset_index"])
        direction = int(context["direction"])
        value = float(trend_array[index])
        if direction == 1:
            threshold = float(trend_q75_100_array[index])
            return bool(np.isfinite(value) and np.isfinite(threshold) and value >= threshold)
        threshold = float(trend_q25_100_array[index])
        return bool(np.isfinite(value) and np.isfinite(threshold) and value <= threshold)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_30m,
    )

    _, strength_100_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, rolling_strength_filter_100),
        management=cooldown_30m,
    )

    _, adaptive_cooldown_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            cooldown_after_win_minutes=15,
            cooldown_after_loss_minutes=30,
        ),
    )

    max_quality_params = replace(
        base_params,
        SkipWednesday=True,
        SkipShortWednesday=False,
        SkipHour13=True,
        SkipShortHour13=False,
    )
    _, max_quality_metrics = run_backtest_with_management(
        dataset=dataset,
        params=max_quality_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_30m,
    )

    prior_tue_to_thu: dict[str, Any] | None = None
    if STRUCTURE_REFERENCE_PATH.exists():
        payload = json.loads(STRUCTURE_REFERENCE_PATH.read_text(encoding="utf-8"))
        prior_tue_to_thu = payload.get("weekday_trade_subset_analysis", {}).get(
            "exact_tuesday_through_thursday_only_variant"
        )

    summary = {
        "reference_variant": "session_winner_cooldown_30m",
        "reference_metrics": reference_metrics,
        "trend_strength_rolling_100bar_percentile": {
            "rule": "Require long signals to exceed the rolling 100-bar 75th percentile of trend efficiency and short signals to be below the rolling 25th percentile.",
            "metrics": strength_100_metrics,
        },
        "adaptive_cooldown": {
            "rule": "After a winning trade, wait 15 minutes before the next entry. After a losing trade, wait 30 minutes.",
            "metrics": adaptive_cooldown_metrics,
        },
        "maximum_quality_all_sides_timing": {
            "rule": "Session filter 10/11/12/14 + 30-minute cooldown + full Wednesday skip + full 13:00 skip.",
            "metrics": max_quality_metrics,
        },
        "existing_tuesday_through_thursday_exact": prior_tue_to_thu,
        "notes": [
            "The maximum-quality configuration keeps the session filter and 30-minute cooldown, then upgrades the Wednesday restriction from short-only to all sides.",
            "The 13:00 all-sides skip is already structurally enforced by the 10/11/12/14 session filter, but it is still included in the configuration for MT5 preset clarity.",
            "The adaptive cooldown is exit-based, not entry-based: the waiting clock starts when the prior trade closes.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_exit_15m_win_30m_loss",
            family="session_adaptive_cooldown",
            metrics=adaptive_cooldown_metrics,
            notes="Exact session winner with exit-based adaptive cooldown: 15m after wins, 30m after losses.",
            artifact=summary_path,
            params={"cooldown_after_win_minutes": 15, "cooldown_after_loss_minutes": 30},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_strength_gt_rolling75_100bars",
            family="session_signal_strength",
            metrics=strength_100_metrics,
            notes="Exact session+cooldown winner with directional trend-efficiency strength gating against the rolling 100-bar 75th/25th percentile.",
            artifact=summary_path,
            params={"trend_strength_history_bars": 100, "percentile": 0.75, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_full_wednesday_skip",
            family="session_max_quality_timing",
            metrics=max_quality_metrics,
            notes="Exact session+cooldown winner with all-sides Wednesday disabled and 13:00 disabled for preset parity.",
            artifact=summary_path,
            params={"skip_wednesday_all_sides": True, "skip_hour13_all_sides": True, "min_minutes_between_entries": 30},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
