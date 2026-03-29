from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_directional_contract_switch_followups_20260329 import _combine_filters
from .stalker_v10_1_roc_agreement_followups import _leaderboard_row, _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_production_rerun_20260329")


def _variant_payload(
    name: str,
    family: str,
    rule: str,
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    params: dict,
    walkforward: bool = True,
    recent_windows: bool = True,
) -> dict:
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    payload = {
        "name": name,
        "family": family,
        "rule": rule,
        "metrics": calculate_metrics(trades, trade_dates),
        **_risk_block(trades, trade_dates),
        "params": params,
    }
    if walkforward:
        train_trades = trades[trades["session_date"].isin(pd.Index(train_dates).strftime("%Y-%m-%d"))].copy()
        test_trades = trades[trades["session_date"].isin(pd.Index(test_dates).strftime("%Y-%m-%d"))].copy()
        payload["walkforward_70_30"] = {
            "train_metrics": calculate_metrics(train_trades, train_dates),
            "train_risk": _risk_block(train_trades, train_dates),
            "test_metrics": calculate_metrics(test_trades, test_dates),
            "test_risk": _risk_block(test_trades, test_dates),
        }
    if recent_windows:
        recent_60 = trade_dates[-60:]
        recent_30 = trade_dates[-30:]
        recent_10 = trade_dates[-10:]
        payload["recent_60d"] = {
            "metrics": calculate_metrics(trades[trades["session_date"].isin(pd.Index(recent_60).strftime("%Y-%m-%d"))], recent_60),
            **_risk_block(trades[trades["session_date"].isin(pd.Index(recent_60).strftime("%Y-%m-%d"))], recent_60),
        }
        payload["recent_30d"] = {
            "metrics": calculate_metrics(trades[trades["session_date"].isin(pd.Index(recent_30).strftime("%Y-%m-%d"))], recent_30),
            **_risk_block(trades[trades["session_date"].isin(pd.Index(recent_30).strftime("%Y-%m-%d"))], recent_30),
        }
        payload["recent_10d"] = {
            "metrics": calculate_metrics(trades[trades["session_date"].isin(pd.Index(recent_10).strftime("%Y-%m-%d"))], recent_10),
            **_risk_block(trades[trades["session_date"].isin(pd.Index(recent_10).strftime("%Y-%m-%d"))], recent_10),
        }
    return payload


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    base_params = session_winner_params()

    tier1_params = V101Params(SL_ATRMultiplier=0.84, TP_ATRMultiplier=0.30)
    tier1_trades, _ = run_backtest(dataset=dataset, params=tier1_params, trade_dates=trade_dates)

    tier2_mgmt = ManagementConfig(min_minutes_between_entries=25)
    tier3_mgmt = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    tier2a_mgmt = ManagementConfig(min_minutes_between_entries=28)

    tier2_filter = session_filter({10, 11, 12, 14})
    tier2a_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    tier2_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=tier2_filter,
        management=tier2_mgmt,
    )
    tier2a_params = replace(base_params, ATR_Length=10, NumDaysToConsiderPreviousContractMARange=2)
    tier2a_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=tier2a_params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=tier2a_mgmt,
    )
    tier3_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=tier2a_params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=tier3_mgmt,
    )

    variants = [
        _variant_payload(
            "tier1_exact_analog_corrected",
            "corrected_production_rerun",
            "Tier 1 exact analog rerun after cost/lookahead fixes.",
            tier1_trades,
            trade_dates,
            {"params": asdict(tier1_params)},
        ),
        _variant_payload(
            "tier2_corrected",
            "corrected_production_rerun",
            "Tier 2 rerun after cost/lookahead fixes.",
            tier2_trades,
            trade_dates,
            {"params": asdict(base_params), "management": asdict(tier2_mgmt)},
        ),
        _variant_payload(
            "tier2a_corrected",
            "corrected_production_rerun",
            "Tier 2A rerun after cost/lookahead fixes.",
            tier2a_trades,
            trade_dates,
            {"params": asdict(tier2a_params), "management": asdict(tier2a_mgmt), "roc_agreement_bars": 5},
        ),
        _variant_payload(
            "tier3_corrected",
            "corrected_production_rerun",
            "Tier 3 rerun after cost/lookahead fixes.",
            tier3_trades,
            trade_dates,
            {"params": asdict(tier2a_params), "management": asdict(tier3_mgmt), "roc_agreement_bars": 5},
        ),
    ]

    ranked = sorted(
        variants,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["batch_rank"] = rank

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "ranked_variants": ranked,
                "notes": [
                    "Corrective rerun after setting ROUND_TRIP_COST_BRL to 11.0, lagging ROC filters by one bar, switching ATR sizing to get_atr_open, and resetting cooldowns at session boundaries.",
                    "Spread conversion was verified against the data: Spread column values are 0 or 500, so 0.001 price-unit scaling remains correct (500 -> 0.5 BRL -> 1 tick).",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    leaderboard_rows = []
    for variant in ranked:
        row = candidate_row(
            name=variant["name"],
            family="corrected_production_rerun",
            metrics=dict(variant["metrics"]),
            notes=variant["rule"],
            artifact=summary_path,
            params=variant["params"],
        )
        row["comparison_tier"] = "corrected"
        row["sortino_ratio"] = variant["risk_adjusted_metrics"]["sortino_ratio"]
        row["calmar_ratio"] = variant["risk_adjusted_metrics"]["calmar_ratio"]
        row["omega_ratio"] = variant["risk_adjusted_metrics"]["omega_ratio"]
        row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
        leaderboard_rows.append(row)
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
