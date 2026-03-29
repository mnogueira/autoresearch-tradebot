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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_hybrid_split_followups_20260329")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    recent_60 = trade_dates[-60:]

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_long, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    tier2a_short, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=-1)
    tier3_long, _ = _run_variant(dataset, trade_dates, tier3_management, direction=1)
    tier3_short, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)

    hybrid_l2s3 = _combined_trades(tier2a_long, tier3_short)
    hybrid_l3s2 = _combined_trades(tier3_long, tier2a_short)

    variants = [
        _variant_payload(
            "tier2a_long_only",
            "Strengthened Tier 2A using only long entries.",
            tier2a_long,
            trade_dates,
            {"management": {"min_minutes_between_entries": 28}, "direction": "long_only"},
        ),
        _variant_payload(
            "tier2a_short_only",
            "Strengthened Tier 2A using only short entries.",
            tier2a_short,
            trade_dates,
            {"management": {"min_minutes_between_entries": 28}, "direction": "short_only"},
        ),
        _variant_payload(
            "tier3_long_only",
            "Strengthened Tier 3 using only long entries.",
            tier3_long,
            trade_dates,
            {"management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150}, "direction": "long_only"},
        ),
        _variant_payload(
            "tier3_short_only",
            "Strengthened Tier 3 using only short entries.",
            tier3_short,
            trade_dates,
            {"management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150}, "direction": "short_only"},
        ),
        _variant_payload(
            "hybrid_tier2a_long_tier3_short",
            "Use strengthened Tier 2A longs and strengthened Tier 3 shorts.",
            hybrid_l2s3,
            trade_dates,
            {
                "long_branch": {"management": {"min_minutes_between_entries": 28}, "direction": "long_only"},
                "short_branch": {
                    "management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150},
                    "direction": "short_only",
                },
            },
        ),
        _variant_payload(
            "hybrid_tier3_long_tier2a_short",
            "Use strengthened Tier 3 longs and strengthened Tier 2A shorts.",
            hybrid_l3s2,
            trade_dates,
            {
                "long_branch": {
                    "management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150},
                    "direction": "long_only",
                },
                "short_branch": {"management": {"min_minutes_between_entries": 28}, "direction": "short_only"},
            },
        ),
    ]

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

    top_name = str(variants[0]["name"])
    top_trades = hybrid_l2s3 if top_name == "hybrid_tier2a_long_tier3_short" else hybrid_l3s2 if top_name == "hybrid_tier3_long_tier2a_short" else tier2a_long if top_name == "tier2a_long_only" else tier2a_short if top_name == "tier2a_short_only" else tier3_long if top_name == "tier3_long_only" else tier3_short
    recent_top = filter_trades_to_dates(top_trades, recent_60)

    summary = {
        "variants": variants,
        "top_variant_recent_60d": _variant_payload(
            f"{top_name}_recent60",
            "Recent 60-trading-day readout for the top directional sleeve/hybrid in this split scout.",
            recent_top,
            recent_60,
            {},
        ),
        "notes": [
            "Lightweight follow-up after the full directional hybrid scout timed out.",
            "Tests only directional sleeves and recombined long/short hybrids on the strengthened Tier 2A and Tier 3 lines.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
