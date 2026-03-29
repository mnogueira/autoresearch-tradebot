from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_directional_contract_switch_followups_20260329 import _combine_filters
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_survival_followups_20260329")


def _subset_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict:
    session_index = pd.Index(trade_dates).strftime("%Y-%m-%d")
    subset = trades.loc[trades["session_date"].isin(session_index)].reset_index(drop=True)
    return {
        "metrics": calculate_metrics(subset, trade_dates),
        **_risk_block(subset, trade_dates),
    }


def _variant_payload(name: str, rule: str, trades: pd.DataFrame, trade_dates: pd.Index, params: dict) -> dict:
    return {
        "name": name,
        "rule": rule,
        "metrics": calculate_metrics(trades, trade_dates),
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    base_params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    variants: list[dict] = []
    best_trades: pd.DataFrame | None = None
    best_name = ""
    best_score = float("-inf")

    variant_specs = [
        (
            "tier2a_corrected_reference",
            "Corrected-cost Tier 2A reference.",
            base_params,
            ManagementConfig(min_minutes_between_entries=28),
        ),
        (
            "tier2a_corrected_tp042_cd28",
            "Corrected-cost Tier 2A with wider TP 0.42 and the promoted 28m cooldown.",
            replace(base_params, TP_ATRMultiplier=0.42),
            ManagementConfig(min_minutes_between_entries=28),
        ),
        (
            "tier2a_corrected_tp048_cd28",
            "Corrected-cost Tier 2A with wider TP 0.48 and the promoted 28m cooldown.",
            replace(base_params, TP_ATRMultiplier=0.48),
            ManagementConfig(min_minutes_between_entries=28),
        ),
        (
            "tier2a_corrected_tp048_cd40",
            "Corrected-cost Tier 2A with wider TP 0.48 and reduced trade frequency via 40m cooldown.",
            replace(base_params, TP_ATRMultiplier=0.48),
            ManagementConfig(min_minutes_between_entries=40),
        ),
        (
            "tier2a_corrected_tp048_cd60",
            "Corrected-cost Tier 2A with wider TP 0.48 and reduced trade frequency via 60m cooldown.",
            replace(base_params, TP_ATRMultiplier=0.48),
            ManagementConfig(min_minutes_between_entries=60),
        ),
        (
            "tier3_corrected_tp048_cd25_max150",
            "Corrected-cost Tier 3 with wider TP 0.48, 25m cooldown, and 150m max-hold.",
            replace(base_params, TP_ATRMultiplier=0.48),
            ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150),
        ),
    ]

    for name, rule, params, management in variant_specs:
        trades, _ = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        payload = _variant_payload(
            name=name,
            rule=rule,
            trades=trades,
            trade_dates=trade_dates,
            params={"params": asdict(params), "management": asdict(management)},
        )
        variants.append(payload)
        score = float(payload["sortino_weighted_composite"])
        if score > best_score:
            best_score = score
            best_name = name
            best_trades = trades

    assert best_trades is not None

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

    summary = {
        "ranked_variants": ranked,
        "best_variant_walkforward_70_30": {
            "variant_name": best_name,
            "train": _subset_block(best_trades, train_dates),
            "test": _subset_block(best_trades, test_dates),
        },
        "best_variant_recent_windows": {
            "variant_name": best_name,
            "recent_60d": _subset_block(best_trades, recent_60),
            "recent_30d": _subset_block(best_trades, recent_30),
            "recent_10d": _subset_block(best_trades, recent_10),
        },
        "notes": [
            "Cost-survival sweep after the corrected rerun. Goal: find any static variant that still clears conservative retail WDO costs.",
            "The sweep focuses on wider TP and fewer trades because those are the most plausible ways to survive flat fees without assuming variable sizing.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
