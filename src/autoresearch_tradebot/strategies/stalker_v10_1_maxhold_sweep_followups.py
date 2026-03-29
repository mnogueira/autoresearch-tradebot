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
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_maxhold_sweep_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _recent_metrics(trades: pd.DataFrame, recent_dates: pd.Index) -> dict[str, Any]:
    if trades.empty:
        recent_trades = trades
    else:
        session_dates = pd.to_datetime(trades["session_date"]).dt.normalize()
        recent_index = pd.Index(pd.to_datetime(recent_dates))
        recent_trades = trades.loc[session_dates.isin(recent_index)].reset_index(drop=True)
    metrics = calculate_metrics(recent_trades, pd.Index(pd.to_datetime(recent_dates)))
    return {
        "metrics": metrics,
        **_risk_block(recent_trades, pd.Index(pd.to_datetime(recent_dates))),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    recent_dates = dataset.trade_dates[-30:]

    results: list[dict[str, Any]] = []
    for max_minutes in (60, 90, 120, 150, 180):
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(
                min_minutes_between_entries=25,
                max_bars_in_trade=int(max_minutes),
            ),
        )
        results.append(
            {
                "max_hold_minutes": int(max_minutes),
                "metrics": metrics,
                **_risk_block(trades, dataset.trade_dates),
                "recent_30d": _recent_metrics(trades, recent_dates),
            }
        )

    ranked = sorted(
        results,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["metrics"]["profit_factor"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )

    summary = {
        "maxhold_sweep_with_25m_cooldown": ranked,
        "notes": [
            "All runs use the current 25-minute cooldown winner plus the same session filter, SL, and TP.",
            "Max hold is evaluated in M1 bars because the execution harness measures trade age on the M1 path.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
