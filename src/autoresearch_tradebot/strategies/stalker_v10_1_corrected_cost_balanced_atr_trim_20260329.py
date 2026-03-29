from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block
from .stalker_v10_1_discrete_strength_sizing_followups_20260329 import _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_balanced_atr_trim_20260329")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )

    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
    )
    management = ManagementConfig(min_minutes_between_entries=60)

    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    threshold = prior_day_atr14.rolling(60, min_periods=20).quantile(2 / 3)
    size_map = pd.Series(1.0, index=prior_day_atr14.index)
    size_map.loc[prior_day_atr14 > threshold] = 0.75

    scaled = trades.copy()
    if not scaled.empty:
        weights = pd.to_datetime(scaled["session_date"]).dt.normalize().map(size_map).fillna(1.0).astype(float)
        scaled["pnl_brl"] = scaled["pnl_brl"].astype(float) * weights.to_numpy(dtype=float)
        if "pnl_points" in scaled.columns:
            scaled["pnl_points"] = scaled["pnl_points"].astype(float) * weights.to_numpy(dtype=float)

    metrics = calculate_metrics(scaled, trade_dates)
    payload = {
        "name": "tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_topatr_0p75x",
        "rule": "Corrected-cost balanced simplified branch with 0.75x size on top ATR tercile days.",
        "metrics": metrics,
        **_risk_block(scaled, trade_dates),
        "params": {
            "params": asdict(params),
            "management": asdict(management),
            "top_atr_size_multiplier": 0.75,
        },
    }

    summary = {
        "variant": payload,
        "walkforward_70_30": {
            "train": _subset_block(scaled, train_dates),
            "test": _subset_block(scaled, test_dates),
        },
        "recent_windows": {
            "recent_60d": _subset_block(scaled, recent_60),
            "recent_30d": _subset_block(scaled, recent_30),
            "recent_10d": _subset_block(scaled, recent_10),
        },
        "notes": [
            "Research-only ATR-trim overlay on the corrected-cost balanced branch.",
            "Goal: check whether trimming the hottest ATR regime beats hard ATR exclusion without needing a full advanced sleeve.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
