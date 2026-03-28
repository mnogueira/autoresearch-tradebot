from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
from ..common.mt5_every_tick import candle_bias, generate_every_tick_path, price_to_ticks, ticks_to_price
from .stalker_v10_1_python import (
    PRICE_TICK_SIZE,
    V101Params,
    _ensure_every_tick_cache,
    _ensure_signal_strength_cache,
    _exit_position_at_tick,
    _fill_pending_order_at_tick,
    _is_valid_pending_order,
    _passes_directional_trend_efficiency,
    _passes_relative_volume,
    _passes_signal_volume,
    _trade_slice_bounds,
    allows_entry_direction,
    entry_window_minutes,
    run_backtest,
)
from .stalker_v10_python import (
    BIG_NUMBER,
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    TradeRecord,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    round_to_tick,
)

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_advanced_followups_20260328")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"


def session_winner_params() -> V101Params:
    return V101Params(
        TrendEfficiencyWindowMinutes=15,
        ApplyTrendEfficiencyFilterToLongs=True,
        ApplyTrendEfficiencyFilterToShorts=False,
        MinDirectionalTrendEfficiency15m=0.333333,
        VolumeWindowMinutes=30,
        ApplyVolumeFilterToLongs=False,
        ApplyVolumeFilterToShorts=True,
        MinSignalVolumeWindowSum=30000.0,
        SkipShortWednesday=True,
        SkipShortHour13=True,
        LastEntry_Hour=14,
        LastEntry_Minute=30,
        SL_ATRMultiplier=0.84,
        TP_ATRMultiplier=0.30,
    )


def session_hours_filter(allowed_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    allowed = {int(hour) for hour in allowed_hours}
    return lambda context: int(context["entry_hour"]) in allowed


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active)

    return allow


