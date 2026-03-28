from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import optuna
import pandas as pd

from ..common.mt5_every_tick import (
    candle_bias,
    generate_every_tick_path,
    price_to_ticks,
    ticks_to_price,
)
from ..common.paths import artifact_output_dir
from .stalker_v10_python import (
    BIG_NUMBER,
    CONTINUOUS_SERIES_SYMBOL,
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    TradeRecord,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    round_to_tick,
    split_dates,
)

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_python")
TIME_SLOT_STEP_MINUTES = 5
ENTRY_WINDOW_START_MINUTES = 9 * 60
ENTRY_WINDOW_END_MINUTES = 15 * 60
PRICE_TICK_SIZE = 0.5
SPREAD_POINT_SIZE = 0.001


@dataclass(frozen=True)
class V101Params:
    ContractsPerTrade: float = 1.0
    FilterAsPercOfContractMARange: float = 0.30
    NumDaysToConsiderPreviousContractMARange: int = 5
    RetracementLevel: float = 0.25
    EntryStart_Hour: int = 10
    EntryStart_Minute: int = 0
    LastEntry_Hour: int = 15
    LastEntry_Minute: int = 0
    SkipWednesday: bool = False
    SkipHour13: bool = False
    SkipHour14: bool = False
    AllowMonday: bool = True
    AllowTuesday: bool = True
    AllowWednesday: bool = True
    AllowThursday: bool = True
    AllowFriday: bool = True
    TrendEfficiencyWindowMinutes: int = 15
    ApplyTrendEfficiencyFilterToLongs: bool = False
    ApplyTrendEfficiencyFilterToShorts: bool = False
    MinDirectionalTrendEfficiency15m: float = 0.0
    VolumeWindowMinutes: int = 15
    ApplyVolumeFilterToLongs: bool = False
    ApplyVolumeFilterToShorts: bool = False
    MinSignalVolumeWindowSum: float = 0.0
    RelativeVolumeLookbackDays: int = 20
    ApplyRelativeVolumeFilterToLongs: bool = False
    ApplyRelativeVolumeFilterToShorts: bool = False
    MinRelativeVolumeAtTime: float = 0.0
    SL_ATRMultiplier: float = 0.78
    TP_ATRMultiplier: float = 0.36
    ATRTimeFrame: int = 15
    ATR_Length: int = 20
    MarketClose_Hour: int = 18
    MarketClose_Minute: int = 0
    MinutesBeforeMarketCloseToClosePositions: int = 5


def entry_window_minutes(params: V101Params) -> tuple[int, int]:
    start_minutes = (int(params.EntryStart_Hour) * 60) + int(params.EntryStart_Minute)
    end_minutes = (int(params.LastEntry_Hour) * 60) + int(params.LastEntry_Minute)
    return start_minutes, end_minutes


def is_allowed_trading_day(timestamp: pd.Timestamp, params: V101Params) -> bool:
    weekday = timestamp.dayofweek
    if weekday == 2 and bool(params.SkipWednesday):
        return False
    if weekday == 0:
        return bool(params.AllowMonday)
    if weekday == 1:
        return bool(params.AllowTuesday)
    if weekday == 2:
        return bool(params.AllowWednesday)
    if weekday == 3:
        return bool(params.AllowThursday)
    if weekday == 4:
        return bool(params.AllowFriday)
    return False


def is_within_entry_window(timestamp: pd.Timestamp, params: V101Params) -> bool:
    if timestamp.hour == 13 and bool(params.SkipHour13):
        return False
    if timestamp.hour == 14 and bool(params.SkipHour14):
        return False
    current_minutes = (timestamp.hour * 60) + timestamp.minute
    start_minutes, end_minutes = entry_window_minutes(params)
    return start_minutes <= current_minutes <= end_minutes


def slot_to_hour_minute(slot_minutes: int) -> tuple[int, int]:
    return divmod(int(slot_minutes), 60)


def _mode_to_side_flags(mode: str) -> tuple[bool, bool]:
    normalized = str(mode).strip().lower()
    if normalized == "long":
        return True, False
    if normalized == "short":
        return False, True
    if normalized == "both":
        return True, True
    return False, False


