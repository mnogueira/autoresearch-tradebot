from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_long120_short60_20260329")


def _direction_filter(wanted_direction: int):
    wanted = int(wanted_direction)
    return lambda context: int(context.get("direction", 0)) == wanted


def _combined_trades(*trade_frames: pd.DataFrame) -> pd.DataFrame:
    active = [frame for frame in trade_frames if frame is not None and not frame.empty]
    if not active:
        return pd.DataFrame()
    return pd.concat(active, ignore_index=True).sort_values(
        ["session_date", "entry_time", "direction"], kind="stable"
    ).reset_index(drop=True)


def _run_branch(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    *,
    direction: int,
    cooldown_minutes: int,
) -> pd.DataFrame:
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )
    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
        _direction_filter(direction),
    )
    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(min_minutes_between_entries=cooldown_minutes),
    )
    return trades


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    trades = _combined_trades(
        _run_branch(dataset, trade_dates, direction=1, cooldown_minutes=120),
        _run_branch(dataset, trade_dates, direction=-1, cooldown_minutes=60),
    )
    payload = _variant_payload(
        name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_long120_short60_skipfriday_skiplast1",
        rule="Corrected-cost direction-aware cooldown routing: longs at 120m cooldown, shorts at 60m cooldown.",
        trades=trades,
        trade_dates=trade_dates,
        params={
            "long_cooldown_minutes": 120,
            "short_cooldown_minutes": 60,
        },
    )

    summary = {
        "variant": payload,
        "walkforward_70_30": {
            "train": _subset_block(filter_trades_to_dates(trades, train_dates), train_dates),
            "test": _subset_block(filter_trades_to_dates(trades, test_dates), test_dates),
        },
        "recent_windows": {
            "recent_60d": _subset_block(filter_trades_to_dates(trades, recent_60), recent_60),
            "recent_30d": _subset_block(filter_trades_to_dates(trades, recent_30), recent_30),
            "recent_10d": _subset_block(filter_trades_to_dates(trades, recent_10), recent_10),
        },
        "notes": [
            "Direction-aware corrected-cost cooldown routing.",
            "Goal: slow only the weaker long sleeve while leaving the stronger short sleeve at the current local cooldown peak.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
