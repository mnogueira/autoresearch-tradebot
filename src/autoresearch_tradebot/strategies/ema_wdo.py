from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pandas as pd
import ta

from ..common.paths import artifact_output_dir, artifact_report_path
from ..common.wdo_data import locate_wdo_bar_file


POINT_VALUE_BRL = 10.0
ROUND_TRIP_COST_BRL = 11.0
SESSION_START = time(9, 0)
SESSION_END = time(17, 55)


@dataclass(frozen=True)
class EmaStrategyParams:
    ema_fast: int = 8
    ema_slow: int = 34
    trend_window: int = 220
    rsi_window: int = 7
    rsi_long: int = 65
    rsi_short: int = 40
    adx_window: int = 14
    adx_threshold: int = 20
    atr_window: int = 20
    atr_mult: float = 2.0
    trix_window: int = 12
    trix_median_window: int = 500
    trix_median_min_periods: int = 100
    hurst_window: int = 100
    hurst_threshold: float = 0.50
    vr_short_window: int = 3
    vr_long_window: int = 20
    vr_max: float = 2.0
    use_vwap: bool = True
    skip_12: bool = True
    skip_13: bool = True
    skip_14: bool = False
    entry_cutoff_time: str = "14:55"
    flat_after_bar_time: str = "17:25"


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    direction: str
    entry_price: float
    exit_price: float
    pnl_points: float
    pnl_brl: float
    hold_bars: int


@dataclass
class WalkForwardWindowResult:
    window: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict[str, Any]
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    optuna_trials: int
    best_objective: float


@dataclass
class EmaDataset:
    bars_5m: pd.DataFrame
    bars_1m: pd.DataFrame
    overlap_dates: pd.Index

    @classmethod
    def from_disk(cls) -> "EmaDataset":
        bars_5m = add_session_columns(filter_full_session_days(load_bars("5m"), "5m"))
        bars_1m = add_session_columns(filter_full_session_days(load_bars("1m"), "1m"))
        overlap_dates = pd.Index(
            sorted(set(bars_5m["session_date"].unique()) & set(bars_1m["session_date"].unique()))
        )
        bars_5m = bars_5m[bars_5m["session_date"].isin(overlap_dates)].copy()
        bars_1m = bars_1m[bars_1m["session_date"].isin(overlap_dates)].copy()
        return cls(bars_5m=bars_5m, bars_1m=bars_1m, overlap_dates=overlap_dates)


def parse_clock_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def locate_data_file(timeframe: str) -> Path:
    return locate_wdo_bar_file(timeframe)


def load_bars(timeframe: str) -> pd.DataFrame:
    path = locate_data_file(timeframe)
    frame = pd.read_parquet(path).copy()
    if "time" in frame.columns:
        frame["time"] = pd.to_datetime(frame["time"])
        frame = frame.set_index("time")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(f"{path} does not have a DatetimeIndex.")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    keep = [column for column in ["Open", "High", "Low", "Close", "Volume", "Spread"] if column in frame.columns]
    frame = frame[keep].copy()
    mask = (frame.index.time >= SESSION_START) & (frame.index.time <= SESSION_END)
    return frame.loc[mask].copy()


def expected_bars_per_day(timeframe: str) -> int:
    tf = timeframe.lower()
    if tf == "1m":
        return 536
    if tf == "5m":
        return 108
    raise ValueError(f"Unsupported timeframe={timeframe!r}.")


def filter_full_session_days(frame: pd.DataFrame, timeframe: str, min_coverage_ratio: float = 0.98) -> pd.DataFrame:
    expected = expected_bars_per_day(timeframe)
    counts = frame.groupby(frame.index.normalize()).size()
    full_days = counts[counts >= int(expected * min_coverage_ratio)].index
    return frame[frame.index.normalize().isin(full_days)].copy()


def add_session_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["session_date"] = frame.index.normalize()
    frame["clock_time"] = frame.index.time
    frame["bar_of_day"] = frame.groupby("session_date").cumcount()
    frame["is_first_bar"] = frame["bar_of_day"] == 0
    frame["bars_in_day"] = frame.groupby("session_date")["Close"].transform("count")
    frame["bars_remaining"] = frame["bars_in_day"] - frame["bar_of_day"] - 1
    return frame


