from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_directional_hybrid_followups_20260329 import _combined_trades, _run_variant
from .stalker_v10_1_roc_agreement_followups import _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_weekday_diagnostics_20260329")

WEEKDAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
}


def _weekday_block(trades: pd.DataFrame, trade_dates: pd.Index, weekday: int) -> dict:
    weekday_dates = pd.Index([value for value in trade_dates if pd.Timestamp(value).dayofweek == int(weekday)])
    weekday_trades = filter_trades_to_dates(trades, weekday_dates)
    return {
        "metrics": calculate_metrics(weekday_trades, weekday_dates),
        **_risk_block(weekday_trades, weekday_dates),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    recent_60 = trade_dates[-60:]

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_long, _ = _run_variant(dataset, trade_dates, tier2a_management, direction=1)
    tier3_short, _ = _run_variant(dataset, trade_dates, tier3_management, direction=-1)
    hybrid = _combined_trades(tier2a_long, tier3_short)

    summary = {
        "references": {
            "tier2a_long_only": {
                "metrics": calculate_metrics(tier2a_long, trade_dates),
                **_risk_block(tier2a_long, trade_dates),
            },
            "tier3_short_only": {
                "metrics": calculate_metrics(tier3_short, trade_dates),
                **_risk_block(tier3_short, trade_dates),
            },
            "directional_hybrid": {
                "metrics": calculate_metrics(hybrid, trade_dates),
                **_risk_block(hybrid, trade_dates),
            },
        },
        "weekday_breakdown": {
            "tier2a_long_only": {WEEKDAY_NAMES[idx]: _weekday_block(tier2a_long, trade_dates, idx) for idx in range(5)},
            "tier3_short_only": {WEEKDAY_NAMES[idx]: _weekday_block(tier3_short, trade_dates, idx) for idx in range(5)},
            "directional_hybrid": {WEEKDAY_NAMES[idx]: _weekday_block(hybrid, trade_dates, idx) for idx in range(5)},
        },
        "recent_60d_breakdown": {
            "directional_hybrid": {WEEKDAY_NAMES[idx]: _weekday_block(hybrid, recent_60, idx) for idx in range(5)},
        },
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
