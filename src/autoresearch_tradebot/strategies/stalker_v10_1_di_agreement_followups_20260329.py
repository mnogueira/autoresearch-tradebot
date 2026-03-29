from __future__ import annotations

import json
from dataclasses import replace

from ta.trend import ADXIndicator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_di_agreement_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _make_di_filter(plus_di, minus_di):
    def allow(context):
        idx = int(context["dataset_index"])
        plus_value = float(plus_di[idx])
        minus_value = float(minus_di[idx])
        if plus_value != plus_value or minus_value != minus_value:
            return False
        direction = int(context["direction"])
        return plus_value >= minus_value if direction == 1 else minus_value >= plus_value

    return allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    management = ManagementConfig(min_minutes_between_entries=28)

    bars = dataset.bars_m1
    adx = ADXIndicator(
        high=bars["High"].astype(float),
        low=bars["Low"].astype(float),
        close=bars["Close"].astype(float),
        window=14,
    )
    plus_di = adx.adx_pos().shift(1).to_numpy(dtype=float)
    minus_di = adx.adx_neg().shift(1).to_numpy(dtype=float)

    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    di_filter = _make_di_filter(plus_di, minus_di)

    reference_filter = _combine_filters(base_filter, roc5_filter)
    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=reference_filter,
        management=management,
    )
    candidate_filter = _combine_filters(base_filter, roc5_filter, di_filter)
    candidate_trades, candidate_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=candidate_filter,
        management=management,
    )

    candidate = {
        "name": "tier2a_di_sign",
        "rule": "Strengthened Tier 2A with +DI/-DI directional agreement.",
        "metrics": candidate_metrics,
        **_risk_block(candidate_trades, trade_dates),
        "params": {
            "di_window": 14,
            "roc_agreement_bars": 5,
            "ATR_Length": 10,
            "NumDaysToConsiderPreviousContractMARange": 2,
            "min_minutes_between_entries": 28,
        },
    }

    summary = {
        "reference_tier2a": {
            "metrics": reference_metrics,
            **_risk_block(reference_trades, trade_dates),
        },
        "candidate_di_sign": candidate,
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    row = _leaderboard_row(candidate, summary_path)
    row["family"] = "stalker_v10_1_di_agreement_followup"
    row["screening_method"] = "di_agreement_followup"
    row["comparison_tier"] = "research_exact"
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
