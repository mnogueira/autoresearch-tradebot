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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_opening_bias_followups_20260329")


def _opening_bias_filter(dataset: V10Dataset):
    bars = dataset.bars_m1.copy()
    timestamps = pd.to_datetime(bars.index)
    bars["timestamp"] = timestamps
    bars["session_date_norm"] = pd.to_datetime(bars["session_date"]).dt.normalize()
    first_hour = bars.loc[(bars["timestamp"].dt.hour == 9)]
    grouped = first_hour.groupby("session_date_norm")
    session_open = grouped["Open"].first()
    session_close = grouped["Close"].last()
    bias = np.sign(session_close - session_open)
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
    opening_bias = _opening_bias_filter(dataset)
    roc5 = _make_roc_filter(dataset, 5)

    def t2_opening_bias(context: dict[str, object]) -> bool:
        return bool(base_filter(context) and opening_bias(context))

    def t2a_opening_bias(context: dict[str, object]) -> bool:
        return bool(base_filter(context) and opening_bias(context) and roc5(context))

    variants = []
    leaderboard_rows = []
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    for name, rule, entry_filter in (
        (
            "tier2_opening_bias_confirmation",
            "Only trade in the direction of the 09:00-10:00 opening-hour session return on top of Tier 2.",
            t2_opening_bias,
        ),
        (
            "tier2a_opening_bias_confirmation",
            "Only trade in the direction of the 09:00-10:00 opening-hour session return on top of Tier 2A.",
            t2a_opening_bias,
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
            "params": {"management": asdict(tier2_management), "uses_opening_bias_filter": True},
        }
        variants.append(row)
        leaderboard_row = candidate_row(
            name=name,
            family="stalker_v10_1_opening_bias",
            metrics=metrics,
            notes=rule,
            artifact=summary_path,
            params=row["params"],
        )
        leaderboard_row["comparison_tier"] = "exact"
        leaderboard_row["screening_method"] = "opening_bias_followup"
        leaderboard_row["sortino_ratio"] = risk_block["risk_adjusted_metrics"]["sortino_ratio"]
        leaderboard_row["calmar_ratio"] = risk_block["risk_adjusted_metrics"]["calmar_ratio"]
        leaderboard_row["omega_ratio"] = risk_block["risk_adjusted_metrics"]["omega_ratio"]
        leaderboard_row["sortino_weighted_composite"] = risk_block["sortino_weighted_composite"]
        leaderboard_rows.append(leaderboard_row)

    variants.sort(key=lambda row: float(row["sortino_weighted_composite"]), reverse=True)
    summary = {
        "variants": variants,
        "notes": [
            "This batch tests a simple opening-bias regime filter using the 09:00-10:00 session return sign.",
            "The idea is to see whether the later session signal works better when aligned with the first hour's directional tape.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
