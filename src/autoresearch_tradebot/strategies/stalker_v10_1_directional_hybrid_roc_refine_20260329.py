from __future__ import annotations

import json
from dataclasses import replace
from typing import Callable

from ..common.paths import artifact_output_dir
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _variant_payload
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_hybrid_roc_refine_20260329")


def _combine_filters(*filters: Callable[[dict[str, int]], bool] | None) -> Callable[[dict[str, int]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, int]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _direction_filter(direction: int) -> Callable[[dict[str, int]], bool]:
    allowed = int(direction)
    return lambda context: int(context["direction"]) == allowed


def _run_directional_branch(
    dataset: V10Dataset,
    trade_dates,
    management: ManagementConfig,
    direction: int,
    roc_bars: int,
):
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _make_roc_filter(dataset, int(roc_bars)),
        _direction_filter(int(direction)),
    )
    return run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    recent_60 = trade_dates[-60:]

    long_management = ManagementConfig(min_minutes_between_entries=28)
    short_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    long_variants = {}
    for roc_bars in (4, 5, 6):
        long_variants[roc_bars] = _run_directional_branch(
            dataset=dataset,
            trade_dates=trade_dates,
            management=long_management,
            direction=1,
            roc_bars=roc_bars,
        )

    short_variants = {}
    for roc_bars in (4, 5, 6):
        short_variants[roc_bars] = _run_directional_branch(
            dataset=dataset,
            trade_dates=trade_dates,
            management=short_management,
            direction=-1,
            roc_bars=roc_bars,
        )

    variants = []
    best_name = ""
    best_trades = None
    best_score = float("-inf")

    for long_roc, (long_trades, _) in long_variants.items():
        for short_roc, (short_trades, _) in short_variants.items():
            combined = _combined_trades(long_trades, short_trades)
            variant = _variant_payload(
                f"hybrid_long_roc{long_roc}_short_roc{short_roc}",
                (
                    f"Strengthened Tier 2A longs with ROC({long_roc}) agreement plus "
                    f"strengthened Tier 3 shorts with ROC({short_roc}) agreement."
                ),
                combined,
                trade_dates,
                {
                    "long_branch": {
                        "management": {"min_minutes_between_entries": 28},
                        "direction": "long_only",
                        "roc_agreement_bars": int(long_roc),
                    },
                    "short_branch": {
                        "management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150},
                        "direction": "short_only",
                        "roc_agreement_bars": int(short_roc),
                    },
                },
            )
            variants.append(variant)
            score = float(variant["sortino_weighted_composite"])
            if score > best_score:
                best_score = score
                best_name = str(variant["name"])
                best_trades = combined

    variants.sort(
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(variants, start=1):
        row["batch_rank"] = rank

    recent_best = (
        _variant_payload(
            f"{best_name}_recent60",
            "Recent 60-trading-day readout for the best directional ROC hybrid.",
            filter_trades_to_dates(best_trades, recent_60),
            recent_60,
            {},
        )
        if best_trades is not None
        else {}
    )

    summary = {
        "variants": variants,
        "best_variant_recent_60d": recent_best,
        "notes": [
            "Directional hybrid local signal refinement.",
            "Long and short sleeves sweep ROC(4), ROC(5), and ROC(6) independently while keeping the best local management settings fixed.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
