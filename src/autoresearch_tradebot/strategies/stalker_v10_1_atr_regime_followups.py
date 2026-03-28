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
from .stalker_v10_1_recent_softness_analysis import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_atr_regime_followups_20260328")


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

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    q33 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.3333)
    q67 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)

    def regime_filter(regime: str) -> Callable[[dict[str, Any]], bool]:
        def allow(context: dict[str, Any]) -> bool:
            session = pd.Timestamp(context["session_date"]).normalize()
            atr_value = float(prior_day_atr14.get(session, np.nan))
            lower = float(q33.get(session, np.nan))
            upper = float(q67.get(session, np.nan))
            if not (np.isfinite(atr_value) and np.isfinite(lower) and np.isfinite(upper)):
                return False
            if regime == "low":
                return atr_value <= lower
            if regime == "medium":
                return lower < atr_value <= upper
            return atr_value > upper

        return allow

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )
    _, low_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, regime_filter("low")),
        management=cooldown_management,
    )
    _, medium_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, regime_filter("medium")),
        management=cooldown_management,
    )
    _, high_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, regime_filter("high")),
        management=cooldown_management,
    )

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m",
            "metrics": reference_metrics,
        },
        "atr_regime_definition": {
            "atr_length": 14,
            "lookback_days": 60,
            "percentile_buckets": {
                "low": "bottom 33%",
                "medium": "middle 33%",
                "high": "top 33%",
            },
            "rule": "Use prior-day ATR14 percentile rank inside the trailing 60-day ATR14 distribution.",
        },
        "low_atr_regime": {"metrics": low_metrics},
        "medium_atr_regime": {"metrics": medium_metrics},
        "high_atr_regime": {"metrics": high_metrics},
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_atr_regime_high",
            family="session_atr_regime",
            metrics=high_metrics,
            notes="Cooldown-only variant filtered to the top 33% of prior-day ATR14 percentile over a trailing 60-day window.",
            artifact=summary_path,
            params={"atr_length": 14, "atr_percentile_bucket": "high", "lookback_days": 60},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
