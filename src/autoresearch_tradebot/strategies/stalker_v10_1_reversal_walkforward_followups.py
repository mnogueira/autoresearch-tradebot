from __future__ import annotations

import json
from typing import Any

import pandas as pd

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
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_reversal_walkforward_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _filter_trades_by_dates(trades: pd.DataFrame, dates: pd.Index) -> pd.DataFrame:
    if trades.empty:
        return trades
    normalized_dates = pd.Index(pd.to_datetime(dates))
    session_dates = pd.to_datetime(trades["session_date"]).dt.normalize()
    return trades.loc[session_dates.isin(normalized_dates)].reset_index(drop=True)


def _result_block(trades: pd.DataFrame, metrics: dict[str, Any], trade_dates: pd.Index, note: str) -> dict[str, Any]:
    return {
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "note": note,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    train_dates, test_dates = split_dates(dataset.trade_dates, 0.70)

    leader_trades, leader_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=25,
            max_bars_in_trade=120,
        ),
    )

    reversal_trades, reversal_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=25,
            max_bars_in_trade=120,
            trend_flip_exit_bars=5,
        ),
    )

    leader_train = _filter_trades_by_dates(leader_trades, train_dates)
    leader_test = _filter_trades_by_dates(leader_trades, test_dates)

    summary = {
        "leader_reference_25m_maxhold120": _result_block(
            leader_trades,
            leader_metrics,
            dataset.trade_dates,
            "Current best deployable exact composite candidate.",
        ),
        "leader_70_30_walkforward": {
            "train": {
                "metrics": calculate_metrics(leader_train, train_dates),
                **_risk_block(leader_train, train_dates),
            },
            "test": {
                "metrics": calculate_metrics(leader_test, test_dates),
                **_risk_block(leader_test, test_dates),
            },
            "note": "Fixed-parameter 70/30 chronological walk-forward on the 25-minute cooldown plus max-hold leader.",
        },
        "early_exit_on_trend_flip_5bars": _result_block(
            reversal_trades,
            reversal_metrics,
            dataset.trade_dates,
            "Exit immediately at the next open if directional trend-efficiency flips sign within 5 bars of entry.",
        ),
        "notes": [
            "The walk-forward is chronological and uses the current 25-minute cooldown plus 120-minute max-hold line without re-optimizing parameters.",
            "The reversal exit is tested as a pure risk-control overlay on the same line.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
