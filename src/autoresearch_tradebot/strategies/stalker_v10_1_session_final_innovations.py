from __future__ import annotations

import json

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
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_final_innovations_20260328")


def _aggregate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.resample("15min", label="left", closed="left").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    ).dropna(subset=["Open", "High", "Low", "Close"])


def build_m30_direction_by_index(dataset: V10Dataset) -> np.ndarray:
    m15 = _aggregate_ohlcv(dataset.bars_m1)
    m30 = m15.resample("30min", label="left", closed="left").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    ).dropna(subset=["Open", "High", "Low", "Close"])
    direction = np.sign(m30["Close"] - m30["Open"]).astype(int)
    availability = pd.DataFrame(
        {
            "available_time": direction.index + pd.Timedelta(minutes=30),
            "m30_direction": direction.to_numpy(dtype=int),
        }
    ).sort_values("available_time")
    bars = dataset.bars_m1.reset_index()[["time"]].sort_values("time")
    merged = pd.merge_asof(
        bars,
        availability,
        left_on="time",
        right_on="available_time",
        direction="backward",
    )
    return merged["m30_direction"].fillna(0).astype(int).to_numpy()


def combined_filter(base_hours: set[int], m30_direction_by_index: np.ndarray) -> callable:
    base = session_filter(base_hours)

    def _filter(context: dict[str, object]) -> bool:
        if not base(context):
            return False
        dataset_index = int(context["dataset_index"])
        direction = int(context["direction"])
        higher_timeframe_direction = int(m30_direction_by_index[dataset_index])
        if direction == 1:
            return higher_timeframe_direction > 0
        if direction == -1:
            return higher_timeframe_direction < 0
        return False

    return _filter


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    allowed_hours = {10, 11, 12, 14}
    base_filter = session_filter(allowed_hours)
    base_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    train_dates, test_dates = split_dates(dataset.trade_dates, 0.7)
    _, train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=base_filter,
        management=base_management,
    )
    _, test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    m30_direction_by_index = build_m30_direction_by_index(dataset)
    m30_filter = combined_filter(allowed_hours, m30_direction_by_index)
    _, m30_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=m30_filter,
        management=base_management,
    )

    tp_scale_management = ManagementConfig(
        min_minutes_between_entries=30,
        max_bars_in_trade=120,
        win_streak_threshold=3,
        tp_scale_after_win_streak=0.10,
    )
    _, tp_scale_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=tp_scale_management,
    )

    _, combined_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=m30_filter,
        management=tp_scale_management,
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "walkforward_70_30": {
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
        },
        "m30_confirmation_variant": {
            "rule": "Entry direction must agree with the latest completed M30 candle direction built from aggregated M15 bars.",
            "metrics": m30_metrics,
        },
        "tp_scaling_variant": {
            "rule": "After three consecutive wins, increase TP by 10% for the next eligible trade while keeping SL fixed.",
            "metrics": tp_scale_metrics,
        },
        "combined_m30_and_tp_scaling_variant": {
            "rule": "Require M30 agreement and apply the 10% TP scale after a three-win streak.",
            "metrics": combined_metrics,
        },
        "notes": [
            "The walk-forward repeats the exact 70/30 split on the current max-hold leader for a final confirmation pass.",
            "M30 confirmation uses M15 bars aggregated inside the script, then promotes a completed 30-minute candle direction into the M1 exact engine as an entry filter.",
            "TP scaling is intentionally conservative: SL remains fixed and only the TP multiplier is increased by 10% after a win streak of three or more trades.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_m30_confirmation",
            family="session_multitimeframe_confirmation",
            metrics=m30_metrics,
            notes="Exact max-hold leader with M30 direction confirmation from aggregated M15 bars.",
            artifact=summary_path,
            params={"m30_confirmation": "completed_m30_direction_from_m15"},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_tp_scale_after_3wins",
            family="session_tp_scaling",
            metrics=tp_scale_metrics,
            notes="Exact max-hold leader with TP scaled +10% after a three-win streak.",
            artifact=summary_path,
            params={"win_streak_threshold": 3, "tp_scale_after_win_streak": 0.10},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_m30_confirmation_tp_scale",
            family="session_multitimeframe_tp_scaling",
            metrics=combined_metrics,
            notes="Exact max-hold leader with both M30 confirmation and TP scaling after a three-win streak.",
            artifact=summary_path,
            params={
                "m30_confirmation": "completed_m30_direction_from_m15",
                "win_streak_threshold": 3,
                "tp_scale_after_win_streak": 0.10,
            },
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