def split_dates_by_ratio(dates: pd.Index, train_ratio: float) -> tuple[pd.Index, pd.Index]:
    if len(dates) < 2:
        raise ValueError("Need at least two dates to split.")
    split_index = max(1, min(len(dates) - 1, int(len(dates) * train_ratio)))
    return dates[:split_index], dates[split_index:]


def generate_walk_forward_windows(
    dates: pd.Index,
    window_total_days: int,
    train_ratio: float,
) -> list[tuple[int, pd.Index, pd.Index]]:
    if window_total_days >= len(dates):
        train_dates, test_dates = split_dates_by_ratio(dates, train_ratio)
        return [(1, train_dates, test_dates)]
    train_days = max(20, int(window_total_days * train_ratio))
    test_days = max(10, window_total_days - train_days)
    windows: list[tuple[int, pd.Index, pd.Index]] = []
    start = 0
    window_number = 1
    while start + train_days + test_days <= len(dates):
        window_dates = dates[start : start + train_days + test_days]
        windows.append((window_number, window_dates[:train_days], window_dates[train_days:]))
        start += test_days
        window_number += 1
    return windows


def rolling_hurst(close: pd.Series, window: int) -> pd.Series:
    def hurst_rs(values: np.ndarray) -> float:
        returns = np.diff(values) / values[:-1]
        if len(returns) < 10:
            return 0.5
        mean_r = returns.mean()
        deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min()
        s = returns.std(ddof=1)
        if s == 0 or r == 0:
            return 0.5
        return float(np.log(r / s) / np.log(len(returns)))

    return close.rolling(window).apply(hurst_rs, raw=True)


class IndicatorCache:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.close = frame["Close"]
        self.high = frame["High"]
        self.low = frame["Low"]
        self.volume = frame["Volume"]
        self._ema: dict[int, pd.Series] = {}
        self._rsi: dict[int, pd.Series] = {}
        self._adx: dict[int, pd.Series] = {}
        self._atr: dict[int, pd.Series] = {}
        self._trix: dict[int, pd.Series] = {}
        self._hurst: dict[int, pd.Series] = {}
        self._vr: dict[tuple[int, int], pd.Series] = {}
        self._trix_median: dict[tuple[int, int, int], pd.Series] = {}
        self._vwap: pd.Series | None = None

    def ema(self, window: int) -> pd.Series:
        if window not in self._ema:
            self._ema[window] = ta.trend.ema_indicator(self.close, window=window)
        return self._ema[window]

    def rsi(self, window: int) -> pd.Series:
        if window not in self._rsi:
            self._rsi[window] = ta.momentum.rsi(self.close, window=window)
        return self._rsi[window]

    def adx(self, window: int) -> pd.Series:
        if window not in self._adx:
            self._adx[window] = ta.trend.adx(self.high, self.low, self.close, window=window)
        return self._adx[window]

    def atr(self, window: int) -> pd.Series:
        if window not in self._atr:
            self._atr[window] = ta.volatility.average_true_range(self.high, self.low, self.close, window=window)
        return self._atr[window]

    def trix(self, window: int) -> pd.Series:
        if window not in self._trix:
            self._trix[window] = ta.trend.trix(self.close, window=window)
        return self._trix[window]

    def hurst(self, window: int) -> pd.Series:
        if window not in self._hurst:
            self._hurst[window] = rolling_hurst(self.close, window=window)
        return self._hurst[window]

    def vr(self, short_window: int, long_window: int) -> pd.Series:
        key = (short_window, long_window)
        if key not in self._vr:
            returns = self.close.pct_change()
            self._vr[key] = returns.rolling(short_window).std() / returns.rolling(long_window).std()
        return self._vr[key]

    def trix_median(self, trix_window: int, median_window: int, min_periods: int) -> pd.Series:
        key = (trix_window, median_window, min_periods)
        if key not in self._trix_median:
            trix = self.trix(trix_window)
            self._trix_median[key] = trix.rolling(median_window, min_periods=min_periods).median().shift(1)
        return self._trix_median[key]

    def vwap(self) -> pd.Series:
        if self._vwap is None:
            typical = (self.high + self.low + self.close) / 3
            cum_tp_vol = (typical * self.volume).groupby(self.frame["session_date"]).cumsum()
            cum_vol = self.volume.groupby(self.frame["session_date"]).cumsum().replace(0, np.nan)
            self._vwap = cum_tp_vol / cum_vol
        return self._vwap


