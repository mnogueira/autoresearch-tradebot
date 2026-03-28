from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_followups import daily_ohlc_from_bars
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_macro_followups import compute_adx
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_2025_half_split_20260328")


def select_trade_dates(dataset: V10Dataset, start_date: str, end_date: str) -> pd.Index:
    normalized = pd.to_datetime(dataset.trade_dates).normalize()
    mask = (normalized >= pd.Timestamp(start_date)) & (normalized <= pd.Timestamp(end_date))
    return dataset.trade_dates[mask]


def adx_share_for_dates(dataset: V10Dataset, trade_dates: pd.Index, threshold: float = 25.0) -> float:
    daily_adx = compute_adx(daily_ohlc_from_bars(dataset), period=14).shift(1)
    normalized = pd.to_datetime(trade_dates).normalize()
    values = daily_adx.reindex(normalized)
    if values.empty:
        return 0.0
    return round(float((values.fillna(0.0) > float(threshold)).mean()), 4)


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    first_half_dates = select_trade_dates(dataset, "2025-01-01", "2025-06-30")
    second_half_dates = select_trade_dates(dataset, "2025-07-01", "2025-12-31")

    _, first_half_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=first_half_dates,
        entry_filter=entry_filter,
        management=management,
    )
    _, second_half_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=second_half_dates,
        entry_filter=entry_filter,
        management=management,
    )

    summary = {
        "variant": "session_winner_cooldown_30m_maxhold_120m1bars",
        "first_half_2025": {
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
            "prior_day_adx_gt_25_share": adx_share_for_dates(dataset, first_half_dates),
            "metrics": first_half_metrics,
        },
        "second_half_2025": {
            "start_date": "2025-07-01",
            "end_date": "2025-12-31",
            "prior_day_adx_gt_25_share": adx_share_for_dates(dataset, second_half_dates),
            "metrics": second_half_metrics,
        },
        "notes": [
            "This split keeps the exact production candidate fixed and only changes the calendar slice.",
            "The ADX share is based on prior-day daily ADX(14) > 25 and is reported to show whether the weaker half coincides with a less-trending tape.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
