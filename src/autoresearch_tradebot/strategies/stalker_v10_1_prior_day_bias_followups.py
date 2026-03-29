from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_prior_day_bias_followups_20260329")


def _prior_day_bias_filter(dataset: V10Dataset):
    bars = dataset.bars_m1.copy()
    session_dates = pd.to_datetime(bars["session_date"]).dt.normalize()
    daily = (
        bars.assign(session_date_norm=session_dates)
        .groupby("session_date_norm")
        .agg(Open=("Open", "first"), Close=("Close", "last"))
    )
    bias = np.sign(daily["Close"] - daily["Open"]).shift(1)
    bias_lookup = {pd.Timestamp(idx).date().isoformat(): int(val) for idx, val in bias.items() if np.isfinite(val)}

    def _allow(context: dict[str, object]) -> bool:
        session_key = pd.Timestamp(context["session_date"]).date().isoformat()
        day_bias = int(bias_lookup.get(session_key, 0))
        if day_bias == 0:
            return False
        return int(context["direction"]) == day_bias

    return _allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    tier2_management = ManagementConfig(min_minutes_between_entries=25)
    prior_day_bias = _prior_day_bias_filter(dataset)
    roc5 = _make_roc_filter(dataset, 5)

    def t2_prior_day(context: dict[str, object]) -> bool:
        return bool(base_filter(context) and prior_day_bias(context))

    def t2a_prior_day(context: dict[str, object]) -> bool:
        return bool(base_filter(context) and prior_day_bias(context) and roc5(context))

    variants = []
    leaderboard_rows = []
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    for name, rule, entry_filter in (
        (
            "tier2_prior_day_bias_confirmation",
            "Only trade in the direction of the prior day's close-vs-open sign on top of Tier 2.",
            t2_prior_day,
        ),
        (
            "tier2a_prior_day_bias_confirmation",
            "Only trade in the direction of the prior day's close-vs-open sign on top of Tier 2A.",
            t2a_prior_day,
        ),
    ):
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=tier2_management,
        )
        risk_block = _risk_block(trades, trade_dates)
        row = {
            "name": name,
            "rule": rule,
            "metrics": metrics,
            **risk_block,
            "params": {"management": asdict(tier2_management), "uses_prior_day_bias_filter": True},
        }
        variants.append(row)
        leaderboard_row = candidate_row(
            name=name,
            family="stalker_v10_1_prior_day_bias",
            metrics=metrics,
            notes=rule,
            artifact=summary_path,
            params=row["params"],
        )
        leaderboard_row["comparison_tier"] = "exact"
        leaderboard_row["screening_method"] = "prior_day_bias_followup"
        leaderboard_row["sortino_ratio"] = risk_block["risk_adjusted_metrics"]["sortino_ratio"]
        leaderboard_row["calmar_ratio"] = risk_block["risk_adjusted_metrics"]["calmar_ratio"]
        leaderboard_row["omega_ratio"] = risk_block["risk_adjusted_metrics"]["omega_ratio"]
        leaderboard_row["sortino_weighted_composite"] = risk_block["sortino_weighted_composite"]
        leaderboard_rows.append(leaderboard_row)

    variants.sort(key=lambda row: float(row["sortino_weighted_composite"]), reverse=True)
    summary = {
        "variants": variants,
        "notes": [
            "This batch tests a simple prior-day directional bias filter using the previous session's close-vs-open sign.",
            "The idea is to see whether the intraday strategy works better when aligned with the previous daily tape.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