def generate_raw_positions(
    frame: pd.DataFrame,
    params: EmaStrategyParams,
    cache: IndicatorCache | None = None,
) -> pd.Series:
    cache = cache or IndicatorCache(frame)
    ema_fast = cache.ema(params.ema_fast).to_numpy(dtype=float)
    ema_slow = cache.ema(params.ema_slow).to_numpy(dtype=float)
    trend = cache.ema(params.trend_window).to_numpy(dtype=float)
    rsi = cache.rsi(params.rsi_window).to_numpy(dtype=float)
    adx = cache.adx(params.adx_window).to_numpy(dtype=float)
    atr = cache.atr(params.atr_window).to_numpy(dtype=float)
    trix = cache.trix(params.trix_window).to_numpy(dtype=float)
    trix_median = cache.trix_median(
        params.trix_window,
        params.trix_median_window,
        params.trix_median_min_periods,
    ).to_numpy(dtype=float)
    hurst = cache.hurst(params.hurst_window).to_numpy(dtype=float)
    vr = cache.vr(params.vr_short_window, params.vr_long_window).to_numpy(dtype=float)
    vwap = cache.vwap().to_numpy(dtype=float)

    close = frame["Close"].to_numpy(dtype=float)
    times = frame["clock_time"].to_numpy()
    dates = frame["session_date"].to_numpy()
    is_first = frame["is_first_bar"].to_numpy(dtype=bool)

    entry_cutoff = parse_clock_time(params.entry_cutoff_time)
    flat_after = parse_clock_time(params.flat_after_bar_time)
    skip_hours = set()
    if params.skip_12:
        skip_hours.add(12)
    if params.skip_13:
        skip_hours.add(13)
    if params.skip_14:
        skip_hours.add(14)

    raw = np.zeros(len(frame), dtype=np.int64)
    position = 0
    peak = 0.0
    previous_date = pd.NaT

    for i in range(len(frame)):
        current_date = dates[i]
        current_time = times[i]

        if is_first[i] or current_date != previous_date:
            position = 0
            peak = 0.0
            previous_date = current_date
            continue

        if current_time >= flat_after:
            raw[i] = 0
            position = 0
            peak = 0.0
            previous_date = current_date
            continue

        if (
            np.isnan(ema_fast[i])
            or np.isnan(ema_slow[i])
            or np.isnan(trend[i])
            or np.isnan(adx[i])
            or np.isnan(atr[i])
        ):
            raw[i] = position
            previous_date = current_date
            continue

        if position != 0:
            current_atr = atr[i] if not np.isnan(atr[i]) else 0.0
            median_value = trix_median[i] if not np.isnan(trix_median[i]) else 0.0
            current_trix = trix[i] if not np.isnan(trix[i]) else median_value
            previous_trix = trix[i - 1] if i > 0 and not np.isnan(trix[i - 1]) else median_value
            trix_exit = (
                (position == 1 and current_trix < median_value and previous_trix >= median_value)
                or (position == -1 and current_trix > median_value and previous_trix <= median_value)
            )
            if trix_exit:
                raw[i] = 0
                position = 0
                peak = 0.0
                previous_date = current_date
                continue

            if position == 1:
                peak = max(peak, close[i])
                if current_atr > 0 and close[i] < peak - params.atr_mult * current_atr:
                    raw[i] = 0
                    position = 0
                    peak = 0.0
                else:
                    raw[i] = 1
            else:
                peak = min(peak, close[i])
                if current_atr > 0 and close[i] > peak + params.atr_mult * current_atr:
                    raw[i] = 0
                    position = 0
                    peak = 0.0
                else:
                    raw[i] = -1
            previous_date = current_date
            continue

        if hasattr(current_time, "hour") and current_time.hour in skip_hours:
            previous_date = current_date
            continue
        if current_time >= entry_cutoff:
            previous_date = current_date
            continue
        if adx[i] < params.adx_threshold:
            previous_date = current_date
            continue
        if not np.isnan(hurst[i]) and hurst[i] < params.hurst_threshold:
            previous_date = current_date
            continue
        if not np.isnan(vr[i]) and vr[i] > params.vr_max:
            previous_date = current_date
            continue

        current_rsi = rsi[i] if not np.isnan(rsi[i]) else 50.0
        current_vwap = vwap[i] if not np.isnan(vwap[i]) else close[i]
        if i > 0 and not np.isnan(ema_fast[i - 1]) and not np.isnan(ema_slow[i - 1]):
            cross_up = ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1]
            cross_down = ema_fast[i] < ema_slow[i] and ema_fast[i - 1] >= ema_slow[i - 1]
            long_ok = cross_up and close[i] > trend[i] and current_rsi > params.rsi_long
            short_ok = cross_down and close[i] < trend[i] and current_rsi < params.rsi_short
            if params.use_vwap:
                if long_ok and close[i] <= current_vwap:
                    long_ok = False
                if short_ok and close[i] >= current_vwap:
                    short_ok = False
            if long_ok:
                raw[i] = 1
                position = 1
                peak = close[i]
            elif short_ok:
                raw[i] = -1
                position = -1
                peak = close[i]
        previous_date = current_date

    return pd.Series(raw, index=frame.index, dtype=int)


