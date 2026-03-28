from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.mt5_every_tick import candle_bias, generate_every_tick_path, price_to_ticks, ticks_to_price
from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
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
from .stalker_v10_1_session_advanced_followups import load_leaderboard, update_leaderboard
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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_execution_refinement_20260328")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"


@dataclass(frozen=True)
class ManagementConfig:
    max_bars_in_trade: int | None = None
    partial_profit_enabled: bool = False
    partial_fraction: float = 0.5


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


def session_filter(allowed_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    allowed = {int(hour) for hour in allowed_hours}
    return lambda context: int(context["entry_hour"]) in allowed


def candidate_row(
    name: str,
    family: str,
    metrics: dict[str, Any],
    notes: str,
    artifact: Path,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "family": family,
        "screening_method": "session_winner_execution_refinement",
        "comparison_tier": "exact",
        "mt5_ready": False,
        "test_total_trades": int(metrics["total_trades"]),
        "test_net_profit_brl": float(metrics["net_profit_brl"]),
        "test_profit_factor": float(metrics["profit_factor"]),
        "test_on_tester_value": float(metrics["on_tester_value"]),
        "test_max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "test_win_rate": float(metrics["win_rate"]),
        "notes": notes,
        "source_artifact": str(artifact.resolve()),
    }
    if params is not None:
        row["params"] = params
    return row


def run_backtest_with_management(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None,
    management: ManagementConfig,
    range_high_ticks_override: np.ndarray | None = None,
    range_low_ticks_override: np.ndarray | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    day_high_current_ticks = (
        range_high_ticks_override[start:stop]
        if range_high_ticks_override is not None
        else cache["day_high_current_ticks"][start:stop]
    )
    day_low_current_ticks = (
        range_low_ticks_override[start:stop]
        if range_low_ticks_override is not None
        else cache["day_low_current_ticks"][start:stop]
    )
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
    initial_target_tick = 0
    half_target_tick = 0
    trail_distance_ticks = 0
    entry_time = pd.NaT
    signal_time = pd.NaT
    fill_reason = ""
    entry_bar_index = 0
    partial_taken = False
    partial_exit_tick = 0
    realized_partial_pnl_brl = 0.0
    realized_partial_points = 0.0
    best_bid_tick = 0
    best_ask_tick = BIG_NUMBER

    pending_order: dict[str, Any] | None = None
    completed_trades_today = 0

    def reset_position_state() -> None:
        nonlocal position, pending_order, partial_taken, partial_exit_tick
        nonlocal realized_partial_pnl_brl, realized_partial_points, trail_distance_ticks
        nonlocal initial_target_tick, half_target_tick, best_bid_tick, best_ask_tick
        position = 0
        pending_order = None
        partial_taken = False
        partial_exit_tick = 0
        realized_partial_pnl_brl = 0.0
        realized_partial_points = 0.0
        trail_distance_ticks = 0
        initial_target_tick = 0
        half_target_tick = 0
        best_bid_tick = 0
        best_ask_tick = BIG_NUMBER

    def append_trade(session_date: np.datetime64, exit_time: pd.Timestamp, exit_tick: int, exit_reason: str) -> None:
        nonlocal completed_trades_today
        entry_price = ticks_to_price(entry_tick, PRICE_TICK_SIZE)
        exit_price = ticks_to_price(exit_tick, PRICE_TICK_SIZE)
        remainder_fraction = 1.0 - (management.partial_fraction if partial_taken else 0.0)
        final_points = (exit_price - entry_price) * position * remainder_fraction
        pnl_points = realized_partial_points + final_points
        pnl_brl = (
            realized_partial_pnl_brl
            + (final_points * POINT_VALUE_BRL * params.ContractsPerTrade)
            - ROUND_TRIP_COST_BRL
        )
        trades.append(
            TradeRecord(
                session_date=pd.Timestamp(session_date).date().isoformat(),
                signal_time=str(signal_time),
                entry_time=str(entry_time),
                exit_time=str(exit_time),
                direction="long" if position == 1 else "short",
                entry_price=entry_price,
                exit_price=float(exit_price),
                stop_price=ticks_to_price(stop_tick, PRICE_TICK_SIZE),
                target_price=ticks_to_price(target_tick, PRICE_TICK_SIZE),
                pnl_points=round(float(pnl_points), 2),
                pnl_brl=round(float(pnl_brl), 2),
                fill_reason=fill_reason or "active_position",
                exit_reason=exit_reason,
            )
        )
        completed_trades_today += 1

    def arm_position_state(current_index: int) -> None:
        nonlocal entry_bar_index, initial_target_tick, half_target_tick, trail_distance_ticks
        nonlocal partial_taken, partial_exit_tick, realized_partial_pnl_brl, realized_partial_points
        nonlocal best_bid_tick, best_ask_tick
        entry_bar_index = int(current_index)
        initial_target_tick = int(target_tick)
        partial_taken = False
        partial_exit_tick = 0
        realized_partial_pnl_brl = 0.0
        realized_partial_points = 0.0
        if management.partial_profit_enabled:
            target_distance_ticks = max(1, abs(initial_target_tick - entry_tick))
            half_distance_ticks = max(1, target_distance_ticks // 2)
            half_target_tick = entry_tick + (half_distance_ticks * position)
            trail_distance_ticks = max(1, target_distance_ticks - half_distance_ticks)
        else:
            half_target_tick = 0
            trail_distance_ticks = 0
        best_bid_tick = entry_tick
        best_ask_tick = entry_tick

    def maybe_take_partial(current_bid_tick: int, current_ask_tick: int) -> None:
        nonlocal partial_taken, partial_exit_tick, realized_partial_pnl_brl, realized_partial_points, stop_tick
        nonlocal best_bid_tick, best_ask_tick
        if position == 0 or partial_taken or not management.partial_profit_enabled:
            return
        hit_partial = (position == 1 and current_bid_tick >= half_target_tick) or (
            position == -1 and current_ask_tick <= half_target_tick
        )
        if not hit_partial:
            return
        partial_taken = True
        partial_exit_tick = half_target_tick
        partial_exit_price = ticks_to_price(partial_exit_tick, PRICE_TICK_SIZE)
        partial_points = (partial_exit_price - ticks_to_price(entry_tick, PRICE_TICK_SIZE)) * position * management.partial_fraction
        realized_partial_points = float(partial_points)
        realized_partial_pnl_brl = float(partial_points * POINT_VALUE_BRL * params.ContractsPerTrade)
        if position == 1:
            best_bid_tick = max(best_bid_tick, current_bid_tick)
            stop_tick = max(stop_tick, entry_tick, best_bid_tick - trail_distance_ticks)
        else:
            best_ask_tick = min(best_ask_tick, current_ask_tick)
            stop_tick = min(stop_tick, entry_tick, best_ask_tick + trail_distance_ticks)

    def update_trailing_stop(current_bid_tick: int, current_ask_tick: int) -> None:
        nonlocal stop_tick, best_bid_tick, best_ask_tick
        if position == 0 or not partial_taken or trail_distance_ticks <= 0:
            return
        if position == 1:
            best_bid_tick = max(best_bid_tick, current_bid_tick)
            stop_tick = max(stop_tick, entry_tick, best_bid_tick - trail_distance_ticks)
        else:
            best_ask_tick = min(best_ask_tick, current_ask_tick)
            stop_tick = min(stop_tick, entry_tick, best_ask_tick + trail_distance_ticks)

    for index in range(len(timestamps)):
        timestamp = timestamps[index]
        session_date = session_dates[index]
        bid_open_tick = int(open_ticks[index])
        ask_open_tick = bid_open_tick + int(spread_ticks[index])

        if current_date is None or session_date != current_date:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(current_date, timestamp, exit_tick, "forced_day_change")
                reset_position_state()
            current_date = session_date
            previous_high_tick = 0
            previous_low_tick = price_to_ticks(BIG_NUMBER, PRICE_TICK_SIZE)
            completed_trades_today = 0

        if position != 0:
            update_trailing_stop(bid_open_tick, ask_open_tick)
            open_exit_tick, open_exit_reason = _exit_position_at_tick(
                direction=position,
                bid_tick=bid_open_tick,
                ask_tick=ask_open_tick,
                stop_tick=stop_tick,
                target_tick=target_tick,
                open_tick=True,
            )
            if open_exit_tick is not None and open_exit_reason is not None:
                maybe_take_partial(bid_open_tick, ask_open_tick)
                update_trailing_stop(bid_open_tick, ask_open_tick)
                append_trade(session_date, timestamp, open_exit_tick, open_exit_reason)
                reset_position_state()
            elif management.max_bars_in_trade is not None and (index - entry_bar_index) >= int(management.max_bars_in_trade):
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(session_date, timestamp, exit_tick, f"time_exit_{int(management.max_bars_in_trade)}bars")
                reset_position_state()

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
                arm_position_state(index)
                maybe_take_partial(bid_open_tick, ask_open_tick)
                update_trailing_stop(bid_open_tick, ask_open_tick)
                same_tick_exit, same_tick_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=bid_open_tick,
                    ask_tick=ask_open_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if same_tick_exit is not None and same_tick_reason is not None:
                    append_trade(session_date, timestamp, same_tick_exit, same_tick_reason)
                    reset_position_state()

        if minute_of_day[index] >= cutoff_minutes:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(session_date, timestamp, exit_tick, "time_cutoff")
                reset_position_state()
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
            if current_day_high_tick > previous_high_tick:
                if pending_order is not None and int(pending_order["direction"]) == -1:
                    pending_order = None
                base_price = ticks_to_price(upper_retracement_tick, PRICE_TICK_SIZE)
                candidate_order = {
                    "direction": 1,
                    "limit_tick": upper_retracement_tick,
                    "stop_tick": price_to_ticks(round_to_tick(base_price - (atr_value * params.SL_ATRMultiplier)), PRICE_TICK_SIZE),
                    "target_tick": price_to_ticks(round_to_tick(base_price + (atr_value * params.TP_ATRMultiplier)), PRICE_TICK_SIZE),
                    "signal_time": timestamp,
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
                    "stop_tick": price_to_ticks(round_to_tick(base_price + (atr_value * params.SL_ATRMultiplier)), PRICE_TICK_SIZE),
                    "target_tick": price_to_ticks(round_to_tick(base_price - (atr_value * params.TP_ATRMultiplier)), PRICE_TICK_SIZE),
                    "signal_time": timestamp,
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
                    entry_time = timestamp
                    signal_time = pending_order["signal_time"]
                    fill_reason = "limit_touch"
                    pending_order = None
                    arm_position_state(index)
                    maybe_take_partial(current_bid_tick, current_ask_tick)
                    update_trailing_stop(current_bid_tick, current_ask_tick)
                    same_tick_exit, same_tick_reason = _exit_position_at_tick(
                        direction=position,
                        bid_tick=current_bid_tick,
                        ask_tick=current_ask_tick,
                        stop_tick=stop_tick,
                        target_tick=target_tick,
                    )
                    if same_tick_exit is not None and same_tick_reason is not None:
                        append_trade(session_date, timestamp, same_tick_exit, same_tick_reason)
                        reset_position_state()
                        continue

            if position != 0:
                maybe_take_partial(current_bid_tick, current_ask_tick)
                update_trailing_stop(current_bid_tick, current_ask_tick)
                exit_tick, exit_reason = _exit_position_at_tick(
                    direction=position,
                    bid_tick=current_bid_tick,
                    ask_tick=current_ask_tick,
                    stop_tick=stop_tick,
                    target_tick=target_tick,
                )
                if exit_tick is not None and exit_reason is not None:
                    append_trade(session_date, timestamp, exit_tick, exit_reason)
                    reset_position_state()
                    break

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    reference_trades, reference_metrics = run_backtest(dataset, base_params, dataset.trade_dates, entry_filter=base_filter)

    tighter_sl_results: list[dict[str, Any]] = []
    retracement_grid_results: list[dict[str, Any]] = []
    time_exit_results: list[dict[str, Any]] = []
    wider_tp_results: list[dict[str, Any]] = []
    rolling_retracement_results: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []

    for sl_value in (0.60, 0.66, 0.72):
        params = V101Params(**{**asdict(base_params), "SL_ATRMultiplier": float(sl_value)})
        _, metrics = run_backtest(dataset, params, dataset.trade_dates, entry_filter=base_filter)
        tighter_sl_results.append({"sl_atr_mult": sl_value, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_tighter_sl_{str(sl_value).replace('.', 'p')}",
                family="session_tighter_sl",
                metrics=metrics,
                notes=f"Exact session winner with tighter stop {sl_value:.2f} ATR and TP 0.30 ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"sl_atr_mult": sl_value, "tp_atr_mult": 0.30, "retracement_level": base_params.RetracementLevel},
            )
        )

    for retracement_level in (0.18, 0.22, 0.25, 0.28, 0.32):
        for sl_value in (0.60, 0.66, 0.72, 0.84):
            params = V101Params(
                **{
                    **asdict(base_params),
                    "RetracementLevel": float(retracement_level),
                    "SL_ATRMultiplier": float(sl_value),
                }
            )
            _, metrics = run_backtest(dataset, params, dataset.trade_dates, entry_filter=base_filter)
            retracement_grid_results.append(
                {
                    "retracement_level": retracement_level,
                    "sl_atr_mult": sl_value,
                    "tp_atr_mult": 0.30,
                    "metrics": metrics,
                }
            )

    retracement_grid_results.sort(
        key=lambda row: (
            float(row["metrics"]["on_tester_value"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )
    for row in retracement_grid_results[:5]:
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_retr_{str(row['retracement_level']).replace('.', 'p')}_sl_{str(row['sl_atr_mult']).replace('.', 'p')}",
                family="session_retracement_sltp",
                metrics=row["metrics"],
                notes="Exact session winner with retracement and tighter-stop refinement, TP fixed at 0.30 ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={
                    "retracement_level": row["retracement_level"],
                    "sl_atr_mult": row["sl_atr_mult"],
                    "tp_atr_mult": row["tp_atr_mult"],
                },
            )
        )

    for max_bars in (30, 60, 90):
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(max_bars_in_trade=max_bars),
        )
        time_exit_results.append({"max_bars_in_trade": max_bars, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_time_exit_{max_bars}bars",
                family="session_time_exit",
                metrics=metrics,
                notes=f"Exact session winner with forced exit after {max_bars} M1 bars if still open.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"max_bars_in_trade": max_bars},
            )
        )

    _, partial_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(partial_profit_enabled=True, partial_fraction=0.5),
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_partial_half_tp_trail",
            family="session_partial_profit",
            metrics=partial_metrics,
            notes="Exact session winner: close half at TP/2, move stop to breakeven, trail the rest by the remaining half-target distance.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"partial_fraction": 0.5, "first_take_profit_fraction_of_tp": 0.5},
        )
    )

    for tp_value in (0.42, 0.48, 0.54):
        params = V101Params(**{**asdict(base_params), "TP_ATRMultiplier": float(tp_value)})
        _, metrics = run_backtest(dataset, params, dataset.trade_dates, entry_filter=base_filter)
        wider_tp_results.append({"sl_atr_mult": base_params.SL_ATRMultiplier, "tp_atr_mult": tp_value, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_wider_tp_{str(tp_value).replace('.', 'p')}",
                family="session_wider_tp",
                metrics=metrics,
                notes=f"Exact session winner with wider TP {tp_value:.2f} ATR and SL 0.84 ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"sl_atr_mult": base_params.SL_ATRMultiplier, "tp_atr_mult": tp_value},
            )
        )

    bars = dataset.bars_m1
    for lookback_bars in (8, 12, 20, 30):
        rolling_high = (
            bars.groupby("session_date")["High"]
            .transform(lambda series: series.rolling(int(lookback_bars), min_periods=1).max())
            .to_numpy(dtype=float)
        )
        rolling_low = (
            bars.groupby("session_date")["Low"]
            .transform(lambda series: series.rolling(int(lookback_bars), min_periods=1).min())
            .to_numpy(dtype=float)
        )
        rolling_high_ticks = np.rint(rolling_high / PRICE_TICK_SIZE).astype(np.int32)
        rolling_low_ticks = np.rint(rolling_low / PRICE_TICK_SIZE).astype(np.int32)
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(),
            range_high_ticks_override=rolling_high_ticks,
            range_low_ticks_override=rolling_low_ticks,
        )
        rolling_retracement_results.append({"lookback_bars": lookback_bars, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_rolling_retracement_{lookback_bars}bars",
                family="session_rolling_retracement",
                metrics=metrics,
                notes=f"Exact session winner using a rolling intraday retracement range of {lookback_bars} M1 bars instead of the full session-to-date range.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"lookback_bars": lookback_bars, "sl_atr_mult": base_params.SL_ATRMultiplier, "tp_atr_mult": base_params.TP_ATRMultiplier},
            )
        )

    summary = {
        "reference": {
            "name": "session_winner_hours_10_11_12_14_sl0p84_tp0p30",
            "params": asdict(base_params),
            "metrics": reference_metrics,
        },
        "tighter_sl_results": tighter_sl_results,
        "retracement_sl_grid_top5": retracement_grid_results[:5],
        "retracement_sl_grid_total_variants": len(retracement_grid_results),
        "time_exit_results": time_exit_results,
        "partial_profit_result": {
            "partial_fraction": 0.5,
            "first_take_profit_fraction_of_tp": 0.5,
            "trail_distance_after_partial": "remaining half-target distance",
            "metrics": partial_metrics,
        },
        "wider_tp_results": wider_tp_results,
        "rolling_retracement_results": rolling_retracement_results,
        "notes": [
            "Exact session-winner execution refinement over the current best exact entry schedule: 10:00, 11:00, 12:00, and 14:00 only.",
            "Time exits close at the next M1 bar open once the trade age reaches the configured bar count.",
            "Partial-profit model assumption: close half at TP/2, move stop to breakeven, and trail the remainder by the remaining half-target distance.",
            "Rolling retracement variants replace the full session-to-date range with a rolling M1 window for the high/low anchor.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
