from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_signal_followups_20260328")


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
    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    bars = dataset.bars_m1
    session_key = bars["session_date"]
    close_values = bars["Close"]
    volume_values = bars["Volume"].astype(float)
    volume_ma20 = volume_values.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(20, min_periods=5).mean()
    )
    roc10 = close_values.groupby(session_key).transform(lambda series: series.pct_change(10))
    roc20 = close_values.groupby(session_key).transform(lambda series: series.pct_change(20))

    volume_array = volume_values.to_numpy(dtype=float)
    volume_ma20_array = volume_ma20.to_numpy(dtype=float)
    roc10_array = roc10.to_numpy(dtype=float)
    roc20_array = roc20.to_numpy(dtype=float)

    def make_volume_confirmation_filter(multiplier: float) -> Callable[[dict[str, Any]], bool]:
        def allow(context: dict[str, Any]) -> bool:
            index = int(context["dataset_index"])
            baseline = float(volume_ma20_array[index])
            return bool(np.isfinite(baseline) and volume_array[index] > (float(multiplier) * baseline))

        return allow

    def make_roc_filter(values: np.ndarray) -> Callable[[dict[str, Any]], bool]:
        def allow(context: dict[str, Any]) -> bool:
            index = int(context["dataset_index"])
            roc_value = float(values[index])
            if not np.isfinite(roc_value):
                return False
            direction = int(context["direction"])
            return roc_value > 0.0 if direction == 1 else roc_value < 0.0

        return allow

    def skip_first_15m_of_allowed_session(context: dict[str, Any]) -> bool:
        timestamp = context["timestamp"]
        return not (int(timestamp.hour) == 10 and int(timestamp.minute) < 15)

    summary: dict[str, Any] = {
        "reference_variant": "session_winner_cooldown_30m",
        "notes": [
            "The requested 09:15 opening-auction gap filter is a structural no-op for the current session winner because the strategy already starts evaluating entries at 10:00.",
            "A practical analog is included here: skip the first 15 minutes of the allowed 10:00 hour to reduce opening noise inside the current session window.",
            "ROC variants replace the trend-efficiency gate with a simpler directional ROC sign check while keeping the proven session, cooldown, timing, and short-side volume structure.",
        ],
    }
    leaderboard_rows: list[dict[str, Any]] = []

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )
    summary["reference"] = reference_metrics

    volume_filter = combine_filters(base_filter, make_volume_confirmation_filter(1.5))
    _, volume_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=volume_filter,
        management=cooldown_management,
    )
    summary["volume_confirmation_1p5x_avg20"] = {
        "rule": "Current M1 bar volume must exceed 1.5x the prior 20-bar session rolling average.",
        "metrics": volume_metrics,
    }
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_volume_gt_1p5x_avg20",
            family="session_volume_confirmation",
            metrics=volume_metrics,
            notes="Exact session+cooldown winner with current bar volume > 1.5x prior 20-bar average.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"volume_multiplier": 1.5, "volume_average_bars": 20, "min_minutes_between_entries": 30},
        )
    )

    practical_gap_filter = combine_filters(base_filter, skip_first_15m_of_allowed_session)
    _, gap_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=practical_gap_filter,
        management=cooldown_management,
    )
    summary["session_open_gap_practical_10h15_start"] = {
        "rule": "Practical analog of the requested auction gap: skip entries from 10:00 through 10:14 inside the current allowed session.",
        "metrics": gap_metrics,
    }
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_start_10h15",
            family="session_open_gap",
            metrics=gap_metrics,
            notes="Exact session+cooldown winner but skip the first 15 minutes of the allowed 10:00 hour.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"session_start_hour": 10, "session_start_minute": 15, "min_minutes_between_entries": 30},
        )
    )

    for name, roc_values, window in (
        ("roc10", roc10_array, 10),
        ("roc20", roc20_array, 20),
    ):
        roc_params = replace(
            base_params,
            ApplyTrendEfficiencyFilterToLongs=False,
            ApplyTrendEfficiencyFilterToShorts=False,
        )
        roc_filter = combine_filters(base_filter, make_roc_filter(roc_values))
        _, roc_metrics = run_backtest_with_management(
            dataset=dataset,
            params=roc_params,
            trade_dates=dataset.trade_dates,
            entry_filter=roc_filter,
            management=cooldown_management,
        )
        summary[name] = {
            "rule": f"Replace trend-efficiency confirmation with directional ROC({window}) sign while keeping session, cooldown, and short-side volume rules.",
            "metrics": roc_metrics,
        }
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_cooldown_30m_{name}_directional",
                family="session_roc_directional",
                metrics=roc_metrics,
                notes=f"Exact session+cooldown winner with trend-efficiency replaced by directional ROC({window}) sign.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"roc_bars": int(window), "min_minutes_between_entries": 30},
            )
        )

    _, loss_stop_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_consecutive_losses_per_day=2,
        ),
    )
    summary["max_consecutive_losses_per_day_2"] = {
        "rule": "Stop opening new trades for the session after two consecutive realized losses.",
        "metrics": loss_stop_metrics,
    }
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_stop_after_2_losses",
            family="session_daily_loss_stop",
            metrics=loss_stop_metrics,
            notes="Exact session+cooldown winner with a daily stop after two consecutive losses.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"max_consecutive_losses_per_day": 2, "min_minutes_between_entries": 30},
        )
    )

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
