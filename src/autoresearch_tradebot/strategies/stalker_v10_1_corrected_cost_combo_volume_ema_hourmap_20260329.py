from __future__ import annotations

import json
from dataclasses import asdict, replace

import numpy as np
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
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_combo_volume_ema_hourmap_20260329")


def _directional_filter(allowed_long_dates: set[pd.Timestamp], allowed_short_hours: set[int]):
    def _allow(context: dict) -> bool:
        direction = int(context.get("direction", 0))
        if direction == 1:
            return pd.Timestamp(context["session_date"]).normalize() in allowed_long_dates
        if direction == -1:
            return int(context["entry_hour"]) in allowed_short_hours
        return False

    return _allow


def _m15_state_filter(state_by_minute: pd.Series):
    def _allow(context: dict) -> bool:
        timestamp = pd.Timestamp(context["timestamp"])
        direction = int(context.get("direction", 0))
        state = state_by_minute.get(timestamp, 0)
        if direction == 1:
            return bool(state == 1)
        if direction == -1:
            return bool(state == -1)
        return False

    return _allow


def _build_common_objects(dataset: V10Dataset):
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

    base_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
        _directional_filter(allowed_long_dates, {10, 11, 12}),
    )
    management = ManagementConfig(min_minutes_between_entries=60)
    return params, base_filter, management


def _build_m15_volume_gate(dataset: V10Dataset, threshold_mult: float = 1.5) -> pd.Series:
    m15 = (
        dataset.bars_m1[["Volume"]]
        .resample("15min")
        .agg({"Volume": "sum"})
        .dropna()
    )
    avg_volume = m15["Volume"].rolling(20, min_periods=10).mean().shift(1)
    gate = (m15["Volume"] > (float(threshold_mult) * avg_volume)).astype(int).shift(1).fillna(0)
    minute_index = pd.DatetimeIndex(dataset.bars_m1.index)
    return gate.reindex(minute_index, method="ffill").fillna(0).astype(int)


def _build_m15_ema20_state(dataset: V10Dataset) -> pd.Series:
    m15 = (
        dataset.bars_m1[["Close"]]
        .resample("15min")
        .agg({"Close": "last"})
        .dropna()
    )
    ema20 = m15["Close"].ewm(span=20, adjust=False).mean()
    state = pd.Series(0, index=m15.index, dtype=int)
    state.loc[m15["Close"] > ema20] = 1
    state.loc[m15["Close"] < ema20] = -1
    state = state.shift(1).fillna(0).astype(int)
    minute_index = pd.DatetimeIndex(dataset.bars_m1.index)
    return state.reindex(minute_index, method="ffill").fillna(0).astype(int)


def _hour_map(trades: pd.DataFrame, trade_dates: pd.Index) -> list[dict[str, object]]:
    if trades.empty:
        return []
    frame = trades.copy()
    frame["entry_hour"] = pd.to_datetime(frame["entry_time"]).dt.hour
    rows: list[dict[str, object]] = []
    for hour, group in frame.groupby("entry_hour", sort=True):
        metrics = calculate_metrics(group.reset_index(drop=True), trade_dates)
        rows.append(
            {
                "entry_hour": int(hour),
                "total_trades": int(metrics["total_trades"]),
                "net_profit_brl": float(metrics["net_profit_brl"]),
                "profit_factor": float(metrics["profit_factor"]),
                "win_rate": float(metrics["win_rate"]),
                "avg_profit_brl": float(metrics["avg_profit_brl"]),
            }
        )
    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    params, base_filter, management = _build_common_objects(dataset)

    combo_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=management,
    )

    volume_gate = _build_m15_volume_gate(dataset, 1.5)
    volume_filter = _combine_filters(base_filter, _m15_state_filter(volume_gate))
    volume_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=volume_filter,
        management=management,
    )

    ema_state = _build_m15_ema20_state(dataset)
    ema_filter = _combine_filters(base_filter, _m15_state_filter(ema_state))
    ema_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=ema_filter,
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
        "volume_gate_1p5x": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_volume_gate_1p5x",
                rule="Corrected-cost combo plus M15 volume > 1.5x prior 20-bar average.",
                trades=volume_trades,
                trade_dates=trade_dates,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(volume_trades, train_dates),
                "test": _subset_block(volume_trades, test_dates),
            },
            "recent_windows": {
                "recent_60d": _subset_block(volume_trades, recent_60),
                "recent_30d": _subset_block(volume_trades, recent_30),
                "recent_10d": _subset_block(volume_trades, recent_10),
            },
        },
        "ema20_trend_filter": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_ema20_filter",
                rule="Corrected-cost combo plus prior completed M15 close must be above EMA20 for longs and below EMA20 for shorts.",
                trades=ema_trades,
                trade_dates=trade_dates,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(ema_trades, train_dates),
                "test": _subset_block(ema_trades, test_dates),
            },
            "recent_windows": {
                "recent_60d": _subset_block(ema_trades, recent_60),
                "recent_30d": _subset_block(ema_trades, recent_30),
                "recent_10d": _subset_block(ema_trades, recent_10),
            },
        },
        "hour_map": _hour_map(combo_trades, trade_dates),
        "notes": [
            "Corrected-cost combo diagnostics batch.",
            "Covers volume gating, EMA20 trend agreement, and the hour-by-hour PnL map for the current static leader.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