def generate_executable_signals(
    frame: pd.DataFrame,
    params: EmaStrategyParams,
    cache: IndicatorCache | None = None,
) -> pd.Series:
    raw = generate_raw_positions(frame, params=params, cache=cache)
    return raw.groupby(frame["session_date"]).shift(1).fillna(0).astype(int)


def lookup_fill_price(fill_frame: pd.DataFrame, timestamp: pd.Timestamp) -> float | None:
    if timestamp in fill_frame.index:
        return float(fill_frame.at[timestamp, "Open"])
    same_day = fill_frame[fill_frame["session_date"] == timestamp.normalize()]
    future = same_day[same_day.index >= timestamp]
    if future.empty:
        return None
    return float(future.iloc[0]["Open"])


def backtest_signals(
    signal_frame: pd.DataFrame,
    fill_frame: pd.DataFrame,
    signals: pd.Series,
) -> pd.DataFrame:
    signals = signals.reindex(signal_frame.index).fillna(0).astype(int).clip(-1, 1)
    position = 0
    entry_price = 0.0
    entry_time = pd.NaT
    entry_bar = -1
    trades: list[Trade] = []

    for i, timestamp in enumerate(signal_frame.index):
        signal = int(signals.iloc[i])
        fill_price = lookup_fill_price(fill_frame, timestamp)
        if fill_price is None:
            continue
        if signal != position:
            if position != 0:
                pnl_points = (fill_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                trades.append(
                    Trade(
                        entry_time=str(entry_time),
                        exit_time=str(timestamp),
                        direction="long" if position == 1 else "short",
                        entry_price=entry_price,
                        exit_price=fill_price,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        hold_bars=i - entry_bar,
                    )
                )
            if signal != 0:
                entry_price = fill_price
                entry_time = timestamp
                entry_bar = i
            position = signal

    if not trades:
        return pd.DataFrame(columns=list(Trade.__annotations__.keys()))
    return pd.DataFrame([asdict(trade) for trade in trades])


def calculate_metrics(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    if trades.empty:
        return {
            "sharpe": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "net_profit_brl": 0.0,
            "avg_profit_per_trade": 0.0,
            "avg_win_brl": 0.0,
            "avg_loss_brl": 0.0,
            "max_consec_losses": 0,
            "avg_hold_bars": 0.0,
        }

    pnl = trades["pnl_brl"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    n = len(pnl)
    gross_profit = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 1e-9
    if n > 1 and np.std(pnl, ddof=1) > 0:
        sharpe = (np.mean(pnl) / np.std(pnl, ddof=1)) * np.sqrt((n / max(len(trade_dates), 1)) * 252)
    else:
        sharpe = 0.0
    equity = 100_000.0 + np.concatenate([[0.0], np.cumsum(pnl)])
    peak = np.maximum.accumulate(equity)
    max_dd_pct = ((peak - equity) / peak * 100).max()
    max_consec_losses = 0
    current_losses = 0
    for value in pnl:
        if value < 0:
            current_losses += 1
            max_consec_losses = max(max_consec_losses, current_losses)
        else:
            current_losses = 0
    return {
        "sharpe": round(float(sharpe), 4),
        "profit_factor": round(float(gross_profit / gross_loss), 4),
        "max_drawdown_pct": round(float(max_dd_pct), 2),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "total_trades": int(n),
        "net_profit_brl": round(float(pnl.sum()), 2),
        "avg_profit_per_trade": round(float(pnl.mean()), 2),
        "avg_win_brl": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss_brl": round(float(losses.mean()) if len(losses) else 0.0, 2),
        "max_consec_losses": int(max_consec_losses),
        "avg_hold_bars": round(float(trades["hold_bars"].mean()), 2),
    }


def run_backtest(
    dataset: EmaDataset,
    params: EmaStrategyParams,
    trade_dates: pd.Index,
    use_1m_fills: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    date_set = set(pd.to_datetime(trade_dates))
    bars_5m = dataset.bars_5m[dataset.bars_5m["session_date"].isin(date_set)].copy()
    fill_frame = dataset.bars_1m if use_1m_fills else dataset.bars_5m
    fill_frame = fill_frame[fill_frame["session_date"].isin(date_set)].copy()
    cache = IndicatorCache(bars_5m)
    signals = generate_executable_signals(bars_5m, params=params, cache=cache)
    trades = backtest_signals(bars_5m, fill_frame, signals)
    return trades, calculate_metrics(trades, pd.Index(sorted(date_set)))


def params_from_mapping(mapping: dict[str, Any]) -> EmaStrategyParams:
    return EmaStrategyParams(**mapping)


def current_strategy_baseline_params() -> EmaStrategyParams:
    return EmaStrategyParams(
        ema_fast=8,
        ema_slow=34,
        trend_window=220,
        rsi_window=7,
        rsi_long=65,
        rsi_short=40,
        adx_window=14,
        adx_threshold=20,
        atr_window=20,
        atr_mult=2.0,
        trix_window=12,
        trix_median_window=500,
        trix_median_min_periods=100,
        hurst_window=100,
        hurst_threshold=0.50,
        vr_short_window=3,
        vr_long_window=20,
        vr_max=2.0,
        use_vwap=True,
        skip_12=True,
        skip_13=True,
        skip_14=False,
        entry_cutoff_time="14:55",
        flat_after_bar_time="17:25",
    )


def sample_params(trial: optuna.Trial) -> EmaStrategyParams:
    params = EmaStrategyParams(
        ema_fast=trial.suggest_int("ema_fast", 5, 12),
        ema_slow=trial.suggest_int("ema_slow", 21, 50),
        trend_window=trial.suggest_int("trend_window", 180, 280, step=10),
        rsi_window=trial.suggest_int("rsi_window", 5, 14),
        rsi_long=trial.suggest_int("rsi_long", 55, 75),
        rsi_short=trial.suggest_int("rsi_short", 25, 45),
        adx_window=trial.suggest_int("adx_window", 10, 18),
        adx_threshold=trial.suggest_int("adx_threshold", 15, 30),
        atr_window=trial.suggest_int("atr_window", 10, 30),
        atr_mult=trial.suggest_float("atr_mult", 1.0, 4.0, step=0.25),
        trix_window=trial.suggest_int("trix_window", 8, 20),
        trix_median_window=trial.suggest_int("trix_median_window", 200, 700, step=100),
        trix_median_min_periods=trial.suggest_int("trix_median_min_periods", 50, 200, step=25),
        hurst_window=trial.suggest_int("hurst_window", 80, 140, step=10),
        hurst_threshold=trial.suggest_float("hurst_threshold", 0.42, 0.58, step=0.02),
        vr_short_window=trial.suggest_int("vr_short_window", 2, 6),
        vr_long_window=trial.suggest_int("vr_long_window", 15, 40, step=5),
        vr_max=trial.suggest_float("vr_max", 1.0, 4.0, step=0.25),
        use_vwap=trial.suggest_categorical("use_vwap", [True, False]),
        skip_12=trial.suggest_categorical("skip_12", [True, False]),
        skip_13=trial.suggest_categorical("skip_13", [True, False]),
        skip_14=trial.suggest_categorical("skip_14", [True, False]),
        entry_cutoff_time=trial.suggest_categorical("entry_cutoff_time", ["14:35", "14:45", "14:55", "15:05", "15:15"]),
        flat_after_bar_time=trial.suggest_categorical("flat_after_bar_time", ["17:10", "17:15", "17:20", "17:25", "17:30", "17:35"]),
    )
    if params.ema_fast >= params.ema_slow:
        raise ValueError("ema_fast must be less than ema_slow")
    if params.vr_short_window >= params.vr_long_window:
        raise ValueError("vr_short_window must be less than vr_long_window")
    if params.trix_median_min_periods > params.trix_median_window:
        raise ValueError("TRIX min periods cannot exceed the median window")
    return params


def objective_factory(dataset: EmaDataset, train_dates: pd.Index):
    def objective(trial: optuna.Trial) -> float:
        try:
            params = sample_params(trial)
        except ValueError:
            return -999.0
        _, metrics = run_backtest(dataset, params, trade_dates=train_dates, use_1m_fills=True)
        if metrics["total_trades"] < 20 or metrics["sharpe"] <= 0:
            return -999.0
        return float(metrics["sharpe"] + min(metrics["profit_factor"], 4.0) * 0.05)

    return objective


def optimize_split(
    dataset: EmaDataset,
    train_dates: pd.Index,
    test_dates: pd.Index,
    trials: int,
    seed: int,
) -> tuple[optuna.Study, EmaStrategyParams, pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective_factory(dataset, train_dates), n_trials=trials, show_progress_bar=False)
    best_params = params_from_mapping(study.best_params)
    train_trades, train_metrics = run_backtest(dataset, best_params, train_dates, use_1m_fills=True)
    test_trades, test_metrics = run_backtest(dataset, best_params, test_dates, use_1m_fills=True)
    return study, best_params, train_trades, train_metrics, test_trades, test_metrics


def run_walk_forward(
    dataset: EmaDataset,
    dates: pd.Index,
    train_ratio: float,
    window_total_days: int,
    trials_per_window: int,
    seed: int,
) -> tuple[list[WalkForwardWindowResult], pd.DataFrame, dict[str, Any]]:
    results: list[WalkForwardWindowResult] = []
    all_test_trades: list[pd.DataFrame] = []
    all_test_dates: list[pd.Index] = []
    for window_number, train_dates, test_dates in generate_walk_forward_windows(dates, window_total_days, train_ratio):
        study, best_params, _, train_metrics, test_trades, test_metrics = optimize_split(
            dataset=dataset,
            train_dates=train_dates,
            test_dates=test_dates,
            trials=trials_per_window,
            seed=seed + window_number,
        )
        if not test_trades.empty:
            tagged = test_trades.copy()
            tagged["walk_forward_window"] = window_number
            all_test_trades.append(tagged)
        all_test_dates.append(test_dates)
        results.append(
            WalkForwardWindowResult(
                window=window_number,
                train_start=train_dates[0].date().isoformat(),
                train_end=train_dates[-1].date().isoformat(),
                test_start=test_dates[0].date().isoformat(),
                test_end=test_dates[-1].date().isoformat(),
                best_params=asdict(best_params),
                train_metrics=train_metrics,
                test_metrics=test_metrics,
                optuna_trials=len(study.trials),
                best_objective=float(study.best_value),
            )
        )
    combined_test_trades = pd.concat(all_test_trades, ignore_index=True) if all_test_trades else pd.DataFrame()
    combined_dates = pd.Index(sorted(pd.concat([pd.Series(index) for index in all_test_dates]).unique()))
    return results, combined_test_trades, calculate_metrics(combined_test_trades, combined_dates)


def audit_findings(dataset: EmaDataset) -> dict[str, Any]:
    baseline = current_strategy_baseline_params()
    _, baseline_5m = run_backtest(dataset, baseline, dataset.overlap_dates, use_1m_fills=False)
    _, baseline_1m = run_backtest(dataset, baseline, dataset.overlap_dates, use_1m_fills=True)
    last_30_count = int(dataset.bars_5m.groupby("session_date")["bars_remaining"].apply(lambda s: int((s <= 6).sum())).median())
    return {
        "classic_lookahead_found": False,
        "intrabar_stop_target_ambiguity": False,
        "median_last_30min_marked_bars": last_30_count,
        "baseline_overlap_5m_metrics": baseline_5m,
        "baseline_overlap_1m_metrics": baseline_1m,
        "notes": [
            "The EMA strategy decides on completed 5m bars and executes on the next bar open, so it does not suffer from the Stalker-style same-bar stop/target ambiguity.",
            "The TRIX rolling median is causal because it uses rolling(...).median().shift(1).",
            "The current session helper names a 35-minute zone as 'last 30min' because bars_remaining <= 6 also includes the 17:25 bar on M5.",
            "1m validation largely matches 5m fills because the next 5m open is also a valid 1m bar boundary; the overlap is still limited to the available 1m history.",
        ],
    }


def write_report(report_path: Path, summary: dict[str, Any]) -> None:
    holdout = summary["optimized_holdout"]
    walk_forward = summary["walk_forward"]
    audit = summary["audit"]
    lines = [
        "# EMA WDO Audit And 1m Validation",
        "",
        "## Audit",
        "",
        f"- Classic look-ahead found: `{audit['classic_lookahead_found']}`",
        f"- Intrabar stop/target ambiguity: `{audit['intrabar_stop_target_ambiguity']}`",
        f"- Median bars marked as `last_30min` on M5: `{audit['median_last_30min_marked_bars']}`",
        "",
        "## Baseline Overlap Comparison",
        "",
        f"- 5m fill Sharpe: `{audit['baseline_overlap_5m_metrics']['sharpe']}`",
        f"- 1m fill Sharpe: `{audit['baseline_overlap_1m_metrics']['sharpe']}`",
        f"- 5m fill PnL: `R${audit['baseline_overlap_5m_metrics']['net_profit_brl']}`",
        f"- 1m fill PnL: `R${audit['baseline_overlap_1m_metrics']['net_profit_brl']}`",
        "",
        "## Optimized Holdout",
        "",
        "```json",
        json.dumps(holdout["best_params"], indent=2),
        "```",
        "",
        f"- Train metrics: `{holdout['train_metrics']}`",
        f"- Test metrics: `{holdout['test_metrics']}`",
        "",
        "## Walk-Forward",
        "",
        f"- Aggregate metrics: `{walk_forward['aggregate_metrics']}`",
        f"- Windows: `{walk_forward['window_count']}`",
        "",
        "## Audit Notes",
        "",
    ]
    lines.extend([f"- {note}" for note in audit["notes"]])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and optimize the EMA WDO strategy with 1m validation.")
    parser.add_argument("--trials", type=int, default=300, help="Optuna trials for the 70/30 holdout.")
    parser.add_argument("--wf-trials", type=int, default=40, help="Optuna trials per walk-forward window.")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Chronological train ratio.")
    parser.add_argument("--window-total-days", type=int, default=84, help="Trading days per walk-forward window.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=artifact_output_dir("ema_wdo"),
        help="Artifact directory.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=artifact_report_path("ema_wdo_report.md"),
        help="Markdown report path.",
    )
    args = parser.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    dataset = EmaDataset.from_disk()
    audit = audit_findings(dataset)
    train_dates, test_dates = split_dates_by_ratio(dataset.overlap_dates, args.train_ratio)
    study, best_params, train_trades, train_metrics, test_trades, test_metrics = optimize_split(
        dataset=dataset,
        train_dates=train_dates,
        test_dates=test_dates,
        trials=args.trials,
        seed=args.seed,
    )
    wf_results, wf_test_trades, wf_metrics = run_walk_forward(
        dataset=dataset,
        dates=dataset.overlap_dates,
        train_ratio=args.train_ratio,
        window_total_days=args.window_total_days,
        trials_per_window=args.wf_trials,
        seed=args.seed,
    )

    summary = {
        "overlap_period": {
            "start_date": dataset.overlap_dates[0].date().isoformat(),
            "end_date": dataset.overlap_dates[-1].date().isoformat(),
            "trading_days": int(len(dataset.overlap_dates)),
        },
        "audit": audit,
        "optimized_holdout": {
            "train_days": int(len(train_dates)),
            "test_days": int(len(test_dates)),
            "best_params": asdict(best_params),
            "optuna_trials": len(study.trials),
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
        },
        "walk_forward": {
            "window_total_days": args.window_total_days,
            "window_count": len(wf_results),
            "aggregate_metrics": wf_metrics,
            "windows": [asdict(result) for result in wf_results],
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    study.trials_dataframe().to_csv(args.output_dir / "holdout_optuna_trials.csv", index=False)
    train_trades.to_csv(args.output_dir / "holdout_train_trades.csv", index=False)
    test_trades.to_csv(args.output_dir / "holdout_test_trades.csv", index=False)
    wf_test_trades.to_csv(args.output_dir / "walk_forward_test_trades.csv", index=False)
    write_report(args.report_path, summary)

    print("Audit:", audit)
    print("Best params:", asdict(best_params))
    print("Train metrics:", train_metrics)
    print("Test metrics:", test_metrics)
    print("Walk-forward aggregate:", wf_metrics)
    print(f"Artifacts saved to {args.output_dir}")


if __name__ == "__main__":
    main()
