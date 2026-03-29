from __future__ import annotations

import json
from dataclasses import replace

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
from .stalker_v10_python import POINT_VALUE_BRL, V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_microstructure_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _improve_each_trade_by_one_tick(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    improved = trades.copy()
    tick_brl = POINT_VALUE_BRL * 0.5
    improved["pnl_brl"] = improved["pnl_brl"].astype(float) + tick_brl
    improved["pnl_points"] = improved["pnl_points"].astype(float) + 0.5
    metrics = calculate_metrics(improved, trade_dates)
    return {
        "metrics": metrics,
        **_risk_block(improved, trade_dates),
        "per_trade_improvement_brl": round(float(tick_brl), 2),
        "assumption": "Research-only fill-quality proxy: every executed trade improves by exactly one WDO tick.",
    }


def _lot_size_result(dataset: V10Dataset, contracts: float) -> dict[str, object]:
    params = replace(session_winner_params(), ContractsPerTrade=float(contracts))
    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=session_filter({10, 11, 12, 14}),
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    return {
        "metrics": metrics,
        **_risk_block(trades, dataset.trade_dates),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=session_winner_params(),
        trade_dates=dataset.trade_dates,
        entry_filter=session_filter({10, 11, 12, 14}),
        management=ManagementConfig(min_minutes_between_entries=30),
    )

    summary = {
        "reference_tier2_cooldown_only": {
            "metrics": reference_metrics,
            **_risk_block(reference_trades, dataset.trade_dates),
        },
        "one_tick_better_fill_proxy": _improve_each_trade_by_one_tick(reference_trades, dataset.trade_dates),
        "lot_size_scaling": {
            "contracts_1": _lot_size_result(dataset, 1.0),
            "contracts_2": _lot_size_result(dataset, 2.0),
            "contracts_5": _lot_size_result(dataset, 5.0),
        },
        "notes": [
            "The one-tick-better-fill study is research-only. It assumes every filled trade improves by one WDO tick without changing fill probability.",
            "The lot-size grid is an exact-engine rerun with different ContractsPerTrade values and no additional slippage model.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
