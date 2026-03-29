from __future__ import annotations

import json

from ..common.paths import artifact_output_dir
from .stalker_v10_1_directional_hybrid_followups_20260329 import (
    _combined_trades,
    _run_variant,
    _variant_payload,
)
from .stalker_v10_1_session_execution_refinement import ManagementConfig
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_hybrid_local_refine_20260329")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    recent_60 = trade_dates[-60:]

    long_variants: dict[int, tuple] = {}
    for cooldown in (25, 28, 30):
        management = ManagementConfig(min_minutes_between_entries=cooldown)
        long_variants[cooldown] = _run_variant(dataset, trade_dates, management, direction=1)

    short_variants: dict[int, tuple] = {}
    for max_hold in (120, 150, 180):
        management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=max_hold)
        short_variants[max_hold] = _run_variant(dataset, trade_dates, management, direction=-1)

    variants = []
    best_name = ""
    best_trades = None
    best_composite = float("-inf")

    for long_cooldown, (long_trades, _) in long_variants.items():
        for short_hold, (short_trades, _) in short_variants.items():
            combined = _combined_trades(long_trades, short_trades)
            variant = _variant_payload(
                f"hybrid_long_cd{long_cooldown}_short_hold{short_hold}",
                (
                    f"Strengthened Tier 2A long-only branch with cooldown {long_cooldown}m "
                    f"plus strengthened Tier 3 short-only branch with max-hold {short_hold}m."
                ),
                combined,
                trade_dates,
                {
                    "long_branch": {
                        "management": {"min_minutes_between_entries": long_cooldown},
                        "direction": "long_only",
                    },
                    "short_branch": {
                        "management": {"min_minutes_between_entries": 25, "max_bars_in_trade": short_hold},
                        "direction": "short_only",
                    },
                },
            )
            variants.append(variant)
            composite = float(variant["sortino_weighted_composite"])
            if composite > best_composite:
                best_composite = composite
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
            "Recent 60-trading-day readout for the best local directional sleeve refinement.",
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
            "Local refinement of the best directional sleeve discovered in the split scout.",
            "Long-side cooldown and short-side max-hold are swept separately, then recombined without rerunning the full grid.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
