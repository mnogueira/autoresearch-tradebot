from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.mt5_every_tick import candle_bias, generate_every_tick_path, price_to_ticks, ticks_to_price
from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_python import PRICE_TICK_SIZE, _ensure_every_tick_cache, _exit_position_at_tick, _trade_slice_bounds
from .stalker_v10_python import (
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    TradeRecord,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    round_to_tick,
)

DEFAULT_OUTPUT_DIR = artifact_output_dir("wdo_vwap_extreme_mean_reversion_exact_20260329")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"


@dataclass(frozen=True)
class VWAPExtremeParams:
    sl_atr_mult: float
    tp_atr_mult: float
    atr_length: int = 20
    extreme_atr_mult: float = 2.0
    cooldown_minutes: int = 25
    entry_hours: tuple[int, ...] = (10, 11, 12, 14)
    market_close_hour: int = 18
    market_close_minute: int = 0
    minutes_before_close: int = 5


def build_vwap_extreme_signal_map(dataset: V10Dataset, params: VWAPExtremeParams) -> dict[pd.Timestamp, int]:
    bars = dataset.bars_m1.copy()
    bars["session_date_norm"] = pd.to_datetime(bars["session_date"]).dt.normalize()

    cumulative_notional = (bars["Close"] * bars["Volume"]).groupby(bars["session_date"]).cumsum()
    cumulative_volume = bars["Volume"].groupby(bars["session_date"]).cumsum().replace(0.0, np.nan)
    bars["session_vwap"] = cumulative_notional / cumulative_volume
    bars["atr_current"] = dataset.get_atr_current(int(params.atr_length))

    m15 = (
        bars.resample("15min")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "session_vwap": "last",
                "atr_current": "last",
                "session_date_norm": "last",
            }
        )
        .dropna()
    )

    upper_extreme = m15["session_vwap"] + (float(params.extreme_atr_mult) * m15["atr_current"])
    lower_extreme = m15["session_vwap"] - (float(params.extreme_atr_mult) * m15["atr_current"])
    short_signal = m15["Close"] >= upper_extreme
    long_signal = m15["Close"] <= lower_extreme

    signal_map: dict[pd.Timestamp, int] = {}
    for timestamp, is_long in long_signal.items():
        if bool(is_long):
            signal_map[pd.Timestamp(timestamp) + pd.Timedelta(minutes=15)] = 1
    for timestamp, is_short in short_signal.items():
        if bool(is_short):
            signal_map[pd.Timestamp(timestamp) + pd.Timedelta(minutes=15)] = -1
    return signal_map


def run_vwap_extreme_backtest(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    params: VWAPExtremeParams,
) -> tuple[pd.DataFrame, dict[str, object]]:
    start, stop = _trade_slice_bounds(dataset, trade_dates)
    if start >= stop:
        return pd.DataFrame(), calculate_metrics(pd.DataFrame(), trade_dates)

    cache = _ensure_every_tick_cache(dataset)
    atr_current = dataset.get_atr_current(params.atr_length)
    signal_map = build_vwap_extreme_signal_map(dataset, params)

    timestamps = pd.DatetimeIndex(cache["timestamps"][start:stop])
    session_dates = cache["session_dates"][start:stop]
    open_ticks = cache["open_ticks"][start:stop]
    high_ticks = cache["high_ticks"][start:stop]
    low_ticks = cache["low_ticks"][start:stop]
    close_ticks = cache["close_ticks"][start:stop]
    volume = cache["volume"][start:stop]
    spread_ticks = cache["spread_ticks"][start:stop]
    atr_slice = atr_current[start:stop]

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
        allowed_time = timestamp.dayofweek < 5 and timestamp.hour in set(params.entry_hours)
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


def candidate_row(name: str, params: VWAPExtremeParams, metrics: dict[str, object], summary_path: Path) -> dict[str, object]:
    return {
        "name": name,
        "family": "vwap_extreme_mean_reversion_exact",
        "screening_method": "exact_every_tick_vwap_extreme_entry",
        "comparison_tier": "exact",
        "mt5_ready": False,
        "params": {
            "sl_atr_mult": params.sl_atr_mult,
            "tp_atr_mult": params.tp_atr_mult,
            "extreme_atr_mult": params.extreme_atr_mult,
            "entry_hours": list(params.entry_hours),
            "cooldown_minutes": int(params.cooldown_minutes),
        },
        "test_total_trades": int(metrics["total_trades"]),
        "test_net_profit_brl": float(metrics["net_profit_brl"]),
        "test_profit_factor": float(metrics["profit_factor"]),
        "test_on_tester_value": float(metrics["on_tester_value"]),
        "test_max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "test_win_rate": float(metrics["win_rate"]),
        "notes": "Exact mean-reversion entry against 2x ATR session-VWAP overextensions, with the same session hours and cooldown as the production ladder.",
        "source_artifact": str(summary_path.resolve()),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))

    candidates = [
        ("vwap_extreme_mean_reversion_sl0p84_tp0p30_cd25", VWAPExtremeParams(sl_atr_mult=0.84, tp_atr_mult=0.30)),
        ("vwap_extreme_mean_reversion_sl0p84_tp0p42_cd25", VWAPExtremeParams(sl_atr_mult=0.84, tp_atr_mult=0.42)),
    ]

    results: list[dict[str, object]] = []
    leaderboard_rows: list[dict[str, object]] = []
    for name, params in candidates:
        _, metrics = run_vwap_extreme_backtest(dataset, dataset.trade_dates, params)
        results.append({"name": name, "params": params.__dict__, "metrics": metrics})

    summary = {
        "notes": [
            "Exact mean-reversion entry against 2x ATR session-VWAP overextensions on M15 closes.",
            "Session filter kept to 10:00, 11:00, 12:00, and 14:00 and cooldown fixed at 25 minutes to stay comparable with the production ladder.",
        ],
        "results": results,
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for result, candidate in zip(results, candidates):
        leaderboard_rows.append(candidate_row(result["name"], candidate[1], result["metrics"], summary_path))
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
