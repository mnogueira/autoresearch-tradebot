from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import (
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    resolve_open_gap_exit,
    round_to_tick,
)

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_meanrev_volume_hour_followups_20260329")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _volume_above_20bar_average_filter(dataset: V10Dataset) -> Callable[[dict[str, Any]], bool]:
    volume = dataset.bars_m1["Volume"].astype(float)
    rolling_mean = volume.rolling(20, min_periods=20).mean().to_numpy(dtype=float)
    current_values = volume.to_numpy(dtype=float)

    def _filter(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        baseline = float(rolling_mean[idx])
        if not np.isfinite(baseline) or baseline <= 0.0:
            return False
        return float(current_values[idx]) > baseline

    return _filter


def _allowed_hours_filter(allowed_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    allowed = {int(hour) for hour in allowed_hours}
    return lambda context: int(context["entry_hour"]) in allowed


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    avg_gain = gains.ewm(alpha=1.0 / float(period), adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1.0 / float(period), adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _append_trade(
    trades: list[dict[str, object]],
    session_date: pd.Timestamp,
    direction: int,
    signal_time: pd.Timestamp,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
    exit_price: float,
    stop_price: float,
    target_price: float,
    exit_reason: str,
) -> None:
    pnl_points = float(exit_price - entry_price) * float(direction)
    pnl_brl = (pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL
    trades.append(
        {
            "session_date": pd.Timestamp(session_date).date().isoformat(),
            "signal_time": str(signal_time),
            "entry_time": str(entry_time),
            "exit_time": str(exit_time),
            "direction": "long" if int(direction) == 1 else "short",
            "entry_price": round(float(entry_price), 2),
            "exit_price": round(float(exit_price), 2),
            "stop_price": round(float(stop_price), 2),
            "target_price": round(float(target_price), 2),
            "pnl_points": round(float(pnl_points), 2),
            "pnl_brl": round(float(pnl_brl), 2),
            "fill_reason": "prototype_market_open",
            "exit_reason": exit_reason,
        }
    )


def _prototype_mean_reversion_rsi(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    *,
    allowed_hours: set[int],
    cooldown_minutes: int,
    rsi_period: int = 14,
    rsi_low: float = 30.0,
    rsi_high: float = 70.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    bars_m15 = dataset.m15_complete.copy()
    bars_m15["session_date"] = bars_m15.index.normalize()
    bars_m15["entry_hour"] = bars_m15.index.hour
    bars_m15["weekday"] = bars_m15.index.dayofweek

    rsi = _rsi(bars_m15["Close"].astype(float), int(rsi_period))
    bars_m15["rsi14"] = rsi

    bars_m1 = dataset.bars_m1.loc[
        dataset.bars_m1.index.isin(bars_m15.index),
        ["Open", "High", "Low", "Close", "Spread", "session_date"],
    ].copy()
    bars_m15["entry_open"] = bars_m1["Open"].reindex(bars_m15.index)
    bars_m15["entry_high"] = bars_m1["High"].reindex(bars_m15.index)
    bars_m15["entry_low"] = bars_m1["Low"].reindex(bars_m15.index)
    bars_m15["entry_spread_price"] = bars_m1["Spread"].reindex(bars_m15.index).astype(float) * 0.001

    atr_current = pd.Series(dataset.get_atr_current(int(session_winner_params().ATR_Length)), index=dataset.bars_m1.index)
    bars_m15["atr_current"] = atr_current.reindex(bars_m15.index)
    bars_m15 = bars_m15.dropna(subset=["entry_open", "entry_spread_price", "atr_current"]).copy()

    trades: list[dict[str, object]] = []
    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_time = pd.NaT
    signal_time = pd.NaT
    entry_session = pd.NaT
    last_entry_time = pd.NaT

    for idx in range(1, len(bars_m15)):
        bar = bars_m15.iloc[idx]
        timestamp = pd.Timestamp(bars_m15.index[idx])
        session_date = pd.Timestamp(bar["session_date"])
        bar_open = round_to_tick(float(bar["entry_open"]))
        bar_high = round_to_tick(float(bar["High"]))
        bar_low = round_to_tick(float(bar["Low"]))

        if position != 0:
            gap_price, gap_reason = resolve_open_gap_exit(position, bar_open, stop_price, target_price)
            exit_price = None
            exit_reason = None
            if gap_price is not None:
                exit_price = float(gap_price)
                exit_reason = str(gap_reason)
            elif position == 1:
                if bar_low <= stop_price:
                    exit_price = float(stop_price)
                    exit_reason = "stop_loss"
                elif bar_high >= target_price:
                    exit_price = float(target_price)
                    exit_reason = "take_profit"
            else:
                if bar_high >= stop_price:
                    exit_price = float(stop_price)
                    exit_reason = "stop_loss"
                elif bar_low <= target_price:
                    exit_price = float(target_price)
                    exit_reason = "take_profit"

            if exit_price is not None:
                _append_trade(
                    trades=trades,
                    session_date=entry_session,
                    direction=position,
                    signal_time=signal_time,
                    entry_time=entry_time,
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=float(exit_price),
                    stop_price=stop_price,
                    target_price=target_price,
                    exit_reason=str(exit_reason),
                )
                position = 0
                continue

            if session_date != entry_session:
                _append_trade(
                    trades=trades,
                    session_date=entry_session,
                    direction=position,
                    signal_time=signal_time,
                    entry_time=entry_time,
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=bar_open,
                    stop_price=stop_price,
                    target_price=target_price,
                    exit_reason="forced_day_change",
                )
                position = 0
                continue

        if position != 0:
            continue

        if int(bar["weekday"]) >= 5 or int(bar["entry_hour"]) not in allowed_hours:
            continue
        if pd.notna(last_entry_time):
            delta_minutes = (timestamp - pd.Timestamp(last_entry_time)).total_seconds() / 60.0
            if delta_minutes < float(cooldown_minutes):
                continue

        prev_bar = bars_m15.iloc[idx - 1]
        prev_rsi = float(prev_bar["rsi14"]) if pd.notna(prev_bar["rsi14"]) else np.nan
        atr_value = float(bar["atr_current"]) if pd.notna(bar["atr_current"]) else np.nan
        if not np.isfinite(prev_rsi) or not np.isfinite(atr_value) or atr_value <= 0.0:
            continue

        direction = 0
        if prev_rsi < float(rsi_low):
            direction = 1
        elif prev_rsi > float(rsi_high):
            direction = -1
        if direction == 0:
            continue

        spread_price = float(bar["entry_spread_price"]) if pd.notna(bar["entry_spread_price"]) else 0.0
        if direction == 1:
            entry_price = round_to_tick(bar_open + spread_price)
            stop_price = round_to_tick(entry_price - (atr_value * 0.84))
            target_price = round_to_tick(entry_price + (atr_value * 0.30))
        else:
            entry_price = round_to_tick(bar_open)
            stop_price = round_to_tick(entry_price + (atr_value * 0.84))
            target_price = round_to_tick(entry_price - (atr_value * 0.30))

        signal_time = pd.Timestamp(bars_m15.index[idx - 1])
        entry_time = timestamp
        entry_session = session_date
        last_entry_time = timestamp
        position = int(direction)

    trades_df = pd.DataFrame(trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def run_exact_followups(dataset: V10Dataset) -> dict[str, Any]:
    params = session_winner_params()
    base_hours = {10, 11, 12, 14}
    base_filter = session_filter(base_hours)
    management = ManagementConfig(min_minutes_between_entries=25)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=management,
    )

    volume_filter = _volume_above_20bar_average_filter(dataset)
    volume_trades, volume_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(base_filter, volume_filter),
        management=management,
    )

    skip_hour_results: list[dict[str, Any]] = []
    for label, allowed_hours, note in [
        ("skip_12h", {10, 11, 14}, "Remove 12:00 entries from the current 10/11/12/14 session filter."),
        ("skip_14h", {10, 11, 12}, "Remove 14:00 entries from the current 10/11/12/14 session filter."),
        ("skip_15h", {10, 11, 12, 14}, "Structural no-op in the current exact harness because 15:00 entries are already excluded."),
    ]:
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=_allowed_hours_filter(allowed_hours),
            management=management,
        )
        skip_hour_results.append(
            {
                "name": label,
                "allowed_hours": sorted(int(hour) for hour in allowed_hours),
                "metrics": metrics,
                **_risk_block(trades, dataset.trade_dates),
                "note": note,
            }
        )

    return {
        "reference_tier2_cooldown_25m": {
            "metrics": reference_metrics,
            **_risk_block(reference_trades, dataset.trade_dates),
            "note": "Current exact Tier 2 candidate: session winner with 25-minute cooldown.",
        },
        "signal_bar_volume_above_20bar_average": {
            "metrics": volume_metrics,
            **_risk_block(volume_trades, dataset.trade_dates),
            "note": "Exact follow-up: only allow entries when current M1 signal-bar volume exceeds the rolling 20-bar average.",
        },
        "skip_hour_sweep": skip_hour_results,
    }


def run_rsi_prototype(dataset: V10Dataset) -> dict[str, Any]:
    base_hours = {10, 11, 12, 14}
    mean_reversion_trades, mean_reversion_metrics = _prototype_mean_reversion_rsi(
        dataset=dataset,
        trade_dates=dataset.trade_dates,
        allowed_hours=base_hours,
        cooldown_minutes=25,
    )

    return {
        "rsi14_mean_reversion_prototype": {
            "metrics": mean_reversion_metrics,
            **_risk_block(mean_reversion_trades, dataset.trade_dates),
            "note": "Prototype family, not MT5 parity: use M15 RSI(14) signals, enter at the next M15 open during session hours with the same 25-minute cooldown and ATR-based SL/TP.",
            "parameters": {
                "rsi_period": 14,
                "oversold_threshold": 30,
                "overbought_threshold": 70,
                "allowed_hours": sorted(base_hours),
                "cooldown_minutes": 25,
                "sl_atr_mult": 0.84,
                "tp_atr_mult": 0.30,
            },
        },
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    exact_summary = run_exact_followups(dataset)
    prototype_summary = run_rsi_prototype(dataset)

    summary = {
        **exact_summary,
        **prototype_summary,
        "notes": [
            "The skip-hour and volume-gate variants are exact reruns on the live Tier 2 line.",
            "The RSI mean-reversion family is a separate prototype screen so we do not overstate parity with the Stalker exact engine.",
            "Skip-15h is included because it was requested, but it is structurally a no-op under the current 10/11/12/14 session schedule.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
