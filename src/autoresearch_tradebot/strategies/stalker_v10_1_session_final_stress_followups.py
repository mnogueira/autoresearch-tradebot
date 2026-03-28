from __future__ import annotations

import json

from dataclasses import replace

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
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_final_stress_followups_20260328")


def build_vwap_slope_direction_by_index(dataset: V10Dataset, window_bars: int = 30) -> np.ndarray:
    bars = dataset.bars_m1.copy()
    typical_price = (bars["High"] + bars["Low"] + bars["Close"]) / 3.0
    weighted_price = typical_price * bars["Volume"]
    session_groups = bars["session_date"]
    cumulative_value = weighted_price.groupby(session_groups).cumsum()
    cumulative_volume = bars["Volume"].groupby(session_groups).cumsum()
    vwap = cumulative_value / cumulative_volume.replace(0, np.nan)
    slope = vwap.groupby(session_groups).diff(int(window_bars)) / float(window_bars)
    return np.sign(slope.fillna(0.0)).astype(int).to_numpy()


def vwap_slope_filter(base_hours: set[int], slope_direction_by_index: np.ndarray):
    base = session_filter(base_hours)

    def _filter(context: dict[str, object]) -> bool:
        if not base(context):
            return False
        dataset_index = int(context["dataset_index"])
        direction = int(context["direction"])
        slope_direction = int(slope_direction_by_index[dataset_index])
        if direction == 1:
            return slope_direction > 0
        if direction == -1:
            return slope_direction < 0
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

    slope_direction_by_index = build_vwap_slope_direction_by_index(dataset, window_bars=30)
    slope_filter = vwap_slope_filter(allowed_hours, slope_direction_by_index)
    _, slope_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=slope_filter,
        management=base_management,
    )

    size_grid_results: list[dict[str, object]] = []
    for contracts in (0.5, 1.0, 2.0, 3.0):
        sized_params = replace(params, ContractsPerTrade=float(contracts))
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=sized_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=base_management,
        )
        size_grid_results.append({"contracts_per_trade": contracts, "metrics": metrics})

    _, spread_3x_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            spread_multiplier=3.0,
        ),
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "vwap_slope_filter_variant": {
            "rule": "Require the simple 30-bar intraday VWAP slope sign to agree with the entry direction.",
            "metrics": slope_metrics,
        },
        "contracts_per_trade_grid": size_grid_results,
        "spread_3x_stress": {
            "rule": "Multiply the exact intrabar spread by 3.0x on the max-hold leader.",
            "metrics": spread_3x_metrics,
        },
        "notes": [
            "The VWAP slope uses session-cumulative VWAP and a simple 30-bar slope proxy: (VWAP_t - VWAP_t-30) / 30.",
            "Contract-size runs reuse the same exact trade logic but vary ContractsPerTrade to expose how fixed transaction costs bend the curve.",
            "The 3x spread stress is the harsh slippage-style case for the current max-hold leader, not the earlier plain session winner.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_vwap_slope30",
            family="session_intraday_regime_filter",
            metrics=slope_metrics,
            notes="Exact max-hold leader gated by a 30-bar intraday VWAP slope sign filter.",
            artifact=summary_path,
            params={"vwap_slope_window_bars": 30},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_spread_3x",
            family="session_cost_stress",
            metrics=spread_3x_metrics,
            notes="Exact max-hold leader with intrabar spread multiplied by 3.0x.",
            artifact=summary_path,
            params={"spread_multiplier": 3.0, "max_bars_in_trade": 120, "min_minutes_between_entries": 30},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
