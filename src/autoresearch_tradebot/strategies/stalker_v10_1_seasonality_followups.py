from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import _composite_score, _daily_pnl_from_trades, _risk_adjusted_metrics
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_seasonality_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _subset_metrics(trades: pd.DataFrame, label: str) -> dict[str, object]:
    subset = trades.copy()
    subset_dates = pd.Index(sorted(pd.to_datetime(subset["session_date"]).unique())) if not subset.empty else pd.Index([])
    metrics = calculate_metrics(subset, subset_dates if len(subset_dates) else pd.Index([pd.Timestamp("2021-01-01")]))
    return {
        "label": label,
        "metrics": metrics,
        **_risk_block(subset, subset_dates if len(subset_dates) else pd.Index([pd.Timestamp("2021-01-01")])),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=session_winner_params(),
        trade_dates=dataset.trade_dates,
        entry_filter=session_filter({10, 11, 12, 14}),
        management=ManagementConfig(min_minutes_between_entries=30),
    )

    frame = trades.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    frame["quarter"] = frame["session_date"].dt.quarter
    frame["month"] = frame["session_date"].dt.month
    frame["year"] = frame["session_date"].dt.year
    frame["year_quarter"] = frame["year"].astype(str) + "-Q" + frame["quarter"].astype(str)

    quarter_results: list[dict[str, object]] = []
    for quarter in (1, 2, 3, 4):
        quarter_subset = frame.loc[frame["quarter"].eq(quarter)].copy()
        quarter_results.append(_subset_metrics(quarter_subset, f"Q{quarter}"))

    q1_q3_subset = frame.loc[frame["quarter"].isin([1, 3])].copy()
    q2_q4_subset = frame.loc[frame["quarter"].isin([2, 4])].copy()

    yearly_quarter_rows = []
    for year_quarter, group in frame.groupby("year_quarter", sort=True):
        yearly_quarter_rows.append(_subset_metrics(group.copy(), str(year_quarter)))

    summary = {
        "reference_tier2_cooldown_only": {
            "metrics": metrics,
            **_risk_block(trades, dataset.trade_dates),
        },
        "quarter_breakdown": quarter_results,
        "seasonal_pairs": {
            "q1_q3_combined": _subset_metrics(q1_q3_subset, "Q1_Q3"),
            "q2_q4_combined": _subset_metrics(q2_q4_subset, "Q2_Q4"),
        },
        "year_quarter_breakdown": yearly_quarter_rows,
        "notes": [
            "Seasonality is evaluated on the Tier 2 exact production candidate: session hours 10/11/12/14 with a 30-minute cooldown.",
            "Quarter subsets are pooled across all years in the backtest window.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
