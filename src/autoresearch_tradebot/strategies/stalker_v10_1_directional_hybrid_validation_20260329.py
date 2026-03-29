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
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_hybrid_validation_20260329")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    full_long, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    full_short, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)
    full_trades = _combined_trades(full_long, full_short)

    train_long, _ = _run_variant(dataset, train_dates, tier2a_management, direction=1)
    train_short, _ = _run_variant(dataset, train_dates, tier3_management, direction=-1)
    train_trades = _combined_trades(train_long, train_short)

    test_long, _ = _run_variant(dataset, test_dates, tier2a_management, direction=1)
    test_short, _ = _run_variant(dataset, test_dates, tier3_management, direction=-1)
    test_trades = _combined_trades(test_long, test_short)

    summary = {
        "variant_name": "hybrid_tier2a_long_tier3_short",
        "full_sample": _variant_payload(
            "hybrid_tier2a_long_tier3_short",
            "Strengthened Tier 2A longs plus strengthened Tier 3 shorts.",
            full_trades,
            trade_dates,
            {
                "long_branch": {"management": {"min_minutes_between_entries": 28}, "direction": "long_only"},
                "short_branch": {
                    "management": {"min_minutes_between_entries": 25, "max_bars_in_trade": 150},
                    "direction": "short_only",
                },
            },
        ),
        "walkforward_70_30": {
            "train": _variant_payload(
                "hybrid_tier2a_long_tier3_short_train",
                "Train slice.",
                train_trades,
                train_dates,
                {},
            ),
            "test": _variant_payload(
                "hybrid_tier2a_long_tier3_short_test",
                "Test slice.",
                test_trades,
                test_dates,
                {},
            ),
        },
        "recent_60d": _variant_payload(
            "hybrid_tier2a_long_tier3_short_recent60",
            "Recent 60-trading-day slice.",
            filter_trades_to_dates(full_trades, recent_60),
            recent_60,
            {},
        ),
        "recent_30d": _variant_payload(
            "hybrid_tier2a_long_tier3_short_recent30",
            "Recent 30-trading-day slice.",
            filter_trades_to_dates(full_trades, recent_30),
            recent_30,
            {},
        ),
        "recent_10d": _variant_payload(
            "hybrid_tier2a_long_tier3_short_recent10",
            "Recent 10-trading-day slice.",
            filter_trades_to_dates(full_trades, recent_10),
            recent_10,
            {},
        ),
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