def build_summary(
    dataset: V10Dataset,
    baseline: V101Params,
    base_metrics: dict[str, Any],
    optimization: dict[str, Any] | None,
    data_path: Path,
    train_ratio: float,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "strategy": "WDO Stalker Strategy v10.1 Time Filters GPT 5.4",
        "execution_model": "MT5 Every tick (documented support-point generator)",
        "symbol": CONTINUOUS_SERIES_SYMBOL,
        "data_source": str(dataset.bars_m1.attrs.get("source_path", data_path)),
        "dataset": {
            "start_date": pd.Timestamp(dataset.trade_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(dataset.trade_dates[-1]).date().isoformat(),
            "trading_days": int(len(dataset.trade_dates)),
        },
        "baseline_params": asdict(baseline),
        "baseline_metrics": base_metrics,
        "optimization_config": {
            "train_ratio": float(train_ratio),
            "time_slot_step_minutes": TIME_SLOT_STEP_MINUTES,
        },
    }
    if optimization is not None:
        summary["optimized_holdout"] = {
            "best_params": asdict(optimization["best_params"]),
            "best_objective": float(optimization["study"].best_value),
            "optuna_trials": int(len(optimization["study"].trials)),
            "train_metrics": optimization["train_metrics"],
            "test_metrics": optimization["test_metrics"],
        }
    return summary


def _ensure_every_tick_cache(dataset: V10Dataset) -> dict[str, np.ndarray]:
    cache = getattr(dataset, "_v101_every_tick_cache", None)
    if cache is not None:
        return cache

    bars = dataset.bars_m1
    spread_points = (
        bars["Spread"].to_numpy(dtype=float)
        if "Spread" in bars.columns
        else np.zeros(len(bars), dtype=float)
    )
    cache = {
        "timestamps": bars.index.to_numpy(dtype="datetime64[ns]"),
        "session_dates": bars["session_date"].to_numpy(dtype="datetime64[ns]"),
        "open_ticks": np.rint(bars["Open"].to_numpy(dtype=float) / PRICE_TICK_SIZE).astype(np.int32),
        "high_ticks": np.rint(bars["High"].to_numpy(dtype=float) / PRICE_TICK_SIZE).astype(np.int32),
        "low_ticks": np.rint(bars["Low"].to_numpy(dtype=float) / PRICE_TICK_SIZE).astype(np.int32),
        "close_ticks": np.rint(bars["Close"].to_numpy(dtype=float) / PRICE_TICK_SIZE).astype(np.int32),
        "volume": bars["Volume"].to_numpy(dtype=np.int32),
        "spread_ticks": np.rint((spread_points * SPREAD_POINT_SIZE) / PRICE_TICK_SIZE).astype(np.int16),
        "day_high_current_ticks": np.rint(
            bars["day_high_current"].to_numpy(dtype=float) / PRICE_TICK_SIZE
        ).astype(np.int32),
        "day_low_current_ticks": np.rint(
            bars["day_low_current"].to_numpy(dtype=float) / PRICE_TICK_SIZE
        ).astype(np.int32),
    }
    setattr(dataset, "_v101_every_tick_cache", cache)
    return cache


def _trade_slice_bounds(dataset: V10Dataset, trade_dates: pd.Index) -> tuple[int, int]:
    if len(trade_dates) == 0:
        return 0, 0

    session_dates = _ensure_every_tick_cache(dataset)["session_dates"]
    start_date = np.datetime64(pd.Timestamp(trade_dates[0]).normalize(), "ns")
    end_date = np.datetime64(pd.Timestamp(trade_dates[-1]).normalize(), "ns")
    start = int(np.searchsorted(session_dates, start_date, side="left"))
    stop = int(np.searchsorted(session_dates, end_date, side="right"))
    return start, stop


def _rolling_session_sum(values: pd.Series, session_key: pd.Series, window: int) -> pd.Series:
    min_periods = max(3, min(int(window), 10))
    return values.groupby(session_key).transform(
        lambda series: series.rolling(int(window), min_periods=min_periods).sum()
    )


def _rolling_same_minute_mean(values: pd.Series, minute_of_day: pd.Index, lookback: int) -> pd.Series:
    min_periods = max(3, min(int(lookback), 10))
    return values.groupby(minute_of_day).transform(
        lambda series: series.rolling(int(lookback), min_periods=min_periods).mean().shift(1)
    )


def _ensure_signal_strength_cache(
    dataset: V10Dataset,
    trend_window: int,
    volume_window: int,
    relative_volume_lookback: int,
) -> dict[str, np.ndarray]:
    store = getattr(dataset, "_v101_signal_strength_cache_store", None)
    if store is None:
        store = {}
        setattr(dataset, "_v101_signal_strength_cache_store", store)

    key = (int(trend_window), int(volume_window), int(relative_volume_lookback))
    cache = store.get(key)
    if cache is not None:
        return cache

    bars = dataset.bars_m1
    session_key = bars["session_date"]
    minute_of_day = pd.Index((bars.index.hour * 60) + bars.index.minute)

    prev_close = bars.groupby("session_date")["Close"].shift(1)
    close_n_bars_ago = bars.groupby("session_date")["Close"].shift(int(trend_window) + 1)
    ret_trend_raw = prev_close - close_n_bars_ago
    ret_prev = bars.groupby("session_date")["Close"].diff().groupby(session_key).shift(1)
    realized_abs = _rolling_session_sum(ret_prev.abs(), session_key, int(trend_window))
    trend_efficiency_raw = ret_trend_raw / realized_abs.replace(0.0, np.nan)

    volume_prev = bars.groupby("session_date")["Volume"].shift(1)
    signal_volume_sum = _rolling_session_sum(volume_prev, session_key, int(volume_window))
    expected_volume_same_time = _rolling_same_minute_mean(
        signal_volume_sum,
        minute_of_day,
        int(relative_volume_lookback),
    )
    relative_volume = signal_volume_sum / expected_volume_same_time.replace(0.0, np.nan)

    cache = {
        "trend_efficiency_raw": trend_efficiency_raw.to_numpy(dtype=float),
        "signal_volume_sum": signal_volume_sum.to_numpy(dtype=float),
        "relative_volume": relative_volume.to_numpy(dtype=float),
    }
    store[key] = cache
    return cache


def _passes_directional_trend_efficiency(
    direction: int,
    raw_value: float,
    params: V101Params,
) -> bool:
    if direction == 1 and not params.ApplyTrendEfficiencyFilterToLongs:
        return True
    if direction == -1 and not params.ApplyTrendEfficiencyFilterToShorts:
        return True
    if not np.isfinite(raw_value):
        return False
    directional_value = raw_value if direction == 1 else -raw_value
    return directional_value >= float(params.MinDirectionalTrendEfficiency15m)


def _passes_signal_volume(
    direction: int,
    raw_value: float,
    params: V101Params,
) -> bool:
    if direction == 1 and not params.ApplyVolumeFilterToLongs:
        return True
    if direction == -1 and not params.ApplyVolumeFilterToShorts:
        return True
    if not np.isfinite(raw_value):
        return False
    return raw_value >= float(params.MinSignalVolumeWindowSum)


def _passes_relative_volume(
    direction: int,
    raw_value: float,
    params: V101Params,
) -> bool:
    if direction == 1 and not params.ApplyRelativeVolumeFilterToLongs:
        return True
    if direction == -1 and not params.ApplyRelativeVolumeFilterToShorts:
        return True
    if not np.isfinite(raw_value):
        return False
    return raw_value >= float(params.MinRelativeVolumeAtTime)


def _is_timestamp_allowed(timestamp: pd.Timestamp, params: V101Params) -> bool:
    return is_allowed_trading_day(timestamp, params) and is_within_entry_window(timestamp, params)


def _is_valid_pending_order(direction: int, limit_tick: int, bid_tick: int, ask_tick: int) -> bool:
    if direction == 1:
        return limit_tick < ask_tick
    return limit_tick > bid_tick


def _fill_pending_order_at_tick(
    pending_order: dict[str, Any],
    bid_tick: int,
    ask_tick: int,
) -> int | None:
    direction = int(pending_order["direction"])
    limit_tick = int(pending_order["limit_tick"])
    if direction == 1 and ask_tick <= limit_tick:
        return limit_tick
    if direction == -1 and bid_tick >= limit_tick:
        return limit_tick
    return None


def _exit_position_at_tick(
    direction: int,
    bid_tick: int,
    ask_tick: int,
    stop_tick: int,
    target_tick: int,
    open_tick: bool = False,
) -> tuple[int | None, str | None]:
    if direction == 1:
        if bid_tick <= stop_tick:
            return bid_tick, "stop_gap_open" if open_tick else "stop_loss"
        if bid_tick >= target_tick:
            return bid_tick, "take_profit_gap_open" if open_tick else "take_profit"
    else:
        if ask_tick >= stop_tick:
            return ask_tick, "stop_gap_open" if open_tick else "stop_loss"
        if ask_tick <= target_tick:
            return ask_tick, "take_profit_gap_open" if open_tick else "take_profit"
    return None, None


def run_backtest(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if int(params.ATRTimeFrame) != 15:
        raise ValueError("ATRTimeFrame must be 15 to match the MQ5 v10.1 port.")

    start, stop = _trade_slice_bounds(dataset, trade_dates)
    if start >= stop:
        metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return pd.DataFrame(), metrics

    cache = _ensure_every_tick_cache(dataset)
    strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    signal_range = dataset.get_signal_range(
        params.FilterAsPercOfContractMARange,
        params.NumDaysToConsiderPreviousContractMARange,
    )
    atr_open = dataset.get_atr_current(params.ATR_Length)

    timestamps = pd.DatetimeIndex(cache["timestamps"][start:stop])
    session_dates = cache["session_dates"][start:stop]
    open_ticks = cache["open_ticks"][start:stop]
    high_ticks = cache["high_ticks"][start:stop]
    low_ticks = cache["low_ticks"][start:stop]
    close_ticks = cache["close_ticks"][start:stop]
    volume = cache["volume"][start:stop]
    spread_ticks = cache["spread_ticks"][start:stop]
    day_high_current_ticks = cache["day_high_current_ticks"][start:stop]
    day_low_current_ticks = cache["day_low_current_ticks"][start:stop]
    signal_range_slice = signal_range[start:stop]
    atr_open_slice = atr_open[start:stop]
    trend_efficiency_slice = strength_cache["trend_efficiency_raw"][start:stop]
    signal_volume_slice = strength_cache["signal_volume_sum"][start:stop]
    relative_volume_slice = strength_cache["relative_volume"][start:stop]

    minute_of_day = (timestamps.hour * 60) + timestamps.minute
    start_minutes, end_minutes = entry_window_minutes(params)
    allowed_weekdays = np.array(
        [
            bool(params.AllowMonday),
            bool(params.AllowTuesday),
            bool(params.AllowWednesday) and not bool(params.SkipWednesday),
            bool(params.AllowThursday),
            bool(params.AllowFriday),
            False,
            False,
        ],
        dtype=bool,
    )
    blocked_hours = (
        ((timestamps.hour == 13) & bool(params.SkipHour13))
        | ((timestamps.hour == 14) & bool(params.SkipHour14))
    )
    can_enter_flags = (
        allowed_weekdays[timestamps.dayofweek]
        & (minute_of_day >= start_minutes)
        & (minute_of_day <= end_minutes)
        & ~blocked_hours
    )
    cutoff_minutes = (
        (params.MarketClose_Hour * 60)
        + params.MarketClose_Minute
        - params.MinutesBeforeMarketCloseToClosePositions
    )

    trades: list[TradeRecord] = []
    previous_high_tick = 0
    previous_low_tick = price_to_ticks(BIG_NUMBER, PRICE_TICK_SIZE)
    current_date: np.datetime64 | None = None
    previous_bias = 1

    position = 0
    entry_tick = 0
    stop_tick = 0
    target_tick = 0
    entry_time = pd.NaT
    signal_time = pd.NaT
    fill_reason = ""

    pending_order: dict[str, Any] | None = None
    completed_trades_today = 0

    def append_trade(
        session_date: np.datetime64,
        exit_time: pd.Timestamp,
        exit_tick: int,
        exit_reason: str,
    ) -> None:
        nonlocal completed_trades_today
        entry_price = ticks_to_price(entry_tick, PRICE_TICK_SIZE)
        exit_price = ticks_to_price(exit_tick, PRICE_TICK_SIZE)
        stop_price = ticks_to_price(stop_tick, PRICE_TICK_SIZE)
        target_price = ticks_to_price(target_tick, PRICE_TICK_SIZE)
        pnl_points = (exit_price - entry_price) * position
        pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
        trades.append(
            TradeRecord(
                session_date=pd.Timestamp(session_date).date().isoformat(),
                signal_time=str(signal_time),
                entry_time=str(entry_time),
                exit_time=str(exit_time),
                direction="long" if position == 1 else "short",
                entry_price=entry_price,
                exit_price=float(exit_price),
                stop_price=stop_price,
                target_price=target_price,
                pnl_points=round(pnl_points, 2),
                pnl_brl=round(pnl_brl, 2),
                fill_reason=fill_reason or "active_position",
                exit_reason=exit_reason,
            )
        )
        completed_trades_today += 1

    for index in range(len(timestamps)):
        timestamp = timestamps[index]
        session_date = session_dates[index]
        bid_open_tick = int(open_ticks[index])
        ask_open_tick = bid_open_tick + int(spread_ticks[index])

        if current_date is None or session_date != current_date:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(
                    session_date=current_date,
                    exit_time=timestamp,
                    exit_tick=exit_tick,
                    exit_reason="forced_day_change",
                )

            current_date = session_date
            previous_high_tick = 0
            previous_low_tick = price_to_ticks(BIG_NUMBER, PRICE_TICK_SIZE)
            position = 0
            pending_order = None
            completed_trades_today = 0

        if position != 0:
            open_exit_tick, open_exit_reason = _exit_position_at_tick(
                direction=position,
                bid_tick=bid_open_tick,
                ask_tick=ask_open_tick,
                stop_tick=stop_tick,
                target_tick=target_tick,
                open_tick=True,
            )
            if open_exit_tick is not None and open_exit_reason is not None:
                append_trade(
                    session_date=session_date,
                    exit_time=timestamp,
                    exit_tick=open_exit_tick,
                    exit_reason=open_exit_reason,
                )
                position = 0
                pending_order = None

        if position == 0 and pending_order is not None:
            fill_tick = _fill_pending_order_at_tick(
                pending_order=pending_order,
                bid_tick=bid_open_tick,
                ask_tick=ask_open_tick,
            )
            if fill_tick is not None:
                position = int(pending_order["direction"])
                entry_tick = int(fill_tick)
                stop_tick = int(pending_order["stop_tick"])
                target_tick = int(pending_order["target_tick"])
                entry_time = timestamp
                signal_time = pending_order["signal_time"]
                fill_reason = "better_open"
                pending_order = None

                same_tick_exit, same_tick_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if same_tick_exit is not None and same_tick_reason is not None:
                    append_trade(
                        session_date=session_date,
                        exit_time=timestamp,
                        exit_tick=same_tick_exit,
                        exit_reason=same_tick_reason,
                    )
                    position = 0

        if minute_of_day[index] >= cutoff_minutes:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(
                    session_date=session_date,
                    exit_time=timestamp,
                    exit_tick=exit_tick,
                    exit_reason="time_cutoff",
                )
                position = 0
            pending_order = None
            previous_bias = candle_bias(
                open_tick=bid_open_tick,
                close_tick=int(close_ticks[index]),
                previous_bias=previous_bias,
            )
            continue

        can_enter_new_trades = bool(can_enter_flags[index])
        if not can_enter_new_trades:
            pending_order = None

        current_day_high_tick = int(day_high_current_ticks[index])
        current_day_low_tick = int(day_low_current_ticks[index])
        current_day_high = ticks_to_price(current_day_high_tick, PRICE_TICK_SIZE)
        current_day_low = ticks_to_price(current_day_low_tick, PRICE_TICK_SIZE)
        current_day_range = current_day_high - current_day_low
        contract_range_filter_value = float(signal_range_slice[index])
        atr_value = float(atr_open_slice[index]) if pd.notna(atr_open_slice[index]) else np.nan
        trend_efficiency_value = (
            float(trend_efficiency_slice[index]) if pd.notna(trend_efficiency_slice[index]) else np.nan
        )
        signal_volume_value = (
            float(signal_volume_slice[index]) if pd.notna(signal_volume_slice[index]) else np.nan
        )
        relative_volume_value = (
            float(relative_volume_slice[index]) if pd.notna(relative_volume_slice[index]) else np.nan
        )

        upper_retracement_tick = price_to_ticks(
            round_to_tick(current_day_high - (current_day_range * params.RetracementLevel)),
            PRICE_TICK_SIZE,
        )
        lower_retracement_tick = price_to_ticks(
            round_to_tick(current_day_low + (current_day_range * params.RetracementLevel)),
            PRICE_TICK_SIZE,
        )

        has_open_position = position != 0
        is_daily_range_big_enough = (
            current_day_range > 0.0
            and contract_range_filter_value > 0.0
            and current_day_range >= contract_range_filter_value
        )

        if (
            not has_open_position
            and can_enter_new_trades
            and is_daily_range_big_enough
            and pd.notna(atr_value)
            and atr_value > 0.0
        ):
            if current_day_high_tick > previous_high_tick:
                if pending_order is not None and int(pending_order["direction"]) == -1:
                    pending_order = None

                base_price = ticks_to_price(upper_retracement_tick, PRICE_TICK_SIZE)
                candidate_order = {
                    "direction": 1,
                    "limit_tick": upper_retracement_tick,
                    "stop_tick": price_to_ticks(
                        round_to_tick(base_price - (atr_value * params.SL_ATRMultiplier)),
                        PRICE_TICK_SIZE,
                    ),
                    "target_tick": price_to_ticks(
                        round_to_tick(base_price + (atr_value * params.TP_ATRMultiplier)),
                        PRICE_TICK_SIZE,
                    ),
                    "signal_time": timestamp,
                }
                if _is_valid_pending_order(
                    direction=1,
                    limit_tick=upper_retracement_tick,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                ) and _passes_directional_trend_efficiency(
                    direction=1,
                    raw_value=trend_efficiency_value,
                    params=params,
                ) and _passes_signal_volume(
                    direction=1,
                    raw_value=signal_volume_value,
                    params=params,
                ) and _passes_relative_volume(
                    direction=1,
                    raw_value=relative_volume_value,
                    params=params,
                ):
                    entry_context = {
                        "dataset_index": start + index,
                        "timestamp": timestamp,
                        "session_date": pd.Timestamp(session_date),
                        "direction": 1,
                        "entry_hour": int(timestamp.hour),
                        "weekday": int(timestamp.dayofweek),
                        "next_trade_number": int(completed_trades_today + 1),
                        "base_price": float(base_price),
                        "atr_value": float(atr_value),
                        "current_day_range": float(current_day_range),
                        "contract_range_filter_value": float(contract_range_filter_value),
                        "trend_efficiency": float(trend_efficiency_value),
                        "signal_volume_sum": float(signal_volume_value),
                        "relative_volume": float(relative_volume_value),
                        "range_vs_filter": (
                            float(current_day_range / contract_range_filter_value)
                            if contract_range_filter_value > 0.0
                            else np.nan
                        ),
                        "signal_source": "new_day_high",
                    }
                    if entry_filter is None or bool(entry_filter(entry_context)):
                        pending_order = candidate_order
            elif current_day_low_tick < previous_low_tick:
                if pending_order is not None and int(pending_order["direction"]) == 1:
                    pending_order = None

                base_price = ticks_to_price(lower_retracement_tick, PRICE_TICK_SIZE)
                candidate_order = {
                    "direction": -1,
                    "limit_tick": lower_retracement_tick,
                    "stop_tick": price_to_ticks(
                        round_to_tick(base_price + (atr_value * params.SL_ATRMultiplier)),
                        PRICE_TICK_SIZE,
                    ),
                    "target_tick": price_to_ticks(
                        round_to_tick(base_price - (atr_value * params.TP_ATRMultiplier)),
                        PRICE_TICK_SIZE,
                    ),
                    "signal_time": timestamp,
                }
                if _is_valid_pending_order(
                    direction=-1,
                    limit_tick=lower_retracement_tick,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                ) and _passes_directional_trend_efficiency(
                    direction=-1,
                    raw_value=trend_efficiency_value,
                    params=params,
                ) and _passes_signal_volume(
                    direction=-1,
                    raw_value=signal_volume_value,
                    params=params,
                ) and _passes_relative_volume(
                    direction=-1,
                    raw_value=relative_volume_value,
                    params=params,
                ):
                    entry_context = {
                        "dataset_index": start + index,
                        "timestamp": timestamp,
                        "session_date": pd.Timestamp(session_date),
                        "direction": -1,
                        "entry_hour": int(timestamp.hour),
                        "weekday": int(timestamp.dayofweek),
                        "next_trade_number": int(completed_trades_today + 1),
                        "base_price": float(base_price),
                        "atr_value": float(atr_value),
                        "current_day_range": float(current_day_range),
                        "contract_range_filter_value": float(contract_range_filter_value),
                        "trend_efficiency": float(trend_efficiency_value),
                        "signal_volume_sum": float(signal_volume_value),
                        "relative_volume": float(relative_volume_value),
                        "range_vs_filter": (
                            float(current_day_range / contract_range_filter_value)
                            if contract_range_filter_value > 0.0
                            else np.nan
                        ),
                        "signal_source": "new_day_low",
                    }
                    if entry_filter is None or bool(entry_filter(entry_context)):
                        pending_order = candidate_order

        if current_day_high_tick > previous_high_tick:
            previous_high_tick = current_day_high_tick
        if current_day_low_tick < previous_low_tick:
            previous_low_tick = current_day_low_tick

        incoming_bias = previous_bias
        bid_path = generate_every_tick_path(
            high_delta=int(high_ticks[index] - bid_open_tick),
            low_delta=int(low_ticks[index] - bid_open_tick),
            close_delta=int(close_ticks[index] - bid_open_tick),
            tick_volume=int(volume[index]),
            previous_bias=incoming_bias,
        )
        previous_bias = candle_bias(
            open_tick=bid_open_tick,
            close_tick=int(close_ticks[index]),
            previous_bias=incoming_bias,
        )

        for delta_tick in bid_path[1:]:
            current_bid_tick = bid_open_tick + int(delta_tick)
            current_ask_tick = current_bid_tick + int(spread_ticks[index])

            if position == 0 and pending_order is not None:
                fill_tick = _fill_pending_order_at_tick(
                    pending_order=pending_order,
                    bid_tick=current_bid_tick,
                    ask_tick=current_ask_tick,
                )
                if fill_tick is not None:
                    position = int(pending_order["direction"])
                    entry_tick = int(fill_tick)
                    stop_tick = int(pending_order["stop_tick"])
                    target_tick = int(pending_order["target_tick"])
                    entry_time = timestamp
                    signal_time = pending_order["signal_time"]
                    fill_reason = "limit_touch"
                    pending_order = None

                    same_tick_exit, same_tick_reason = _exit_position_at_tick(
                        direction=position,
                        bid_tick=current_bid_tick,
                        ask_tick=current_ask_tick,
                        stop_tick=stop_tick,
                        target_tick=target_tick,
                    )
                    if same_tick_exit is not None and same_tick_reason is not None:
                        append_trade(
                            session_date=session_date,
                            exit_time=timestamp,
                            exit_tick=same_tick_exit,
                            exit_reason=same_tick_reason,
                        )
                        position = 0
                        continue

            if position != 0:
                exit_tick, exit_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=current_bid_tick,
                    ask_tick=current_ask_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if exit_tick is not None and exit_reason is not None:
                    append_trade(
                        session_date=session_date,
                        exit_time=timestamp,
                        exit_tick=exit_tick,
                        exit_reason=exit_reason,
                    )
                    position = 0
                    break

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def sample_params(trial: optuna.Trial, baseline: V101Params) -> V101Params:
    start_total_minutes_raw = trial.suggest_int(
        "EntryStart_TotalMinutes",
        ENTRY_WINDOW_START_MINUTES,
        ENTRY_WINDOW_END_MINUTES,
        step=TIME_SLOT_STEP_MINUTES,
    )
    end_total_minutes_raw = trial.suggest_int(
        "LastEntry_TotalMinutes",
        ENTRY_WINDOW_START_MINUTES,
        ENTRY_WINDOW_END_MINUTES,
        step=TIME_SLOT_STEP_MINUTES,
    )
    start_total_minutes = min(start_total_minutes_raw, end_total_minutes_raw)
    end_total_minutes = max(start_total_minutes_raw, end_total_minutes_raw)
    entry_start_hour, entry_start_minute = slot_to_hour_minute(start_total_minutes)
    last_entry_hour, last_entry_minute = slot_to_hour_minute(end_total_minutes)
    trend_mode = trial.suggest_categorical("TrendEfficiencyFilterMode", ["off", "long", "short", "both"])
    volume_mode = trial.suggest_categorical("VolumeFilterMode", ["off", "long", "short", "both"])
    relative_volume_mode = trial.suggest_categorical(
        "RelativeVolumeFilterMode", ["off", "long", "short", "both"]
    )
    trend_longs, trend_shorts = _mode_to_side_flags(trend_mode)
    volume_longs, volume_shorts = _mode_to_side_flags(volume_mode)
    relvol_longs, relvol_shorts = _mode_to_side_flags(relative_volume_mode)

    return V101Params(
        ContractsPerTrade=baseline.ContractsPerTrade,
        FilterAsPercOfContractMARange=trial.suggest_float(
            "FilterAsPercOfContractMARange", 0.15, 0.50, step=0.05
        ),
        NumDaysToConsiderPreviousContractMARange=trial.suggest_int(
            "NumDaysToConsiderPreviousContractMARange", 3, 8
        ),
        RetracementLevel=trial.suggest_float("RetracementLevel", 0.10, 0.40, step=0.01),
        EntryStart_Hour=entry_start_hour,
        EntryStart_Minute=entry_start_minute,
        LastEntry_Hour=last_entry_hour,
        LastEntry_Minute=last_entry_minute,
        AllowMonday=trial.suggest_categorical("AllowMonday", [True, False]),
        AllowTuesday=trial.suggest_categorical("AllowTuesday", [True, False]),
        AllowWednesday=trial.suggest_categorical("AllowWednesday", [True, False]),
        AllowThursday=trial.suggest_categorical("AllowThursday", [True, False]),
        AllowFriday=trial.suggest_categorical("AllowFriday", [True, False]),
        TrendEfficiencyWindowMinutes=trial.suggest_int("TrendEfficiencyWindowMinutes", 10, 30, step=5),
        ApplyTrendEfficiencyFilterToLongs=trend_longs,
        ApplyTrendEfficiencyFilterToShorts=trend_shorts,
        MinDirectionalTrendEfficiency15m=trial.suggest_float(
            "MinDirectionalTrendEfficiency15m", 0.0, 0.80, step=0.05
        ),
        VolumeWindowMinutes=trial.suggest_int("VolumeWindowMinutes", 10, 30, step=5),
        ApplyVolumeFilterToLongs=volume_longs,
        ApplyVolumeFilterToShorts=volume_shorts,
        MinSignalVolumeWindowSum=trial.suggest_float("MinSignalVolumeWindowSum", 10_000.0, 80_000.0, step=2_500.0),
        RelativeVolumeLookbackDays=trial.suggest_int("RelativeVolumeLookbackDays", 10, 60, step=5),
        ApplyRelativeVolumeFilterToLongs=relvol_longs,
        ApplyRelativeVolumeFilterToShorts=relvol_shorts,
        MinRelativeVolumeAtTime=trial.suggest_float("MinRelativeVolumeAtTime", 0.60, 2.20, step=0.05),
        SL_ATRMultiplier=trial.suggest_float("SL_ATRMultiplier", 0.50, 1.50, step=0.05),
        TP_ATRMultiplier=trial.suggest_float("TP_ATRMultiplier", 0.10, 1.00, step=0.05),
        ATRTimeFrame=baseline.ATRTimeFrame,
        ATR_Length=trial.suggest_int("ATR_Length", 10, 40),
        MarketClose_Hour=baseline.MarketClose_Hour,
        MarketClose_Minute=baseline.MarketClose_Minute,
        MinutesBeforeMarketCloseToClosePositions=trial.suggest_int(
            "MinutesBeforeMarketCloseToClosePositions", 1, 15
        ),
    )


def objective_factory(dataset: V10Dataset, train_dates: pd.Index, baseline: V101Params):
    min_trades = max(12, int(len(train_dates) * 0.05))

    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial, baseline)
        trades_df, metrics = run_backtest(dataset, params, train_dates)
        trial.set_user_attr("train_metrics", metrics)
        if len(trades_df) < min_trades:
            return -1000.0 + len(trades_df)
        return float(metrics["on_tester_value"])

    return objective


def optimize_holdout(
    dataset: V10Dataset,
    baseline: V101Params,
    train_dates: pd.Index,
    test_dates: pd.Index,
    trials: int,
    seed: int,
) -> dict[str, Any]:
    sampler = optuna.samplers.TPESampler(
        seed=seed,
        multivariate=True,
        group=True,
        n_startup_trials=min(max(24, trials // 8), trials),
    )
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective_factory(dataset, train_dates, baseline), n_trials=trials, show_progress_bar=False)

    best_params = sample_params(optuna.trial.FixedTrial(study.best_params), baseline)
    train_trades, train_metrics = run_backtest(dataset, best_params, train_dates)
    test_trades, test_metrics = run_backtest(dataset, best_params, test_dates)

    return {
        "study": study,
        "best_params": best_params,
        "train_trades": train_trades,
        "train_metrics": train_metrics,
        "test_trades": test_trades,
        "test_metrics": test_metrics,
        "trials_df": study.trials_dataframe(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure Python port of WDO Stalker Strategy v10.1 with time filters.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--optuna-trials", type=int, default=80)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--trend-eff-window", type=int, default=15)
    parser.add_argument("--trend-eff-longs", action="store_true")
    parser.add_argument("--trend-eff-shorts", action="store_true")
    parser.add_argument("--trend-eff-min", type=float, default=0.333333)
    parser.add_argument("--volume-window", type=int, default=15)
    parser.add_argument("--volume-longs", action="store_true")
    parser.add_argument("--volume-shorts", action="store_true")
    parser.add_argument("--volume-min", type=float, default=0.0)
    parser.add_argument("--relvol-lookback", type=int, default=20)
    parser.add_argument("--relvol-longs", action="store_true")
    parser.add_argument("--relvol-shorts", action="store_true")
    parser.add_argument("--relvol-min", type=float, default=0.0)
    args = parser.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    data_path = locate_data_file(args.data_path)
    dataset = V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates

    if args.start_date:
        trade_dates = trade_dates[trade_dates >= pd.Timestamp(args.start_date)]
    if args.end_date:
        trade_dates = trade_dates[trade_dates <= pd.Timestamp(args.end_date)]
    if len(trade_dates) < 30:
        raise ValueError("Need at least 30 trading days after date filters.")

    baseline = V101Params(
        TrendEfficiencyWindowMinutes=int(args.trend_eff_window),
        ApplyTrendEfficiencyFilterToLongs=bool(args.trend_eff_longs),
        ApplyTrendEfficiencyFilterToShorts=bool(args.trend_eff_shorts),
        MinDirectionalTrendEfficiency15m=float(args.trend_eff_min),
        VolumeWindowMinutes=int(args.volume_window),
        ApplyVolumeFilterToLongs=bool(args.volume_longs),
        ApplyVolumeFilterToShorts=bool(args.volume_shorts),
        MinSignalVolumeWindowSum=float(args.volume_min),
        RelativeVolumeLookbackDays=int(args.relvol_lookback),
        ApplyRelativeVolumeFilterToLongs=bool(args.relvol_longs),
        ApplyRelativeVolumeFilterToShorts=bool(args.relvol_shorts),
        MinRelativeVolumeAtTime=float(args.relvol_min),
    )
    baseline_trades, baseline_metrics = run_backtest(dataset, baseline, trade_dates)

    optimization = None
    if args.optuna_trials > 0 and len(trade_dates) >= 60:
        train_dates, test_dates = split_dates(trade_dates, args.train_ratio)
        optimization = optimize_holdout(
            dataset=dataset,
            baseline=baseline,
            train_dates=train_dates,
            test_dates=test_dates,
            trials=args.optuna_trials,
            seed=args.seed,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_trades.to_csv(args.output_dir / "baseline_trades.csv", index=False)
    if optimization is not None:
        optimization["train_trades"].to_csv(args.output_dir / "optimized_train_trades.csv", index=False)
        optimization["test_trades"].to_csv(args.output_dir / "optimized_test_trades.csv", index=False)
        optimization["trials_df"].to_csv(args.output_dir / "optuna_trials.csv", index=False)

    summary = build_summary(
        dataset=dataset,
        baseline=baseline,
        base_metrics=baseline_metrics,
        optimization=optimization,
        data_path=data_path,
        train_ratio=args.train_ratio,
    )
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
