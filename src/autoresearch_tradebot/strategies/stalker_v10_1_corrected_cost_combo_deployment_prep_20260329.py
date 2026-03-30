from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_longatr_shorthours_combo_20260329 import _directional_filter
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_combo_deployment_prep_20260329")


def _daily_stats(trades: pd.DataFrame) -> dict[str, float | str]:
    if trades.empty:
        return {
            "mean_daily_pnl_brl": 0.0,
            "std_daily_pnl_brl": 0.0,
            "worst_day_brl": 0.0,
            "worst_day_date": "",
            "best_day_brl": 0.0,
            "best_day_date": "",
            "active_day_mean_pnl_brl": 0.0,
        }
    daily = trades.groupby("session_date", sort=True)["pnl_brl"].sum()
    worst_day_date = str(daily.idxmin())
    best_day_date = str(daily.idxmax())
    return {
        "mean_daily_pnl_brl": round(float(daily.mean()), 2),
        "std_daily_pnl_brl": round(float(daily.std(ddof=0)), 2),
        "worst_day_brl": round(float(daily.min()), 2),
        "worst_day_date": worst_day_date,
        "best_day_brl": round(float(daily.max()), 2),
        "best_day_date": best_day_date,
        "active_day_mean_pnl_brl": round(float(daily.mean()), 2),
    }


def _trade_rate(trades: pd.DataFrame, trading_days: int) -> dict[str, float]:
    total_trades = int(len(trades))
    active_days = int(trades["session_date"].nunique()) if not trades.empty else 0
    return {
        "avg_trades_per_all_trading_day": round(total_trades / trading_days, 4) if trading_days > 0 else 0.0,
        "avg_trades_per_active_day": round(total_trades / active_days, 4) if active_days > 0 else 0.0,
        "active_days": active_days,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)

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

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    threshold = prior_day_atr14.rolling(60, min_periods=20).quantile(2 / 3)
    allowed_long_dates = set(pd.Index(prior_day_atr14.index[(prior_day_atr14 <= threshold) | threshold.isna()]))

    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
        _directional_filter(allowed_long_dates, {10, 11, 12}),
    )
    management = ManagementConfig(min_minutes_between_entries=60)

    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    summary = {
        "variant": _variant_payload(
            name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_prune_longs_topatr33_shorts_10_11_12",
            rule="Corrected-cost stacked combo deployment-prep reference.",
            trades=trades,
            trade_dates=trade_dates,
            params={"params": asdict(params), "management": asdict(management)},
        ),
        "walkforward_70_30": {
            "train": _subset_block(trades, train_dates),
            "test": _subset_block(trades, test_dates),
        },
        "daily_stats": _daily_stats(trades),
        "trade_rate": _trade_rate(trades, len(trade_dates)),
        "notes": [
            "Deployment-prep sheet for the corrected-cost stacked combo leader.",
            "Includes daily PnL distribution and trade-rate summary for Monday ops planning.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
