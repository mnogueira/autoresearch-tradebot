from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import _composite_score, _daily_pnl_from_trades, _risk_adjusted_metrics
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_contract_stress_followups_20260328")


def impact_vs_reference(reference: dict[str, float], candidate: dict[str, float]) -> dict[str, float]:
    return {
        "net_profit_brl_delta": round(float(candidate["net_profit_brl"]) - float(reference["net_profit_brl"]), 2),
        "profit_factor_delta": round(float(candidate["profit_factor"]) - float(reference["profit_factor"]), 4),
        "max_drawdown_pct_delta": round(float(candidate["max_drawdown_pct"]) - float(reference["max_drawdown_pct"]), 2),
        "win_rate_delta": round(float(candidate["win_rate"]) - float(reference["win_rate"]), 4),
        "total_trades_delta": int(candidate["total_trades"]) - int(reference["total_trades"]),
        "on_tester_value_delta": round(
            float(candidate["on_tester_value"]) - float(reference["on_tester_value"]),
            6,
        ),
    }


def contract_month_metrics(reference_trades: pd.DataFrame, dataset: V10Dataset) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for contract_id, contract_daily in dataset.daily.groupby("contract_id", sort=True):
        contract_dates = pd.Index(contract_daily.index)
        contract_trades = filter_trades_to_dates(reference_trades, contract_dates)
        metrics = calculate_metrics(contract_trades, contract_dates)
        risk_metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(contract_trades, contract_dates))
        rows.append(
            {
                "contract_id": str(contract_id),
                "trading_days": int(len(contract_dates)),
                "metrics": metrics,
                "risk_adjusted_metrics": risk_metrics,
                "sortino_weighted_composite": _composite_score(risk_metrics),
            }
        )
    return rows


def summarise_contract_months(contract_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_by_net = sorted(contract_rows, key=lambda row: float(row["metrics"]["net_profit_brl"]))
    ranked_by_composite = sorted(contract_rows, key=lambda row: float(row["sortino_weighted_composite"]))
    positive_contracts = sum(1 for row in contract_rows if float(row["metrics"]["net_profit_brl"]) > 0.0)
    negative_contracts = sum(1 for row in contract_rows if float(row["metrics"]["net_profit_brl"]) < 0.0)
    flat_contracts = len(contract_rows) - positive_contracts - negative_contracts
    return {
        "num_contracts": int(len(contract_rows)),
        "positive_contracts": int(positive_contracts),
        "negative_contracts": int(negative_contracts),
        "flat_contracts": int(flat_contracts),
        "positive_contract_share_pct": round((positive_contracts / len(contract_rows)) * 100.0, 2) if contract_rows else 0.0,
        "median_profit_factor": round(float(pd.Series([row["metrics"]["profit_factor"] for row in contract_rows]).median()), 4)
        if contract_rows
        else 0.0,
        "median_composite": round(float(pd.Series([row["sortino_weighted_composite"] for row in contract_rows]).median()), 4)
        if contract_rows
        else 0.0,
        "best_contract_by_net": ranked_by_net[-1] if ranked_by_net else None,
        "worst_contract_by_net": ranked_by_net[0] if ranked_by_net else None,
        "best_contract_by_composite": ranked_by_composite[-1] if ranked_by_composite else None,
        "worst_contract_by_composite": ranked_by_composite[0] if ranked_by_composite else None,
        "last_6_contracts": contract_rows[-6:],
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    trade_dates = dataset.trade_dates
    base_filter = session_filter({10, 11, 12, 14})
    production_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=production_management,
    )

    fixed_spread_management = replace(production_management, fixed_spread_ticks=5, spread_multiplier=1.0)
    fixed_spread_trades, fixed_spread_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=fixed_spread_management,
    )
    fixed_spread_risk = _risk_adjusted_metrics(_daily_pnl_from_trades(fixed_spread_trades, trade_dates))

    contract_rows = contract_month_metrics(reference_trades, dataset)
    contract_summary = summarise_contract_months(contract_rows)

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown30_maxhold120",
            "metrics": reference_metrics,
        },
        "fixed_spread_5_ticks": {
            "assumption": "Every bar is forced to a 5-tick bid/ask spread inside the exact engine.",
            "metrics": fixed_spread_metrics,
            "impact_vs_reference": impact_vs_reference(reference_metrics, fixed_spread_metrics),
            "risk_adjusted_metrics": fixed_spread_risk,
            "sortino_weighted_composite": _composite_score(fixed_spread_risk),
        },
        "contract_month_robustness": {
            "definition": "Production candidate evaluated separately on each monthly WDO contract bucket from the daily contract_id series.",
            "summary": contract_summary,
            "all_contract_rows": contract_rows,
        },
        "notes": [
            "This pass stress-tests the exact production candidate, not the MT5 base preset.",
            "The 5-tick spread scenario is intentionally harsh and uses a fixed spread rather than a multiplier on the cached 0/1 tick tape.",
            "Contract-month robustness uses the daily contract_id buckets already present in the dataset and scores each contract month independently.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown30_maxhold120_fixed_spread_5_ticks",
            family="session_stress_test",
            metrics=fixed_spread_metrics,
            notes="Exact production candidate with a forced fixed 5-tick spread on every bar. Stress only, not a live candidate.",
            artifact=summary_path,
            params={
                "fixed_spread_ticks": 5,
                "min_minutes_between_entries": 30,
                "max_bars_in_trade": 120,
            },
        )
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
