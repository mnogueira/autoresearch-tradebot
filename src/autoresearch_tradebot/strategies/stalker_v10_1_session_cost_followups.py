from __future__ import annotations

import json

from dataclasses import replace

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_every_tick_cache
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_deployment_followups import monte_carlo_trade_order
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_cost_followups_20260328")


def build_prior_session_average_spread_ticks(dataset: V10Dataset) -> np.ndarray:
    cache = _ensure_every_tick_cache(dataset)
    spread = pd.Series(cache["spread_ticks"].astype(float))
    session_dates = pd.Series(pd.to_datetime(cache["session_dates"]))
    session_counts = spread.groupby(session_dates).cumcount()
    cumulative_spread = spread.groupby(session_dates).cumsum()
    prior_counts = session_counts.to_numpy(dtype=float)
    prior_spread_sum = cumulative_spread.to_numpy(dtype=float) - spread.to_numpy(dtype=float)
    prior_average = np.divide(
        prior_spread_sum,
        prior_counts,
        out=np.full_like(prior_spread_sum, np.nan, dtype=float),
        where=prior_counts > 0,
    )
    return prior_average


def spread_below_session_average_filter(
    base_hours: set[int],
    spread_ticks_by_index: np.ndarray,
    prior_average_spread_by_index: np.ndarray,
):
    base = session_filter(base_hours)

    def _filter(context: dict[str, object]) -> bool:
        if not base(context):
            return False
        dataset_index = int(context["dataset_index"])
        current_spread = float(spread_ticks_by_index[dataset_index])
        prior_average = float(prior_average_spread_by_index[dataset_index])
        if not np.isfinite(prior_average):
            return False
        return current_spread < prior_average

    return _filter


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    allowed_hours = {10, 11, 12, 14}
    base_filter = session_filter(allowed_hours)
    base_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    tp_variants: list[dict[str, object]] = []
    tp_metrics_by_value: dict[float, dict[str, object]] = {}
    for tp_multiplier in (0.42, 0.48):
        tp_params = replace(params, TP_ATRMultiplier=float(tp_multiplier))
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=tp_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=base_management,
        )
        tp_metrics_by_value[float(tp_multiplier)] = metrics
        tp_variants.append(
            {
                "tp_atr_multiplier": float(tp_multiplier),
                "metrics": metrics,
            }
        )

    cache = _ensure_every_tick_cache(dataset)
    prior_average_spread = build_prior_session_average_spread_ticks(dataset)
    spread_filter = spread_below_session_average_filter(
        base_hours=allowed_hours,
        spread_ticks_by_index=cache["spread_ticks"],
        prior_average_spread_by_index=prior_average_spread,
    )
    _, spread_aware_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=spread_filter,
        management=base_management,
    )

    monte_carlo = monte_carlo_trade_order(reference_trades, runs=1000, seed=42)

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "wider_tp_variants": tp_variants,
        "spread_aware_entry": {
            "rule": "Only allow entries when the current spread tick count is strictly below the average spread observed earlier in the same session.",
            "historical_spread_ticks_unique_values": [int(value) for value in np.unique(cache["spread_ticks"]).tolist()],
            "metrics": spread_aware_metrics,
        },
        "monte_carlo": monte_carlo,
        "notes": [
            "The production candidate for this pass is the exact session winner with a 30-minute cooldown and a 120 M1-bar max hold.",
            "The wider take-profit variants keep the same entry logic, cooldown, and max-hold logic and only change the ATR-based TP multiplier.",
            "The spread-aware gate uses a strict prior-session average, so it never looks ahead within the day.",
            "Pure trade-order shuffling keeps final PnL fixed by construction; bootstrap resampling is included to provide an ending-PnL dispersion view.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_tp0p42",
            family="session_take_profit_extension",
            metrics=tp_metrics_by_value[0.42],
            notes="Exact session+cooldown+120m max-hold leader with a wider ATR take-profit of 0.42.",
            artifact=summary_path,
            params={"tp_atr_multiplier": 0.42, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_tp0p48",
            family="session_take_profit_extension",
            metrics=tp_metrics_by_value[0.48],
            notes="Exact session+cooldown+120m max-hold leader with a wider ATR take-profit of 0.48.",
            artifact=summary_path,
            params={"tp_atr_multiplier": 0.48, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_spread_below_session_avg",
            family="session_cost_filter",
            metrics=spread_aware_metrics,
            notes="Exact session+cooldown+120m max-hold leader gated by a strict prior-session average spread filter.",
            artifact=summary_path,
            params={"spread_rule": "current_spread_ticks < prior_session_average_spread_ticks"},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
