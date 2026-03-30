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
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file


OUTPUT_DIR = artifact_output_dir(
    "stalker_v10_1_corrected_cost_short_only_hours_rolling_walkforward_20260329"
)


def _direction_filter(wanted_direction: int):
    wanted = int(wanted_direction)
    return lambda context: int(context.get("direction", 0)) == wanted


def _build_trade_dates(dataset: V10Dataset) -> pd.Index:
    trade_dates = dataset.trade_dates
    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    return pd.Index(trade_dates).intersection(non_last1_dates).sort_values()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = _build_trade_dates(dataset)

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )
    entry_filter = _combine_filters(
        session_filter({10, 11, 12}),
        _direction_filter(-1),
    )
    management = ManagementConfig(min_minutes_between_entries=60)

    full_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    train_len = 252
    test_len = 126
    fold_step = 126
    folds: list[dict] = []
    fold_number = 1
    start = 0
    while start + train_len + test_len <= len(trade_dates):
        train_dates = trade_dates[start : start + train_len]
        test_dates = trade_dates[start + train_len : start + train_len + test_len]
        train_block = _subset_block(full_trades, train_dates)
        test_block = _subset_block(full_trades, test_dates)
        folds.append(
            {
                "fold": fold_number,
                "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
                "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
                "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
                "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
                "train": train_block,
                "test": test_block,
                "test_pass": bool(
                    float(test_block["metrics"]["net_profit_brl"]) > 0.0
                    and float(test_block["metrics"]["profit_factor"]) > 1.0
                ),
            }
        )
        fold_number += 1
        start += fold_step

    pass_count = sum(1 for fold in folds if fold["test_pass"])
    summary = {
        "variant": _variant_payload(
            name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_short_only_10_11_12",
            rule="Corrected-cost short-only branch restricted to hours 10/11/12.",
            trades=full_trades,
            trade_dates=trade_dates,
            params={"params": asdict(params), "management": asdict(management)},
        ),
        "rolling_walkforward": {
            "train_days_per_fold": train_len,
            "test_days_per_fold": test_len,
            "fold_step_days": fold_step,
            "fold_count": len(folds),
            "test_pass_count": pass_count,
            "test_pass_rate": round(pass_count / len(folds), 4) if folds else 0.0,
            "folds": folds,
        },
        "notes": [
            "Rolling walk-forward for the strongest corrected-cost short-only timing sleeve.",
            "Goal: compare sleeve robustness against the stronger balanced side-specific combo.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
