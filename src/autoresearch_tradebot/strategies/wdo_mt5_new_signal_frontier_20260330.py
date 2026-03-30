from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Callable

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir


POINT_VALUE_BRL = 10.0
ROUND_TRIP_COST_BRL = 4.0
TICK_SIZE = 0.5
SYMBOL = "WDO$N"
OUTPUT_DIR = artifact_output_dir("wdo_mt5_new_signal_frontier_20260330")


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    signal_fn: Callable[[pd.DataFrame], pd.Series]
    sl_mult: float
    tp_mult: float
    atr_col: str
    entry_start_hour: int
    last_entry_hour: int
    last_entry_minute: int = 30
    force_flat_hour: int = 17
    force_flat_minute: int = 50
    max_hold_bars: int | None = None


def _spec_dict(spec: StrategySpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    return data


def _round_to_tick(value: float) -> float:
    return round(float(value) / TICK_SIZE) * TICK_SIZE


def _fetch_rates(symbol: str, timeframe: int, start: datetime, end: datetime) -> pd.DataFrame:
    mt5.symbol_select(symbol, True)
    chunk_start = start
    chunks: list[pd.DataFrame] = []
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=45), end)
        rates = mt5.copy_rates_range(symbol, timeframe, chunk_start, chunk_end)
        if rates is not None and len(rates) > 0:
            chunks.append(pd.DataFrame(rates))
        chunk_start = chunk_end
    if not chunks:
        raise RuntimeError(f"No rates returned for {symbol} timeframe={timeframe}: {mt5.last_error()}")
    frame = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    frame["time"] = pd.to_datetime(frame["time"], unit="s")
    frame = frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume",
            "real_volume": "RealVolume",
            "spread": "Spread",
        }
    ).set_index("time")
    return frame[["Open", "High", "Low", "Close", "Volume", "Spread", "RealVolume"]].copy()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    prev_close = frame["Close"].shift(1)
    tr = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - prev_close).abs(),
            (frame["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    avg_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_up / avg_down.replace(0.0, np.nan)
    return 100 - (100 / (1 + rs))


def _session_vwap(frame: pd.DataFrame) -> pd.Series:
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3.0
    value = typical * frame["Volume"].replace(0.0, np.nan)
    session = frame.index.normalize()
    cum_value = value.groupby(session).cumsum()
    cum_volume = frame["Volume"].replace(0.0, np.nan).groupby(session).cumsum()
    return (cum_value / cum_volume).ffill()


def _build_feature_frame(m1: pd.DataFrame, m5: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    frame = m1.copy()
    frame["session_date"] = frame.index.normalize()
    frame["entry_hour"] = frame.index.hour
    frame["entry_minute"] = frame.index.minute
    frame["ema8_m1"] = _ema(frame["Close"], 8)
    frame["ema20_m1"] = _ema(frame["Close"], 20)
    frame["rsi5_m1"] = _rsi(frame["Close"], 5)
    frame["vol_avg20_m1"] = frame["Volume"].rolling(20, min_periods=10).mean()
    frame["session_vwap"] = _session_vwap(frame)

    m5_feat = m5.copy()
    m5_feat["ema9_m5"] = _ema(m5_feat["Close"], 9)
    m5_feat["ema21_m5"] = _ema(m5_feat["Close"], 21)
    m5_feat["atr14_m5"] = _atr(m5_feat, 14)
    m5_feat["donchian_high_10"] = m5_feat["High"].rolling(10, min_periods=10).max().shift(1)
    m5_feat["donchian_low_10"] = m5_feat["Low"].rolling(10, min_periods=10).min().shift(1)
    m5_feat["donchian_high_20"] = m5_feat["High"].rolling(20, min_periods=20).max().shift(1)
    m5_feat["donchian_low_20"] = m5_feat["Low"].rolling(20, min_periods=20).min().shift(1)
    m5_feat["donchian_high_30"] = m5_feat["High"].rolling(30, min_periods=30).max().shift(1)
    m5_feat["donchian_low_30"] = m5_feat["Low"].rolling(30, min_periods=30).min().shift(1)

    m15_feat = m15.copy()
    m15_feat["ema20_m15"] = _ema(m15_feat["Close"], 20)
    m15_feat["ema50_m15"] = _ema(m15_feat["Close"], 50)
    m15_feat["atr14_m15"] = _atr(m15_feat, 14)

    daily = frame.groupby("session_date").agg(day_high=("High", "max"), day_low=("Low", "min"), close=("Close", "last"))
    daily["atr14_day"] = _atr(
        daily.rename(columns={"day_high": "High", "day_low": "Low", "close": "Close"})[["High", "Low", "Close"]],
        14,
    )
    daily["atr14_prior"] = daily["atr14_day"].shift(1)
    daily["atr20_mean_prior"] = daily["atr14_prior"].rolling(20, min_periods=10).mean()

    for col in ["ema9_m5", "ema21_m5", "atr14_m5", "donchian_high_10", "donchian_low_10", "donchian_high_20", "donchian_low_20", "donchian_high_30", "donchian_low_30"]:
        frame[col] = m5_feat[col].reindex(frame.index, method="ffill")
    for col in ["ema20_m15", "ema50_m15", "atr14_m15"]:
        frame[col] = m15_feat[col].reindex(frame.index, method="ffill")
    frame["daily_atr14_prior"] = frame["session_date"].map(daily["atr14_prior"])
    frame["daily_atr20_mean_prior"] = frame["session_date"].map(daily["atr20_mean_prior"])
    return frame


def _signal_mtf_trend(frame: pd.DataFrame) -> pd.Series:
    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["ema9_m5"] > frame["ema21_m5"])
        & (frame["Close"] > frame["ema8_m1"])
        & (frame["Close"].shift(1) <= frame["ema8_m1"].shift(1))
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    short_signal = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["ema9_m5"] < frame["ema21_m5"])
        & (frame["Close"] < frame["ema8_m1"])
        & (frame["Close"].shift(1) >= frame["ema8_m1"].shift(1))
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_volume_spike(frame: pd.DataFrame) -> pd.Series:
    spike = frame["Volume"] > (1.5 * frame["vol_avg20_m1"])
    long_signal = (
        spike
        & (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame["ema9_m5"])
        & (frame["Close"] > frame["Open"])
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    short_signal = (
        spike
        & (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema9_m5"])
        & (frame["Close"] < frame["Open"])
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_mean_revert_afternoon(frame: pd.DataFrame) -> pd.Series:
    low_vol_day = frame["daily_atr14_prior"] <= frame["daily_atr20_mean_prior"]
    m5_atr = frame["atr14_m5"].replace(0.0, np.nan)
    vwap_distance = frame["Close"] - frame["session_vwap"]
    long_signal = (
        low_vol_day
        & frame["entry_hour"].between(14, 16)
        & (vwap_distance < (-1.5 * m5_atr))
        & (frame["rsi5_m1"] < 25)
    )
    short_signal = (
        low_vol_day
        & frame["entry_hour"].between(14, 16)
        & (vwap_distance > (1.5 * m5_atr))
        & (frame["rsi5_m1"] > 75)
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_vwap_fail_short(frame: pd.DataFrame) -> pd.Series:
    short_signal = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame["ema21_m5"])
        & (frame["High"] > frame["session_vwap"])
        & (frame["Close"] < frame["session_vwap"])
        & (frame["entry_hour"].isin([10, 11, 12]))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[short_signal] = -1
    return signal


def _signal_donchian_breakout(frame: pd.DataFrame, lookback: int) -> pd.Series:
    high_col = f"donchian_high_{lookback}"
    low_col = f"donchian_low_{lookback}"
    long_signal = (
        (frame["ema20_m15"] > frame["ema50_m15"])
        & (frame["Close"] > frame[high_col])
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    short_signal = (
        (frame["ema20_m15"] < frame["ema50_m15"])
        & (frame["Close"] < frame[low_col])
        & (frame["entry_hour"].isin([10, 12, 13]))
    )
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _calc_metrics(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, float | int | str]:
    if trades.empty:
        return {
            "start_date": pd.Timestamp(trade_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(trade_dates[-1]).date().isoformat(),
            "trading_days": int(len(trade_dates)),
            "total_trades": 0,
            "win_rate": 0.0,
            "net_profit_brl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_profit_brl": 0.0,
        }
    pnl = trades["pnl_brl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.abs().sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    daily_pnl = (
        trades.assign(session_date=pd.to_datetime(trades["session_date"]))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
    )
    equity = 10000.0 + daily_pnl.cumsum()
    peaks = equity.cummax()
    dd = ((peaks - equity) / peaks.replace(0.0, np.nan) * 100.0).max()
    return {
        "start_date": pd.Timestamp(trade_dates[0]).date().isoformat(),
        "end_date": pd.Timestamp(trade_dates[-1]).date().isoformat(),
        "trading_days": int(len(trade_dates)),
        "total_trades": int(len(trades)),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "net_profit_brl": round(float(pnl.sum()), 2),
        "profit_factor": round(float(pf), 4) if np.isfinite(pf) else float("inf"),
        "max_drawdown_pct": round(float(dd), 2),
        "avg_profit_brl": round(float(pnl.mean()), 2),
    }


def _monthly_walkforward(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    months = pd.Index(sorted(pd.to_datetime(trade_dates).to_period("M").unique()))
    folds: list[dict[str, object]] = []
    for i in range(3, len(months)):
        train_months = months[i - 3 : i]
        test_month = months[i]
        train_dates = pd.Index([d for d in pd.to_datetime(trade_dates) if d.to_period("M") in set(train_months)])
        test_dates = pd.Index([d for d in pd.to_datetime(trade_dates) if d.to_period("M") == test_month])
        if len(test_dates) == 0:
            continue
        train_subset = trades.loc[trades["session_date"].isin(train_dates.strftime("%Y-%m-%d"))].reset_index(drop=True)
        test_subset = trades.loc[trades["session_date"].isin(test_dates.strftime("%Y-%m-%d"))].reset_index(drop=True)
        test_metrics = _calc_metrics(test_subset, test_dates)
        folds.append(
            {
                "train_months": [str(x) for x in train_months],
                "test_month": str(test_month),
                "train_metrics": _calc_metrics(train_subset, train_dates),
                "test_metrics": test_metrics,
                "pass": bool(test_metrics["net_profit_brl"] > 0 and float(test_metrics["profit_factor"]) > 1.0),
            }
        )
    return {
        "total_folds": len(folds),
        "passed_folds": int(sum(1 for fold in folds if fold["pass"])),
        "folds": folds,
    }


def _backtest(frame: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    signal = spec.signal_fn(frame).fillna(0).astype(int)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    cutoff = spec.force_flat_hour * 60 + spec.force_flat_minute
    last_entry_cutoff = spec.last_entry_hour * 60 + spec.last_entry_minute

    trades: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    position: dict[str, object] | None = None

    idx = frame.index
    for i in range(len(frame)):
        ts = idx[i]
        bar = frame.iloc[i]
        minute_of_day = ts.hour * 60 + ts.minute

        if position is not None:
            if minute_of_day >= cutoff:
                exit_price = _round_to_tick(float(bar["Open"]))
                pnl_points = (exit_price - float(position["entry_price"])) * int(position["direction"])
                trades.append(
                    {
                        "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                        "entry_time": str(position["entry_time"]),
                        "exit_time": str(ts),
                        "direction": "long" if int(position["direction"]) == 1 else "short",
                        "entry_price": float(position["entry_price"]),
                        "exit_price": exit_price,
                        "pnl_points": round(pnl_points, 2),
                        "pnl_brl": round((pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL, 2),
                        "exit_reason": "time_cutoff",
                    }
                )
                position = None
            else:
                direction = int(position["direction"])
                stop_price = float(position["stop_price"])
                target_price = float(position["target_price"])
                open_price = _round_to_tick(float(bar["Open"]))
                high_price = _round_to_tick(float(bar["High"]))
                low_price = _round_to_tick(float(bar["Low"]))
                exit_price = None
                exit_reason = None
                if direction == 1:
                    if open_price <= stop_price:
                        exit_price, exit_reason = open_price, "stop_gap_open"
                    elif open_price >= target_price:
                        exit_price, exit_reason = open_price, "target_gap_open"
                    elif low_price <= stop_price and high_price >= target_price:
                        exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                    elif low_price <= stop_price:
                        exit_price, exit_reason = stop_price, "stop_loss"
                    elif high_price >= target_price:
                        exit_price, exit_reason = target_price, "take_profit"
                else:
                    if open_price >= stop_price:
                        exit_price, exit_reason = open_price, "stop_gap_open"
                    elif open_price <= target_price:
                        exit_price, exit_reason = open_price, "target_gap_open"
                    elif high_price >= stop_price and low_price <= target_price:
                        exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                    elif high_price >= stop_price:
                        exit_price, exit_reason = stop_price, "stop_loss"
                    elif low_price <= target_price:
                        exit_price, exit_reason = target_price, "take_profit"
                if exit_price is None and spec.max_hold_bars is not None and i - int(position["entry_index"]) >= spec.max_hold_bars:
                    exit_price, exit_reason = _round_to_tick(float(bar["Close"])), "max_hold"
                if exit_price is not None:
                    pnl_points = (float(exit_price) - float(position["entry_price"])) * direction
                    trades.append(
                        {
                            "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                            "entry_time": str(position["entry_time"]),
                            "exit_time": str(ts),
                            "direction": "long" if direction == 1 else "short",
                            "entry_price": float(position["entry_price"]),
                            "exit_price": float(exit_price),
                            "pnl_points": round(pnl_points, 2),
                            "pnl_brl": round((pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL, 2),
                            "exit_reason": exit_reason,
                        }
                    )
                    position = None

        if position is None and pending is not None:
            open_price = _round_to_tick(float(bar["Open"]))
            direction = int(pending["direction"])
            position = {
                "session_date": pending["session_date"],
                "entry_time": ts,
                "entry_index": i,
                "direction": direction,
                "entry_price": open_price,
                "stop_price": pending["stop_price"],
                "target_price": pending["target_price"],
            }
            pending = None

        if position is None and pending is None and i < len(frame) - 1:
            if minute_of_day < (spec.entry_start_hour * 60) or minute_of_day > last_entry_cutoff:
                continue
            direction = int(signal.iloc[i])
            if direction == 0:
                continue
            atr_value = float(bar[spec.atr_col]) if pd.notna(bar[spec.atr_col]) else np.nan
            if not np.isfinite(atr_value) or atr_value <= 0.0:
                continue
            next_open = _round_to_tick(float(frame.iloc[i + 1]["Open"]))
            if direction == 1:
                stop_price = _round_to_tick(next_open - (spec.sl_mult * atr_value))
                target_price = _round_to_tick(next_open + (spec.tp_mult * atr_value))
            else:
                stop_price = _round_to_tick(next_open + (spec.sl_mult * atr_value))
                target_price = _round_to_tick(next_open - (spec.tp_mult * atr_value))
            pending = {
                "session_date": ts.normalize(),
                "direction": direction,
                "stop_price": stop_price,
                "target_price": target_price,
            }

    return pd.DataFrame(trades)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        end = datetime.now()
        start = end - timedelta(days=365)
        m1 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M1, start, end)
        m5 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M5, start, end)
        m15 = _fetch_rates(SYMBOL, mt5.TIMEFRAME_M15, start, end)
    finally:
        mt5.shutdown()

    frame = _build_feature_frame(m1, m5, m15)
    trade_dates = pd.Index(sorted(frame.index.normalize().unique()))
    recent_90 = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]

    specs = [
        StrategySpec(
            name="mtf_trend_pullback",
            description="M15 EMA trend + M5 trend agreement + M1 re-entry through EMA8, skipping 11h.",
            signal_fn=_signal_mtf_trend,
            sl_mult=1.0,
            tp_mult=1.5,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
        StrategySpec(
            name="volume_spike_trend",
            description="Volume-spike continuation with M15/M5 trend agreement.",
            signal_fn=_signal_volume_spike,
            sl_mult=1.0,
            tp_mult=1.8,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
        StrategySpec(
            name="low_vol_afternoon_mean_revert",
            description="Low-vol afternoon mean reversion back to VWAP on stretched moves.",
            signal_fn=_signal_mean_revert_afternoon,
            sl_mult=1.0,
            tp_mult=1.0,
            atr_col="atr14_m5",
            entry_start_hour=14,
            last_entry_hour=16,
            last_entry_minute=30,
            max_hold_bars=45,
        ),
        StrategySpec(
            name="vwap_fail_short",
            description="Short only after failed push above session VWAP in a broader downtrend.",
            signal_fn=_signal_vwap_fail_short,
            sl_mult=1.0,
            tp_mult=1.5,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=12,
            last_entry_minute=59,
            max_hold_bars=60,
        ),
        StrategySpec(
            name="donchian20_mtf",
            description="M15-trend Donchian-20 breakout with ATR exits.",
            signal_fn=lambda f: _signal_donchian_breakout(f, 20),
            sl_mult=1.0,
            tp_mult=1.8,
            atr_col="atr14_m5",
            entry_start_hour=10,
            last_entry_hour=14,
        ),
    ]

    results: list[dict[str, object]] = []
    ranked_rows: list[dict[str, object]] = []

    for spec in specs:
        trades = _backtest(frame, spec)
        metrics = _calc_metrics(trades, trade_dates)
        walkforward = _monthly_walkforward(trades, trade_dates)
        recent_trades = trades.loc[trades["session_date"].isin(pd.Index(recent_90).strftime("%Y-%m-%d"))].reset_index(drop=True)
        recent_metrics = _calc_metrics(recent_trades, recent_90)
        payload = {
            "name": spec.name,
            "description": spec.description,
            "params": _spec_dict(spec),
            "metrics": metrics,
            "walkforward_3m_train_1m_test_1m_step": walkforward,
            "recent_jan_mar_2026": recent_metrics,
        }
        results.append(payload)
        ranked_rows.append(
            {
                "name": spec.name,
                "net_profit_brl": metrics["net_profit_brl"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "total_trades": metrics["total_trades"],
                "recent_jan_mar_net_profit_brl": recent_metrics["net_profit_brl"],
                "wf_passed_folds": walkforward["passed_folds"],
                "wf_total_folds": walkforward["total_folds"],
            }
        )
        trades.to_csv(OUTPUT_DIR / f"{spec.name}_trades.csv", index=False)

    ranked_rows = sorted(
        ranked_rows,
        key=lambda row: (
            float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
            -float(row["max_drawdown_pct"]),
            float(row["net_profit_brl"]),
        ),
        reverse=True,
    )
    summary = {
        "symbol": SYMBOL,
        "data_window": {
            "start": m1.index.min().isoformat(),
            "end": m1.index.max().isoformat(),
            "m1_bars": int(len(m1)),
            "m5_bars": int(len(m5)),
            "m15_bars": int(len(m15)),
        },
        "cost_model": {
            "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
            "tick_size": TICK_SIZE,
            "point_value_brl": POINT_VALUE_BRL,
        },
        "ranked_variants": ranked_rows,
        "variants": results,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
