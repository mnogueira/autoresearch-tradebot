from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates


def _output_dir(sl_mult: float):
    suffix = str(sl_mult).replace(".", "p")
    return artifact_output_dir(f"stalker_v10_1_corrected_cost_survivor_sl{suffix}_20260329")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sl-mult", type=float, required=True)
    args = parser.parse_args()

    output_dir = _output_dir(args.sl_mult)
    output_dir.mkdir(parents=True, exist_ok=True)

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
        SL_ATRMultiplier=args.sl_mult,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )

    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _make_roc_filter(dataset, 5),
        _date_filter(_date_set(non_last1_dates)),
    )
    management = ManagementConfig(min_minutes_between_entries=60, max_bars_in_trade=150)

    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    payload = _variant_payload(
        name=f"tier2a_corrected_sl{str(args.sl_mult).replace('.', 'p')}_tp048_cd60_skipfriday_skiplast1_maxhold150",
        rule=(
            "Corrected-cost strengthened Tier 2A with TP 0.48, 60-minute cooldown, Friday skipped, "
            f"last contract day skipped, 150-minute max-hold, and SL {args.sl_mult:.2f}."
        ),
        trades=trades,
        trade_dates=trade_dates,
        params={"params": asdict(params), "management": asdict(management)},
    )

    summary = {
        "variant": payload,
        "walkforward_70_30": {
            "train": _subset_block(trades, train_dates),
            "test": _subset_block(trades, test_dates),
        },
        "recent_windows": {
            "recent_60d": _subset_block(trades, recent_60),
            "recent_30d": _subset_block(trades, recent_30),
            "recent_10d": _subset_block(trades, recent_10),
        },
        "notes": [
            "Single-variant stop-width probe around the best corrected-cost static survivor.",
            "Goal: isolate whether a wider stop improves cost-adjusted returns without changing the widened TP and contract-cycle pruning.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
