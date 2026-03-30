from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..common.mt5_every_tick import candle_bias, generate_every_tick_path, price_to_ticks, ticks_to_price
from ..common.paths import artifact_output_dir
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block
from .stalker_v10_1_python import PRICE_TICK_SIZE, _ensure_every_tick_cache, _exit_position_at_tick, _trade_slice_bounds
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets, filter_trades_to_dates
from .stalker_v10_python import (
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    TradeRecord,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    round_to_tick,
    split_dates,
)


OUTPUT_DIR = artifact_output_dir("wdo_opening_range_breakout_corrected_cost_20260329")


@dataclass(frozen=True)
class OpeningRangeCorrectedParams:
    opening_range_minutes: int
    sl_atr_mult: float = 1.0
    tp_atr_mult: float = 0.48
    atr_length: int = 10
    cooldown_minutes: int = 60
    entry_hours: tuple[int, ...] = (10, 11, 12, 14)
    allow_friday: bool = False
    market_close_hour: int = 18
    market_close_minute: int = 0
    minutes_before_close: int = 5


def build_opening_range_signal_map(dataset: V10Dataset, params: OpeningRangeCorrectedParams) -> dict[pd.Timestamp, int]:
    m15 = (
        dataset.bars_m1.assign(session_date_norm=pd.to_datetime(dataset.bars_m1["session_date"]).dt.normalize())
        .resample("15min")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "session_date_norm": "last",
            }
        )
        .dropna()
    )
    bars_in_range = max(1, int(params.opening_range_minutes // 15))
    opening_mask = (m15.index.hour == 9) & (m15.index.minute < params.opening_range_minutes)
    opening_range = (
        m15.loc[opening_mask]
        .groupby("session_date_norm")
        .head(bars_in_range)
        .groupby("session_date_norm")
        .agg(opening_high=("High", "max"), opening_low=("Low", "min"))
    )
    m15 = m15.join(opening_range, on="session_date_norm")

    breakout_after = pd.Timedelta(minutes=params.opening_range_minutes)
    long_breakout = (m15.index.time >= (pd.Timestamp("09:00") + breakout_after).time()) & (m15["Close"] > m15["opening_high"])
    short_breakout = (m15.index.time >= (pd.Timestamp("09:00") + breakout_after).time()) & (m15["Close"] < m15["opening_low"])

    signal_map: dict[pd.Timestamp, int] = {}
    for timestamp, is_long in long_breakout.items():
        if bool(is_long):
            signal_map[pd.Timestamp(timestamp) + pd.Timedelta(minutes=15)] = 1
    for timestamp, is_short in short_breakout.items():
        if bool(is_short):
            signal_map[pd.Timestamp(timestamp) + pd.Timedelta(minutes=15)] = -1
    return signal_map


def run_opening_range_corrected_backtest(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    params: OpeningRangeCorrectedParams,
) -> tuple[pd.DataFrame, dict[str, object]]:
    start, stop = _trade_slice_bounds(dataset, trade_dates)
    if start >= stop:
        return pd.DataFrame(), calculate_metrics(pd.DataFrame(), trade_dates)

    cache = _ensure_every_tick_cache(dataset)
    atr_open = dataset.get_atr_open(int(params.atr_length))
    signal_map = build_opening_range_signal_map(dataset, params)

    timestamps = pd.DatetimeIndex(cache["timestamps"][start:stop])
    session_dates = cache["session_dates"][start:stop]
    open_ticks = cache["open_ticks"][start:stop]
    high_ticks = cache["high_ticks"][start:stop]
    low_ticks = cache["low_ticks"][start:stop]
    close_ticks = cache["close_ticks"][start:stop]
    volume = cache["volume"][start:stop]
    spread_ticks = cache["spread_ticks"][start:stop]
    atr_slice = atr_open[start:stop]

    minute_of_day = (timestamps.hour * 60) + timestamps.minute
    cutoff_minutes = (params.market_close_hour * 60) + params.market_close_minute - params.minutes_before_close

    trades: list[TradeRecord] = []
    previous_bias = 1
    current_date: np.datetime64 | None = None
    position = 0
    entry_tick = 0
    stop_tick = 0
    target_tick = 0
    entry_time = pd.NaT
    signal_time = pd.NaT
    next_allowed_entry_time = pd.Timestamp.min

    def append_trade(session_date: np.datetime64, exit_time: pd.Timestamp, exit_tick: int, exit_reason: str) -> None:
        nonlocal next_allowed_entry_time
        entry_price = ticks_to_price(entry_tick, PRICE_TICK_SIZE)
        exit_price = ticks_to_price(exit_tick, PRICE_TICK_SIZE)
        pnl_points = (exit_price - entry_price) * position
        pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
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
                pnl_points=round(pnl_points, 2),
                pnl_brl=round(pnl_brl, 2),
                fill_reason="market_open",
                exit_reason=exit_reason,
            )
        )
        next_allowed_entry_time = exit_time + pd.Timedelta(minutes=int(params.cooldown_minutes))

    for index in range(len(timestamps)):
        timestamp = timestamps[index]
        session_date = session_dates[index]
        bid_open_tick = int(open_ticks[index])
        ask_open_tick = bid_open_tick + int(spread_ticks[index])

        if current_date is None or session_date != current_date:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(current_date, timestamp, exit_tick, "forced_day_change")
                position = 0
            current_date = session_date
            next_allowed_entry_time = pd.Timestamp.min

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
                append_trade(session_date, timestamp, open_exit_tick, open_exit_reason)
                position = 0

        if minute_of_day[index] >= cutoff_minutes:
            if position != 0:
                exit_tick = bid_open_tick if position == 1 else ask_open_tick
                append_trade(session_date, timestamp, exit_tick, "time_cutoff")
                position = 0
            previous_bias = candle_bias(open_tick=bid_open_tick, close_tick=int(close_ticks[index]), previous_bias=previous_bias)
            continue

        atr_value = float(atr_slice[index]) if pd.notna(atr_slice[index]) else np.nan
        signal_direction = signal_map.get(pd.Timestamp(timestamp), 0)
        allowed_time = (
            timestamp.dayofweek < 5
            and (params.allow_friday or timestamp.dayofweek != 4)
            and timestamp.hour in set(params.entry_hours)
        )
        if (
            position == 0
            and signal_direction in (-1, 1)
            and allowed_time
            and np.isfinite(atr_value)
            and atr_value > 0.0
            and timestamp >= next_allowed_entry_time
        ):
            position = int(signal_direction)
            entry_tick = ask_open_tick if position == 1 else bid_open_tick
            entry_time = timestamp
            signal_time = timestamp
            entry_price = ticks_to_price(entry_tick, PRICE_TICK_SIZE)
            if position == 1:
                stop_tick = price_to_ticks(round_to_tick(entry_price - (atr_value * params.sl_atr_mult)), PRICE_TICK_SIZE)
                target_tick = price_to_ticks(round_to_tick(entry_price + (atr_value * params.tp_atr_mult)), PRICE_TICK_SIZE)
            else:
                stop_tick = price_to_ticks(round_to_tick(entry_price + (atr_value * params.sl_atr_mult)), PRICE_TICK_SIZE)
                target_tick = price_to_ticks(round_to_tick(entry_price - (atr_value * params.tp_atr_mult)), PRICE_TICK_SIZE)

        incoming_bias = previous_bias
        bid_path = generate_every_tick_path(
            high_delta=int(high_ticks[index] - bid_open_tick),
            low_delta=int(low_ticks[index] - bid_open_tick),
            close_delta=int(close_ticks[index] - bid_open_tick),
            tick_volume=int(volume[index]),
            previous_bias=incoming_bias,
        )
        previous_bias = candle_bias(open_tick=bid_open_tick, close_tick=int(close_ticks[index]), previous_bias=incoming_bias)

        for delta_tick in bid_path[1:]:
            if position == 0:
                break
            current_bid_tick = bid_open_tick + int(delta_tick)
            current_ask_tick = current_bid_tick + int(spread_ticks[index])
            exit_tick, exit_reason = _exit_position_at_tick(
                direction=position,
                bid_tick=current_bid_tick,
                ask_tick=current_ask_tick,
                stop_tick=stop_tick,
                target_tick=target_tick,
            )
            if exit_tick is not None and exit_reason is not None:
                append_trade(session_date, timestamp, exit_tick, exit_reason)
                position = 0
                break

    trades_df = pd.DataFrame(trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    trade_dates = pd.Index(dataset.trade_dates).intersection(non_last1_dates).sort_values()
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    variants = [
        ("opening_range_breakout_15m_sl1p0_tp0p48_cd60_skipfriday_skiplast1", OpeningRangeCorrectedParams(opening_range_minutes=15)),
        ("opening_range_breakout_30m_sl1p0_tp0p48_cd60_skipfriday_skiplast1", OpeningRangeCorrectedParams(opening_range_minutes=30)),
    ]

    results: list[dict[str, object]] = []
    for name, params in variants:
        trades, metrics = run_opening_range_corrected_backtest(dataset, trade_dates, params)
        results.append(
            {
                "name": name,
                "params": params.__dict__,
                "metrics": metrics,
                "walkforward_70_30": {
                    "train": _subset_block(filter_trades_to_dates(trades, train_dates), train_dates),
                    "test": _subset_block(filter_trades_to_dates(trades, test_dates), test_dates),
                },
                "recent_windows": {
                    "recent_60d": _subset_block(filter_trades_to_dates(trades, recent_60), recent_60),
                    "recent_30d": _subset_block(filter_trades_to_dates(trades, recent_30), recent_30),
                    "recent_10d": _subset_block(filter_trades_to_dates(trades, recent_10), recent_10),
                },
            }
        )

    summary = {
        "notes": [
            "Corrected-cost opening range breakout using first 15 or 30 minutes of the session.",
            "Breakout is defined by M15 close crossing beyond the opening range, with next-bar exact execution.",
        ],
        "results": results,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
