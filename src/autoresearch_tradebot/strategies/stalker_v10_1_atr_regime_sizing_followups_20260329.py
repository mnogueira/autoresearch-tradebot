from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_discrete_strength_sizing_followups_20260329 import _risk_block
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_atr_regime_sizing_followups_20260329")


def _combine_filters(*filters):
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _apply_session_weights(trades: pd.DataFrame, session_weights: pd.Series) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    frame = trades.copy()
    weights = pd.to_datetime(frame["session_date"]).dt.normalize().map(session_weights).fillna(1.0).astype(float)
    frame["atr_regime_size_multiplier"] = weights.to_numpy(dtype=float)
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["atr_regime_size_multiplier"]
    if "pnl_points" in frame.columns:
        frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["atr_regime_size_multiplier"]
    return frame


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    params: dict[str, Any],
) -> dict[str, Any]:
    metrics = calculate_metrics(trades, trade_dates)
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _leaderboard_row_for_variant(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = _leaderboard_row(variant, artifact)
    row["family"] = "stalker_v10_1_atr_regime_sizing_followup"
    row["screening_method"] = "atr_regime_sizing_followup"
    row["comparison_tier"] = "research_sizing"
    return row


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    management = ManagementConfig(min_minutes_between_entries=28)
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    q33 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.3333)
    q67 = prior_day_atr14.rolling(60, min_periods=20).quantile(0.6667)

    low_mask = prior_day_atr14 <= q33
    high_mask = prior_day_atr14 > q67

    variants = [
        _variant_payload(
            "tier2a_reference",
            "Strengthened Tier 2A reference with fixed one-contract sizing.",
            trades,
            trade_dates,
            {
                "management": asdict(management),
                "roc_agreement_bars": 5,
                "ATR_Length": 10,
                "NumDaysToConsiderPreviousContractMARange": 2,
            },
        )
    ]

    sizing_scenarios = [
        ("high_atr_half", 1.0, 1.0, 0.5),
        ("high_atr_three_quarter", 1.0, 1.0, 0.75),
        ("low_up_high_down", 1.25, 1.0, 0.5),
        ("low_up_high_three_quarter", 1.25, 1.0, 0.75),
    ]

    for name, low_weight, mid_weight, high_weight in sizing_scenarios:
        session_weights = pd.Series(mid_weight, index=prior_day_atr14.index, dtype=float)
        session_weights.loc[low_mask.fillna(False)] = float(low_weight)
        session_weights.loc[high_mask.fillna(False)] = float(high_weight)
        weighted_trades = _apply_session_weights(trades, session_weights)
        variants.append(
            _variant_payload(
                f"tier2a_{name}",
                f"Strengthened Tier 2A with ATR-regime sizing overlay ({low_weight}x low, {mid_weight}x medium, {high_weight}x high ATR).",
                weighted_trades,
                trade_dates,
                {
                    "management": asdict(management),
                    "roc_agreement_bars": 5,
                    "ATR_Length": 10,
                    "NumDaysToConsiderPreviousContractMARange": 2,
                    "atr_regime_sizing": {
                        "lookback_days": 60,
                        "low_weight": low_weight,
                        "medium_weight": mid_weight,
                        "high_weight": high_weight,
                    },
                },
            )
        )

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
        "atr_regime_definition": {
            "atr_length": 14,
            "lookback_days": 60,
            "low_bucket": "bottom 33% of prior-day ATR14",
            "high_bucket": "top 33% of prior-day ATR14",
            "middle_bucket": "everything in between",
        },
        "notes": [
            "Research-only sizing overlay motivated by earlier evidence that high-ATR days were worse for this signal family.",
            "This does not change the actual entry/exit logic; it only rescales trade PnL by prior-day ATR regime.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(
        DEFAULT_LEADERBOARD_PATH,
        [_leaderboard_row_for_variant(variant, summary_path) for variant in variants if variant["name"] != "tier2a_reference"],
    )


if __name__ == "__main__":
    main()
