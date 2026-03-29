from __future__ import annotations

import json
from dataclasses import replace

from ta.momentum import StochasticOscillator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_stochastic_ceiling_validation_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _make_centerline_filter(array, threshold: float = 50.0):
    def allow(context):
        idx = int(context["dataset_index"])
        value = float(array[idx])
        if value != value:
            return False
        direction = int(context["direction"])
        return value >= threshold if direction == 1 else value <= threshold

    return allow


def _summarize_window(dataset, params, trade_dates, entry_filter, management):
    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )
    return {
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    management = ManagementConfig(min_minutes_between_entries=28)

    bars = dataset.bars_m1
    stochastic = StochasticOscillator(
        high=bars["High"].astype(float),
        low=bars["Low"].astype(float),
        close=bars["Close"].astype(float),
        window=14,
        smooth_window=3,
    )
    stoch_d = stochastic.stoch_signal().shift(1).to_numpy(dtype=float)

    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    reference_filter = _combine_filters(base_filter, roc5_filter)
    candidate_filter = _combine_filters(base_filter, roc5_filter, _make_centerline_filter(stoch_d))

    full_reference = _summarize_window(dataset, params, trade_dates, reference_filter, management)
    full_candidate = _summarize_window(dataset, params, trade_dates, candidate_filter, management)

    summary = {
        "reference_tier2a": full_reference,
        "candidate_stoch_d_centerline": full_candidate,
        "walkforward_70_30": {
            "reference_train": _summarize_window(dataset, params, train_dates, reference_filter, management),
            "reference_test": _summarize_window(dataset, params, test_dates, reference_filter, management),
            "candidate_train": _summarize_window(dataset, params, train_dates, candidate_filter, management),
            "candidate_test": _summarize_window(dataset, params, test_dates, candidate_filter, management),
        },
        "recent_windows": {
            "reference_60d": _summarize_window(dataset, params, recent_60, reference_filter, management),
            "candidate_60d": _summarize_window(dataset, params, recent_60, candidate_filter, management),
            "reference_30d": _summarize_window(dataset, params, recent_30, reference_filter, management),
            "candidate_30d": _summarize_window(dataset, params, recent_30, candidate_filter, management),
            "reference_10d": _summarize_window(dataset, params, recent_10, reference_filter, management),
            "candidate_10d": _summarize_window(dataset, params, recent_10, candidate_filter, management),
        },
        "notes": [
            "This validation checks whether the surprisingly strong stochastic D centerline agreement is robust enough to displace the strengthened Tier 2A reference.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
