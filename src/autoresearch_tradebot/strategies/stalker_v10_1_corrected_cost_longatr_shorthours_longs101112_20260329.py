from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
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


OUTPUT_DIR = artifact_output_dir(
    "stalker_v10_1_corrected_cost_longatr_shorthours_longs101112_20260329"
)


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


def _common_params():
    return replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )


def _non_last1_dates(dataset: V10Dataset) -> pd.Index:
    rollover_daily = contract_rollover_buckets(dataset)
    return pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])


def _allowed_long_dates(dataset: V10Dataset) -> pd.Index:
    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    threshold = prior_day_atr14.rolling(60, min_periods=20).quantile(2 / 3)
    return pd.Index(prior_day_atr14.index[(prior_day_atr14 <= threshold) | threshold.isna()])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    common_dates = _date_filter(_date_set(_non_last1_dates(dataset)))
    common_params = _common_params()
    management = ManagementConfig(min_minutes_between_entries=60)

    long_filter = _combine_filters(
        session_filter({10, 11, 12}),
        common_dates,
        _date_filter(_date_set(_allowed_long_dates(dataset))),
        _direction_filter(1),
    )
    short_filter = _combine_filters(
        session_filter({10, 11, 12}),
        common_dates,
        _direction_filter(-1),
    )

    long_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=common_params,
        trade_dates=trade_dates,
        entry_filter=long_filter,
        management=management,
    )
    short_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=common_params,
        trade_dates=trade_dates,
        entry_filter=short_filter,
        management=management,
    )
    trades = _combined_trades(long_trades, short_trades)

    payload = _variant_payload(
        name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_prune_longs_topatr33_longs101112_shorts101112",
        rule="Corrected-cost branch that prunes longs on top ATR days and restricts both directions to hours 10/11/12.",
        trades=trades,
        trade_dates=trade_dates,
        params={"params": asdict(common_params), "management": asdict(management)},
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
            "Corrected-cost static side-specific hours follow-up.",
            "Goal: remove the weaker long 14h sleeve while keeping the current short-hours restriction.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
