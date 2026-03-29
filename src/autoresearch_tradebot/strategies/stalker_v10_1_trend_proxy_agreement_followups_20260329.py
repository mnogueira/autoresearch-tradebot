from __future__ import annotations

import json
from dataclasses import replace

from ta.trend import AroonIndicator, CCIIndicator

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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_trend_proxy_agreement_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _make_centerline_filter(array, threshold: float = 0.0):
    def allow(context):
        idx = int(context["dataset_index"])
        value = float(array[idx])
        if value != value:
            return False
        direction = int(context["direction"])
        return value >= threshold if direction == 1 else value <= threshold

    return allow


def _make_pair_filter(first, second):
    def allow(context):
        idx = int(context["dataset_index"])
        first_value = float(first[idx])
        second_value = float(second[idx])
        if first_value != first_value or second_value != second_value:
            return False
        direction = int(context["direction"])
        return first_value >= second_value if direction == 1 else second_value >= first_value

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
    high = bars["High"].astype(float)
    low = bars["Low"].astype(float)
    close = bars["Close"].astype(float)

    cci = CCIIndicator(high=high, low=low, close=close, window=20).cci().shift(1).to_numpy(dtype=float)
    aroon = AroonIndicator(high=high, low=low, window=25)
    aroon_up = aroon.aroon_up().shift(1).to_numpy(dtype=float)
    aroon_down = aroon.aroon_down().shift(1).to_numpy(dtype=float)

    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)

    variants = []
    best_variant = None

    for name, indicator_filter in (
        ("cci_centerline", _make_centerline_filter(cci)),
        ("aroon_dominance", _make_pair_filter(aroon_up, aroon_down)),
    ):
        entry_filter = _combine_filters(base_filter, roc5_filter, indicator_filter)
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        variant = {
            "name": f"tier2a_{name}",
            "rule": f"Strengthened Tier 2A with {name} directional confirmation.",
            "metrics": metrics,
            **_risk_block(trades, trade_dates),
            "params": {
                "trend_proxy_variant": name,
                "roc_agreement_bars": 5,
                "ATR_Length": 10,
                "NumDaysToConsiderPreviousContractMARange": 2,
                "min_minutes_between_entries": 28,
            },
        }
        variants.append(variant)
        if best_variant is None or float(variant["sortino_weighted_composite"]) > float(best_variant["sortino_weighted_composite"]):
            best_variant = variant

    reference_filter = _combine_filters(base_filter, roc5_filter)
    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=reference_filter,
        management=management,
    )

    summary = {
        "reference_tier2a": {
            "metrics": reference_metrics,
            **_risk_block(reference_trades, trade_dates),
        },
        "variants": variants,
        "best_variant": best_variant,
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if best_variant is not None:
        row = _leaderboard_row(best_variant, summary_path)
        row["family"] = "stalker_v10_1_trend_proxy_agreement_followup"
        row["screening_method"] = "trend_proxy_agreement_followup"
        row["comparison_tier"] = "research_exact"
        update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
