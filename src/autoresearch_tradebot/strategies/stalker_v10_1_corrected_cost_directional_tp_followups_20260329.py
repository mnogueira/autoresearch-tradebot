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


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_directional_tp_followups_20260329")


def _direction_filter(wanted_direction: int):
    wanted = int(wanted_direction)
    return lambda context: int(context.get("direction", 0)) == wanted


def _combined_trades(*trade_frames: pd.DataFrame) -> pd.DataFrame:
    active = [frame for frame in trade_frames if frame is not None and not frame.empty]
    if not active:
        return pd.DataFrame()
    combined = pd.concat(active, ignore_index=True)
    return combined.sort_values(["session_date", "entry_time", "direction"], kind="stable").reset_index(drop=True)


def _run_direction(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    *,
    direction: int,
    tp_mult: float,
    management: ManagementConfig,
) -> pd.DataFrame:
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=tp_mult,
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
        management=management,
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

    management = ManagementConfig(min_minutes_between_entries=60)
    variants: list[dict] = []

    balanced_reference = _combined_trades(
        _run_direction(dataset, trade_dates, direction=1, tp_mult=0.48, management=management),
        _run_direction(dataset, trade_dates, direction=-1, tp_mult=0.48, management=management),
    )
    variants.append(
        _variant_payload(
            name="balanced_reference_sl1p0_tp0p48_cd60_skipfriday_skiplast1",
            rule="Balanced corrected-cost reference using TP 0.48 on both directions.",
            trades=balanced_reference,
            trade_dates=trade_dates,
            params={"long_tp": 0.48, "short_tp": 0.48, "management": asdict(management)},
        )
    )

    best_name = ""
    best_score = float("-inf")
    best_train = {}
    best_test = {}
    best_recent = {}

    combos = [
        ("hybrid_long_tp0p42_short_tp0p48", 0.42, 0.48),
        ("hybrid_long_tp0p42_short_tp0p54", 0.42, 0.54),
        ("hybrid_long_tp0p48_short_tp0p54", 0.48, 0.54),
    ]
    for name, long_tp, short_tp in combos:
        long_trades = _run_direction(dataset, trade_dates, direction=1, tp_mult=long_tp, management=management)
        short_trades = _run_direction(dataset, trade_dates, direction=-1, tp_mult=short_tp, management=management)
        trades = _combined_trades(long_trades, short_trades)
        payload = _variant_payload(
            name=name,
            rule=f"Direction-aware corrected-cost hybrid with long TP {long_tp:.2f} and short TP {short_tp:.2f}.",
            trades=trades,
            trade_dates=trade_dates,
            params={"long_tp": long_tp, "short_tp": short_tp, "management": asdict(management)},
        )
        variants.append(payload)
        score = float(payload["sortino_weighted_composite"])
        if score > best_score:
            best_score = score
            best_name = name
            train_trades = _combined_trades(
                _run_direction(dataset, train_dates, direction=1, tp_mult=long_tp, management=management),
                _run_direction(dataset, train_dates, direction=-1, tp_mult=short_tp, management=management),
            )
            test_trades = _combined_trades(
                _run_direction(dataset, test_dates, direction=1, tp_mult=long_tp, management=management),
                _run_direction(dataset, test_dates, direction=-1, tp_mult=short_tp, management=management),
            )
            best_train = _subset_block(train_trades, train_dates)
            best_test = _subset_block(test_trades, test_dates)
            best_recent = {
                "recent_60d": _subset_block(filter_trades_to_dates(trades, recent_60), recent_60),
                "recent_30d": _subset_block(filter_trades_to_dates(trades, recent_30), recent_30),
                "recent_10d": _subset_block(filter_trades_to_dates(trades, recent_10), recent_10),
            }

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

    summary = {
        "variants": variants,
        "best_hybrid_walkforward_70_30": {
            "variant_name": best_name,
            "train": best_train,
            "test": best_test,
        },
        "best_hybrid_recent_windows": {
            "variant_name": best_name,
            **best_recent,
        },
        "notes": [
            "Corrected-cost direction-aware TP probe after longs proved weaker than shorts.",
            "Research-only sleeve routing: long and short branches are simulated independently, then combined.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