def make_daily_atr_filter(
    daily_atr_by_session: dict[pd.Timestamp, float],
    min_atr: float,
    max_atr: float,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        value = float(daily_atr_by_session.get(session, np.nan))
        return bool(np.isfinite(value) and float(min_atr) <= value <= float(max_atr))

    return allow


def load_leaderboard(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def leaderboard_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    tier = str(row.get("comparison_tier", "exact"))
    tier_rank = {"validated": 3, "exact": 2, "analysis": 1, "proxy": 0}.get(tier, 1)
    if row.get("validated_on_tester_value") is not None:
        on_tester = float(row.get("validated_on_tester_value", 0.0))
        net = float(row.get("validated_net_profit_brl", 0.0))
        dd = -float(row.get("validated_max_drawdown_pct", 0.0))
        return (tier_rank, on_tester, net, dd)
    on_tester = float(row.get("test_on_tester_value", 0.0) or 0.0)
    net = float(row.get("test_net_profit_brl", 0.0) or 0.0)
    dd = -float(row.get("test_max_drawdown_pct", 0.0) or 0.0)
    return (tier_rank, on_tester, net, dd)


def update_leaderboard(path: Path, rows: list[dict[str, Any]]) -> None:
    stale_prefixes = (
        "session_winner_breakeven_proxy_",
        "session_winner_pyramiding_proxy_",
        "session_winner_breakeven_exact_",
        "session_winner_daily_atr_",
    )
    leaderboard = [
        row
        for row in load_leaderboard(path)
        if row.get("name") not in {item["name"] for item in rows}
        and not any(str(row.get("name", "")).startswith(prefix) for prefix in stale_prefixes)
    ]
    leaderboard.extend(rows)
    leaderboard.sort(key=leaderboard_sort_key, reverse=True)
    for rank, row in enumerate(leaderboard, start=1):
        row["rank"] = rank
    path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")


def enrich_trades(dataset: V10Dataset, trades: pd.DataFrame) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    bars["atr20"] = dataset.get_atr_current(20)
    strength = dataset._v101_signal_strength_cache if hasattr(dataset, "_v101_signal_strength_cache") else None
    if strength is None:
        from .stalker_v10_1_python import _ensure_signal_strength_cache

        strength = _ensure_signal_strength_cache(dataset=dataset, trend_window=15, volume_window=30, relative_volume_lookback=20)
    bars["trend_eff_15"] = strength["trend_efficiency_raw"]
    bars["bar_time"] = bars.index.floor("min")
    lookup = bars[["bar_time", "atr20", "trend_eff_15"]].set_index("bar_time")

    frame = trades.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["signal_time"] = pd.to_datetime(frame["signal_time"])
    frame["entry_time"] = pd.to_datetime(frame["entry_time"])
    frame["exit_time"] = pd.to_datetime(frame["exit_time"])
    frame = frame.join(lookup, on=frame["signal_time"].dt.floor("min"))
    return frame


def apply_breakeven_proxy(dataset: V10Dataset, trades: pd.DataFrame, trigger_mult: float) -> pd.DataFrame:
    bars = dataset.bars_m1
    adjusted = trades.copy()
    adjusted_pnl: list[float] = []
    for row in adjusted.itertuples(index=False):
        atr = float(row.atr20) if pd.notna(row.atr20) else np.nan
        if not np.isfinite(atr) or atr <= 0.0:
            adjusted_pnl.append(float(row.pnl_brl))
            continue
        window = bars.loc[pd.Timestamp(row.entry_time) : pd.Timestamp(row.exit_time)]
        if window.empty:
            adjusted_pnl.append(float(row.pnl_brl))
            continue
        entry_price = float(row.entry_price)
        if row.direction == "long":
            favorable_excursion = float(window["High"].max()) - entry_price
        else:
            favorable_excursion = entry_price - float(window["Low"].min())
        if favorable_excursion >= (float(trigger_mult) * atr) and float(row.pnl_brl) < 0.0:
            adjusted_pnl.append(float(-ROUND_TRIP_COST_BRL))
        else:
            adjusted_pnl.append(float(row.pnl_brl))
    adjusted["pnl_brl"] = adjusted_pnl
    return adjusted


def run_backtest_with_breakeven(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None,
    trigger_mult: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if int(params.ATRTimeFrame) != 15:
        raise ValueError("ATRTimeFrame must be 15 for the v10.1 MT5 parity model.")

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
    breakeven_trigger_ticks = 0
    breakeven_armed = False
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

    def arm_breakeven_if_needed(bid_tick: int, ask_tick: int) -> None:
        nonlocal stop_tick, breakeven_armed
        if position == 0 or breakeven_armed or breakeven_trigger_ticks <= 0:
            return
        if position == 1 and (bid_tick - entry_tick) >= breakeven_trigger_ticks:
            stop_tick = max(stop_tick, entry_tick)
            breakeven_armed = True
        elif position == -1 and (entry_tick - ask_tick) >= breakeven_trigger_ticks:
            stop_tick = min(stop_tick, entry_tick)
            breakeven_armed = True

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
            breakeven_trigger_ticks = 0
            breakeven_armed = False

        if position != 0:
            arm_breakeven_if_needed(bid_open_tick, ask_open_tick)
            open_exit_tick, open_exit_reason = _exit_position_at_tick(
                direction=position,
                bid_tick=bid_open_tick,
                ask_tick=ask_open_tick,
                stop_tick=stop_tick,
                target_tick=target_tick,
                open_tick=True,
            )
            if open_exit_tick is not None and open_exit_reason is not None:
                append_trade(session_date=session_date, exit_time=timestamp, exit_tick=open_exit_tick, exit_reason=open_exit_reason)
                position = 0
                pending_order = None
                breakeven_trigger_ticks = 0
                breakeven_armed = False

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
                breakeven_trigger_ticks = int(pending_order.get("breakeven_trigger_ticks", 0))
                breakeven_armed = False
                entry_time = timestamp
                signal_time = pending_order["signal_time"]
                fill_reason = "better_open"
                pending_order = None
                arm_breakeven_if_needed(bid_open_tick, ask_open_tick)
                same_tick_exit, same_tick_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if same_tick_exit is not None and same_tick_reason is not None:
                    append_trade(session_date=session_date, exit_time=timestamp, exit_tick=same_tick_exit, exit_reason=same_tick_reason)
                    position = 0
                    breakeven_trigger_ticks = 0
                    breakeven_armed = False

        if minute_of_day[index] >= cutoff_minutes:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(session_date=session_date, exit_time=timestamp, exit_tick=exit_tick, exit_reason="time_cutoff")
                position = 0
            pending_order = None
            breakeven_trigger_ticks = 0
            breakeven_armed = False
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
        trend_efficiency_value = float(trend_efficiency_slice[index]) if pd.notna(trend_efficiency_slice[index]) else np.nan
        signal_volume_value = float(signal_volume_slice[index]) if pd.notna(signal_volume_slice[index]) else np.nan
        relative_volume_value = float(relative_volume_slice[index]) if pd.notna(relative_volume_slice[index]) else np.nan

        upper_retracement_tick = price_to_ticks(
            round_to_tick(current_day_high - (current_day_range * params.RetracementLevel)),
            PRICE_TICK_SIZE,
        )
        lower_retracement_tick = price_to_ticks(
            round_to_tick(current_day_low + (current_day_range * params.RetracementLevel)),
            PRICE_TICK_SIZE,
        )
        is_daily_range_big_enough = (
            current_day_range > 0.0
            and contract_range_filter_value > 0.0
            and current_day_range >= contract_range_filter_value
        )

        if position == 0 and can_enter_new_trades and is_daily_range_big_enough and pd.notna(atr_value) and atr_value > 0.0:
            breakeven_gap_ticks = max(1, int(np.ceil((float(trigger_mult) * atr_value) / PRICE_TICK_SIZE)))
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
                    "breakeven_trigger_ticks": breakeven_gap_ticks,
                }
                if allows_entry_direction(timestamp, 1, params) and _is_valid_pending_order(
                    direction=1,
                    limit_tick=upper_retracement_tick,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                ) and _passes_directional_trend_efficiency(1, trend_efficiency_value, params) and _passes_signal_volume(
                    1, signal_volume_value, params
                ) and _passes_relative_volume(1, relative_volume_value, params):
                    entry_context = {
                        "dataset_index": start + index,
                        "timestamp": timestamp,
                        "session_date": pd.Timestamp(session_date),
                        "direction": 1,
                        "entry_hour": int(timestamp.hour),
                        "weekday": int(timestamp.dayofweek),
                        "next_trade_number": int(completed_trades_today + 1),
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
                    "breakeven_trigger_ticks": breakeven_gap_ticks,
                }
                if allows_entry_direction(timestamp, -1, params) and _is_valid_pending_order(
                    direction=-1,
                    limit_tick=lower_retracement_tick,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                ) and _passes_directional_trend_efficiency(-1, trend_efficiency_value, params) and _passes_signal_volume(
                    -1, signal_volume_value, params
                ) and _passes_relative_volume(-1, relative_volume_value, params):
                    entry_context = {
                        "dataset_index": start + index,
                        "timestamp": timestamp,
                        "session_date": pd.Timestamp(session_date),
                        "direction": -1,
                        "entry_hour": int(timestamp.hour),
                        "weekday": int(timestamp.dayofweek),
                        "next_trade_number": int(completed_trades_today + 1),
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
                    breakeven_trigger_ticks = int(pending_order.get("breakeven_trigger_ticks", 0))
                    breakeven_armed = False
                    entry_time = timestamp
                    signal_time = pending_order["signal_time"]
                    fill_reason = "limit_touch"
                    pending_order = None
                    arm_breakeven_if_needed(current_bid_tick, current_ask_tick)
                    same_tick_exit, same_tick_reason = _exit_position_at_tick(
                        direction=position,
                        bid_tick=current_bid_tick,
                        ask_tick=current_ask_tick,
                        stop_tick=stop_tick,
                        target_tick=target_tick,
                    )
                    if same_tick_exit is not None and same_tick_reason is not None:
                        append_trade(session_date=session_date, exit_time=timestamp, exit_tick=same_tick_exit, exit_reason=same_tick_reason)
                        position = 0
                        breakeven_trigger_ticks = 0
                        breakeven_armed = False
                        continue
            if position != 0:
                arm_breakeven_if_needed(current_bid_tick, current_ask_tick)
                exit_tick, exit_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=current_bid_tick,
                    ask_tick=current_ask_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if exit_tick is not None and exit_reason is not None:
                    append_trade(session_date=session_date, exit_time=timestamp, exit_tick=exit_tick, exit_reason=exit_reason)
                    position = 0
                    breakeven_trigger_ticks = 0
                    breakeven_armed = False
                    break

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def make_weekday_exclusion_filter(excluded_weekdays: set[int]) -> Callable[[dict[str, Any]], bool]:
    excluded = {int(value) for value in excluded_weekdays}
    return lambda context: int(context["weekday"]) not in excluded


def build_m15_ema_arrays(dataset: V10Dataset) -> tuple[np.ndarray, np.ndarray]:
    m15_close = dataset.bars_m1["Close"].resample("15min").last()
    ema5 = m15_close.ewm(span=5, adjust=False).mean().shift(1)
    ema21 = m15_close.ewm(span=21, adjust=False).mean().shift(1)
    ema5_ffill = ema5.reindex(dataset.bars_m1.index, method="ffill").to_numpy(dtype=float)
    ema21_ffill = ema21.reindex(dataset.bars_m1.index, method="ffill").to_numpy(dtype=float)
    return ema5_ffill, ema21_ffill


def make_ema_crossover_filter(ema_fast: np.ndarray, ema_slow: np.ndarray) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        fast = float(ema_fast[idx])
        slow = float(ema_slow[idx])
        if not np.isfinite(fast) or not np.isfinite(slow):
            return False
        direction = int(context["direction"])
        if direction == 1:
            return fast > slow
        return fast < slow

    return allow


def apply_pyramiding_proxy(trades: pd.DataFrame, trigger_mult: float, min_trend_eff: float, add_fraction: float) -> pd.DataFrame:
    adjusted = trades.copy()
    atr = adjusted["atr20"].astype(float).replace(0.0, np.nan)
    payoff = adjusted["pnl_brl"].astype(float)
    qualifies = (
        payoff.gt(0.0)
        & adjusted["trend_eff_15"].astype(float).ge(float(min_trend_eff))
        & atr.notna()
        & payoff.ge(atr * float(trigger_mult) * 10.0)
    )
    adjusted.loc[qualifies, "pnl_brl"] = payoff.loc[qualifies] * (1.0 + float(add_fraction))
    return adjusted


def build_daily_atr_by_session(dataset: V10Dataset, window: int = 20) -> dict[pd.Timestamp, float]:
    bars = dataset.bars_m1
    daily = bars.groupby("session_date").agg(High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    prev_close = daily["Close"].shift(1)
    tr = pd.concat(
        [
            daily["High"] - daily["Low"],
            (daily["High"] - prev_close).abs(),
            (daily["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(int(window), min_periods=max(3, int(window) // 2)).mean().shift(1)
    return {pd.Timestamp(index).normalize(): float(value) for index, value in atr.items() if pd.notna(value)}


def month_robustness(trades: pd.DataFrame) -> list[dict[str, Any]]:
    frame = trades.copy()
    frame["month"] = pd.to_datetime(frame["entry_time"]).dt.month
    rows: list[dict[str, Any]] = []
    for month, chunk in frame.groupby("month"):
        pnl = chunk["pnl_brl"].astype(float)
        gross_profit = float(pnl[pnl > 0.0].sum())
        gross_loss = float(-pnl[pnl < 0.0].sum())
        pf = gross_profit / gross_loss if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0)
        rows.append(
            {
                "month": int(month),
                "trades": int(len(chunk)),
                "net_profit_brl": round(float(pnl.sum()), 2),
                "profit_factor": round(float(pf), 4) if np.isfinite(pf) else float("inf"),
                "win_rate": round(float((pnl > 0.0).mean()), 4) if len(pnl) else 0.0,
            }
        )
    return sorted(rows, key=lambda row: row["month"])


def candidate_row(
    name: str,
    family: str,
    metrics: dict[str, Any],
    notes: str,
    artifact: Path,
    mt5_ready: bool = False,
    comparison_tier: str = "exact",
) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "screening_method": "session_winner_followup",
        "mt5_ready": mt5_ready,
        "comparison_tier": comparison_tier,
        "test_total_trades": int(metrics["total_trades"]),
        "test_net_profit_brl": float(metrics["net_profit_brl"]),
        "test_profit_factor": float(metrics["profit_factor"]),
        "test_on_tester_value": float(metrics["on_tester_value"]),
        "test_max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "test_win_rate": float(metrics["win_rate"]),
        "notes": notes,
        "source_artifact": str(artifact.resolve()),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_hours_filter({10, 11, 12, 14})
    base_trades, _ = run_backtest(dataset, params, dataset.trade_dates, entry_filter=base_filter)
    base_trades = enrich_trades(dataset, base_trades)
    base_metrics = calculate_metrics(base_trades, dataset.trade_dates)

    daily_atr = build_daily_atr_by_session(dataset, window=20)
    atr_values = pd.Series(daily_atr.values(), dtype=float)
    regime_specs = [
        ("daily_atr_10_90", float(atr_values.quantile(0.10)), float(atr_values.quantile(0.90))),
        ("daily_atr_20_80", float(atr_values.quantile(0.20)), float(atr_values.quantile(0.80))),
        ("daily_atr_25_75", float(atr_values.quantile(0.25)), float(atr_values.quantile(0.75))),
    ]

    regime_results: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    for name, min_atr, max_atr in regime_specs:
        regime_filter = combine_filters(base_filter, make_daily_atr_filter(daily_atr, min_atr, max_atr))
        trades, _ = run_backtest(dataset, params, dataset.trade_dates, entry_filter=regime_filter)
        metrics = calculate_metrics(trades, dataset.trade_dates)
        regime_results.append({"name": name, "min_atr": min_atr, "max_atr": max_atr, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_{name}",
                family="daily_atr_regime",
                metrics=metrics,
                notes=f"Exact session-winner screen with ATR20 daily regime clipped to {name.replace('daily_atr_', '').replace('_', '-')}.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            )
        )

    breakeven_exact_results: list[dict[str, Any]] = []
    for trigger in (0.10, 0.15, 0.20):
        _, metrics = run_backtest_with_breakeven(dataset, params, dataset.trade_dates, base_filter, trigger)
        breakeven_exact_results.append({"trigger_atr_mult": trigger, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_breakeven_exact_{str(trigger).replace('.', 'p')}",
                family="breakeven_exact",
                metrics=metrics,
                notes=f"Exact every-tick breakeven test: move stop to entry after {trigger:.2f} ATR in favor.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            )
        )

    pyramiding = apply_pyramiding_proxy(base_trades, trigger_mult=0.20, min_trend_eff=0.45, add_fraction=0.25)
    pyramiding_metrics = calculate_metrics(pyramiding, dataset.trade_dates)
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_pyramiding_proxy_te045_add25pct",
            family="pyramiding_proxy",
            metrics=pyramiding_metrics,
            notes="Trade-tape proxy: add 25% size to winning trades once trend efficiency is strong and payoff clears a 0.20 ATR hurdle.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            comparison_tier="proxy",
        )
    )

    friday_filter = combine_filters(base_filter, make_weekday_exclusion_filter({4}))
    friday_trades, _ = run_backtest(dataset, params, dataset.trade_dates, entry_filter=friday_filter)
    friday_metrics = calculate_metrics(friday_trades, dataset.trade_dates)
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_skip_friday",
            family="weekday_filter",
            metrics=friday_metrics,
            notes="Exact session-winner backtest excluding all Friday entries.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
        )
    )

    ema_fast, ema_slow = build_m15_ema_arrays(dataset)
    ema_params = V101Params(
        **{
            **asdict(params),
            "ApplyTrendEfficiencyFilterToLongs": False,
            "ApplyTrendEfficiencyFilterToShorts": False,
        }
    )
    ema_filter = combine_filters(base_filter, make_ema_crossover_filter(ema_fast, ema_slow))
    ema_trades, _ = run_backtest(dataset, ema_params, dataset.trade_dates, entry_filter=ema_filter)
    ema_metrics = calculate_metrics(ema_trades, dataset.trade_dates)
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_ema5_21_direction_filter",
            family="ema_crossover_direction",
            metrics=ema_metrics,
            notes="Exact session-window test using M15 EMA 5/21 direction instead of trend-efficiency.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
        )
    )

    summary = {
        "reference": {
            "name": "session_winner_hours_10_12_14_sl0p84_tp0p3",
            "params": asdict(params),
            "metrics": base_metrics,
        },
        "daily_atr_regime_results": regime_results,
        "breakeven_exact_results": breakeven_exact_results,
        "pyramiding_proxy_result": {
            "trigger_atr_mult": 0.20,
            "min_trend_efficiency": 0.45,
            "add_fraction": 0.25,
            "metrics": pyramiding_metrics,
        },
        "friday_filter_result": friday_metrics,
        "ema_crossover_result": {
            "params": asdict(ema_params),
            "metrics": ema_metrics,
        },
        "calendar_month_robustness": month_robustness(base_trades),
        "notes": [
            "The local parquet is a continuous WDO series without contract identifiers, so robustness is reported by calendar month rather than contract code.",
            "Breakeven is exact every-tick in this pass; pyramiding remains a conservative trade-tape proxy.",
            "The EMA 5/21 test swaps out trend efficiency and keeps the session winner timing and SL/TP scaffold intact.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
