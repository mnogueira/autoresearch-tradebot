from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_combo_volume_ema_hourmap_20260329 import _build_m15_ema20_state, _m15_state_filter
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


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_structural_followups_20260329")


def _build_params():
    return replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )


def _build_combo_filter(dataset: V10Dataset):
    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    threshold = prior_day_atr14.rolling(60, min_periods=20).quantile(2 / 3)
    allowed_long_dates = set(pd.Index(prior_day_atr14.index[(prior_day_atr14 <= threshold) | threshold.isna()]))

    return _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
        _directional_filter(allowed_long_dates, {10, 11, 12}),
    )


def _resample_to_5m(dataset: V10Dataset) -> V10Dataset:
    frame = dataset.bars_m1.copy()
    agg: dict[str, str] = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    if "Spread" in frame.columns:
        agg["Spread"] = "last"
    if "RealVolume" in frame.columns:
        agg["RealVolume"] = "sum"
    bars_5m = frame.resample("5min").agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
    return V10Dataset(bars_5m)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = _build_params()
    management = ManagementConfig(min_minutes_between_entries=60)

    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_3m = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    combo_filter = _build_combo_filter(dataset)
    combo_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=combo_filter,
        management=management,
    )

    ema_state = _build_m15_ema20_state(dataset)
    dual_tf_filter = _combine_filters(combo_filter, _m15_state_filter(ema_state))
    dual_tf_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=dual_tf_filter,
        management=management,
    )

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    atr20_mean = prior_day_atr14.rolling(20, min_periods=10).mean()
    high_atr_dates = pd.Index(prior_day_atr14.index[(prior_day_atr14 > atr20_mean) | atr20_mean.isna()])
    high_atr_filter = _combine_filters(combo_filter, _date_filter(_date_set(high_atr_dates)))
    high_atr_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=high_atr_filter,
        management=management,
    )

    dataset_5m = _resample_to_5m(dataset)
    trade_dates_5m = dataset_5m.trade_dates
    train_dates_5m, test_dates_5m = split_dates(trade_dates_5m, 0.7)
    recent_3m_5m = trade_dates_5m[trade_dates_5m >= pd.Timestamp("2026-01-01")]
    recent_60_5m = trade_dates_5m[-60:]
    recent_30_5m = trade_dates_5m[-30:]
    recent_10_5m = trade_dates_5m[-10:]
    combo_filter_5m = _build_combo_filter(dataset_5m)
    m5_trades, _ = run_backtest_with_management(
        dataset=dataset_5m,
        params=params,
        trade_dates=trade_dates_5m,
        entry_filter=combo_filter_5m,
        management=management,
    )

    summary = {
        "combo_reference": _variant_payload(
            name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_prune_longs_topatr33_shorts_10_11_12",
            rule="Corrected-cost stacked combo reference.",
            trades=combo_trades,
            trade_dates=trade_dates,
            params={"params": asdict(params), "management": asdict(management)},
        ),
        "m5_proxy_combo": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_m5_proxy",
                rule="Resample to 5-minute bars and run the stacked combo logic as a lower-frequency proxy.",
                trades=m5_trades,
                trade_dates=trade_dates_5m,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(m5_trades, train_dates_5m),
                "test": _subset_block(m5_trades, test_dates_5m),
            },
            "recent_windows": {
                "recent_3m": _subset_block(m5_trades, recent_3m_5m),
                "recent_60d": _subset_block(m5_trades, recent_60_5m),
                "recent_30d": _subset_block(m5_trades, recent_30_5m),
                "recent_10d": _subset_block(m5_trades, recent_10_5m),
            },
        },
        "dual_timeframe_ema20": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_m15_ema20_filter",
                rule="Corrected-cost stacked combo plus prior completed M15 close above EMA20 for longs and below EMA20 for shorts.",
                trades=dual_tf_trades,
                trade_dates=trade_dates,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(dual_tf_trades, train_dates),
                "test": _subset_block(dual_tf_trades, test_dates),
            },
            "recent_windows": {
                "recent_60d": _subset_block(dual_tf_trades, recent_60),
                "recent_30d": _subset_block(dual_tf_trades, recent_30),
                "recent_10d": _subset_block(dual_tf_trades, recent_10),
            },
        },
        "recent_3m_combo": _subset_block(combo_trades, recent_3m),
        "daily_atr_above_20d_mean": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_daily_atr_above_20d_mean",
                rule="Only trade on days when prior-day ATR14 is above its rolling 20-day mean.",
                trades=high_atr_trades,
                trade_dates=trade_dates,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(high_atr_trades, train_dates),
                "test": _subset_block(high_atr_trades, test_dates),
            },
            "recent_windows": {
                "recent_60d": _subset_block(high_atr_trades, recent_60),
                "recent_30d": _subset_block(high_atr_trades, recent_30),
                "recent_10d": _subset_block(high_atr_trades, recent_10),
            },
        },
        "notes": [
            "Structural follow-up batch around the corrected-cost stacked combo.",
            "Covers an M5 proxy, a dual-timeframe EMA trend filter, a recent three-month regime slice, and a simple high-ATR regime gate.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
