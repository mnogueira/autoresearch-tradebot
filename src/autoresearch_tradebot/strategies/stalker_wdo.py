from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pandas as pd

from ..common.paths import artifact_output_dir, artifact_report_path
from ..common.wdo_data import locate_wdo_bar_file

POINT_VALUE_BRL = 10.0
TICK_SIZE = 0.5
ROUND_TRIP_COST_BRL = 11.0
INITIAL_CAPITAL_BRL = 100_000.0
SESSION_START = dt.time(9, 0)
SESSION_MAX = dt.time(18, 30)
LAST_ENTRY_CHOICES = ("14:45", "15:45", "16:45", "17:15")
SESSION_EXIT_CHOICES = ("17:15", "17:30", "17:45")
FLOAT_EPS = 1e-9


@dataclass(frozen=True)
class StrategyParams:
    range_reference_mode: str
    range_lookback_days: int
    prev_contract_days: int
    activation_basis: str
    activation_threshold_frac: float
    fib_basis: str
    retracement_frac: float
    min_range_points: float
    atr_timeframe: str
    atr_period: int
    stop_atr_mult: float
    target_atr_mult: float
    use_1h_filter: bool
    h1_fast_ema: int
    h1_slow_ema: int
    max_trades_per_day: int
    last_entry_time: str
    session_exit_time: str


@dataclass(frozen=True)
class Trade:
    session_date: str
    signal_time: str
    entry_time: str
    exit_time: str
    direction: str
    signal_direction: int
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    stop_points: float
    target_points: float
    retracement_price: float
    reference_range_points: float
    atr_points: float
    pnl_points: float
    pnl_brl: float
    fill_reason: str
    exit_reason: str


@dataclass(frozen=True)
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


def locate_data_file(timeframe: str) -> Path:
    return locate_wdo_bar_file(timeframe)


def load_parquet(timeframe: str) -> pd.DataFrame:
    path = locate_data_file(timeframe)
    df = pd.read_parquet(path).copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(f"Expected a DatetimeIndex for {timeframe} bars.")

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required_cols if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {timeframe} bars: {missing}")

    df = df.sort_index()
    df = df.loc[(df.index.time >= SESSION_START) & (df.index.time <= SESSION_MAX), required_cols].copy()
    df.attrs["source_path"] = str(path)
    return df


def parse_clock_time(value: str) -> dt.time:
    hour, minute = map(int, value.split(":"))
    return dt.time(hour, minute)


def round_to_tick(value: float) -> float:
    return round(value / TICK_SIZE) * TICK_SIZE


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def atr_wilder(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_retracement_price(
    direction: int,
    session_open: float,
    session_high: float,
    session_low: float,
    retracement_frac: float,
    fib_basis: str,
) -> float:
    if fib_basis == "directional_leg":
        if direction == 1:
            up_leg = max(session_high - session_open, 0.0)
            return session_high - up_leg * retracement_frac
        down_leg = max(session_open - session_low, 0.0)
        return session_low + down_leg * retracement_frac

    session_range = max(session_high - session_low, 0.0)
    if direction == 1:
        return session_high - session_range * retracement_frac
    return session_low + session_range * retracement_frac


def measure_activation_leg(
    direction: int,
    session_open: float,
    session_high: float,
    session_low: float,
    activation_basis: str,
) -> float:
    if activation_basis == "directional_leg":
        if direction == 1:
            return max(session_high - session_open, 0.0)
        return max(session_open - session_low, 0.0)
    return max(session_high - session_low, 0.0)


def fill_limit_order(
    direction: int,
    limit_price: float,
    bar_open: float,
    bar_high: float,
    bar_low: float,
) -> tuple[float | None, str | None]:
    if direction == 1:
        if bar_open <= limit_price + FLOAT_EPS:
            return round_to_tick(bar_open), "better_open"
        if bar_low <= limit_price + FLOAT_EPS <= bar_high + FLOAT_EPS:
            return round_to_tick(limit_price), "limit_touch"
    else:
        if bar_open >= limit_price - FLOAT_EPS:
            return round_to_tick(bar_open), "better_open"
        if bar_low - FLOAT_EPS <= limit_price <= bar_high + FLOAT_EPS:
            return round_to_tick(limit_price), "limit_touch"
    return None, None


def resolve_exit_on_bar(
    direction: int,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    stop_price: float,
    target_price: float,
    is_session_exit_bar: bool,
) -> tuple[float | None, str | None]:
    if direction == 1:
        stop_hit = bar_low <= stop_price + FLOAT_EPS
        target_hit = bar_high >= target_price - FLOAT_EPS
    else:
        stop_hit = bar_high >= stop_price - FLOAT_EPS
        target_hit = bar_low <= target_price + FLOAT_EPS

    if stop_hit and target_hit:
        return stop_price, "ambiguous_stop_first"
    if stop_hit:
        return stop_price, "stop_loss"
    if target_hit:
        return target_price, "take_profit"
    if is_session_exit_bar:
        return bar_close, "session_exit"
    return None, None


def split_dates_by_ratio(dates: pd.Index, train_ratio: float) -> tuple[pd.Index, pd.Index]:
    if len(dates) < 2:
        raise ValueError("Need at least two trading days for a train/test split.")
    split_at = int(len(dates) * train_ratio)
    split_at = min(max(split_at, 1), len(dates) - 1)
    return dates[:split_at], dates[split_at:]


def generate_walk_forward_windows(
    dates: pd.Index,
    window_total_days: int,
    train_ratio: float,
    step_days: int | None = None,
) -> list[tuple[int, pd.Index, pd.Index]]:
    train_days = max(1, int(window_total_days * train_ratio))
    test_days = window_total_days - train_days
    if test_days <= 0:
        raise ValueError("window_total_days and train_ratio produced an empty test window.")

    step = step_days or test_days
    windows: list[tuple[int, pd.Index, pd.Index]] = []
    window = 1
    start = 0
    while start + train_days + test_days <= len(dates):
        train_dates = dates[start : start + train_days]
        test_dates = dates[start + train_days : start + train_days + test_days]
        windows.append((window, train_dates, test_dates))
        window += 1
        start += step
    return windows


def calculate_metrics(
    trades_df: pd.DataFrame,
    trade_dates: pd.Index,
    initial_capital_brl: float = INITIAL_CAPITAL_BRL,
) -> dict[str, Any]:
    if len(trade_dates) == 0:
        raise ValueError("trade_dates cannot be empty.")

    trade_dates = pd.Index(pd.to_datetime(trade_dates)).sort_values()
    start_date = trade_dates[0].date().isoformat()
    end_date = trade_dates[-1].date().isoformat()

    if trades_df.empty:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": int(len(trade_dates)),
            "total_trades": 0,
            "win_rate": 0.0,
            "net_profit_brl": 0.0,
            "avg_profit_brl": 0.0,
            "avg_win_brl": 0.0,
            "avg_loss_brl": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "take_profit_trades": 0,
            "stop_loss_trades": 0,
            "session_exit_trades": 0,
        }

    pnl = trades_df["pnl_brl"].astype(float)
    wins = pnl[pnl > 0.0]
    losses = pnl[pnl < 0.0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.abs().sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0)

    daily_pnl = (
        trades_df.assign(session_date=pd.to_datetime(trades_df["session_date"]))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(trade_dates, fill_value=0.0)
    )
    daily_returns = daily_pnl / initial_capital_brl
    if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0:
        sharpe = float(np.sqrt(252) * daily_returns.mean() / daily_returns.std(ddof=1))
    else:
        sharpe = 0.0

    equity = initial_capital_brl + daily_pnl.cumsum()
    peaks = equity.cummax()
    drawdowns = (peaks - equity) / peaks.replace(0.0, np.nan) * 100.0

    return {
        "start_date": start_date,
        "end_date": end_date,
        "trading_days": int(len(trade_dates)),
        "total_trades": int(len(trades_df)),
        "win_rate": round(float((pnl > 0.0).mean()), 4),
        "net_profit_brl": round(float(pnl.sum()), 2),
        "avg_profit_brl": round(float(pnl.mean()), 2),
        "avg_win_brl": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss_brl": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(float(profit_factor), 4) if np.isfinite(profit_factor) else float("inf"),
        "sharpe": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(drawdowns.max()), 2) if len(drawdowns) else 0.0,
        "take_profit_trades": int((trades_df["exit_reason"] == "take_profit").sum()),
        "stop_loss_trades": int(trades_df["exit_reason"].isin(["stop_loss", "ambiguous_stop_first"]).sum()),
        "session_exit_trades": int((trades_df["exit_reason"] == "session_exit").sum()),
    }


def params_from_mapping(values: dict[str, Any]) -> StrategyParams:
    return StrategyParams(
        range_reference_mode=str(values["range_reference_mode"]),
        range_lookback_days=int(values["range_lookback_days"]),
        prev_contract_days=int(values["prev_contract_days"]),
        activation_basis=str(values["activation_basis"]),
        activation_threshold_frac=float(values["activation_threshold_frac"]),
        fib_basis=str(values["fib_basis"]),
        retracement_frac=float(values["retracement_frac"]),
        min_range_points=float(values["min_range_points"]),
        atr_timeframe=str(values["atr_timeframe"]),
        atr_period=int(values["atr_period"]),
        stop_atr_mult=float(values["stop_atr_mult"]),
        target_atr_mult=float(values["target_atr_mult"]),
        use_1h_filter=bool(values["use_1h_filter"]),
        h1_fast_ema=int(values["h1_fast_ema"]),
        h1_slow_ema=int(values["h1_slow_ema"]),
        max_trades_per_day=int(values["max_trades_per_day"]),
        last_entry_time=str(values["last_entry_time"]),
        session_exit_time=str(values["session_exit_time"]),
    )


def sample_params(trial: optuna.Trial) -> StrategyParams:
    return StrategyParams(
        range_reference_mode=trial.suggest_categorical("range_reference_mode", ["contract_expanding", "rolling_n"]),
        range_lookback_days=trial.suggest_int("range_lookback_days", 5, 40),
        prev_contract_days=trial.suggest_int("prev_contract_days", 3, 7),
        activation_basis=trial.suggest_categorical("activation_basis", ["session_range", "directional_leg"]),
        activation_threshold_frac=trial.suggest_float("activation_threshold_frac", 0.20, 0.60, step=0.05),
        fib_basis=trial.suggest_categorical("fib_basis", ["session_range", "directional_leg"]),
        retracement_frac=trial.suggest_float("retracement_frac", 0.15, 0.40, step=0.01),
        min_range_points=trial.suggest_float("min_range_points", 0.0, 30.0, step=2.5),
        atr_timeframe=trial.suggest_categorical("atr_timeframe", ["15m", "1h"]),
        atr_period=trial.suggest_int("atr_period", 10, 40),
        stop_atr_mult=trial.suggest_float("stop_atr_mult", 0.50, 1.50, step=0.05),
        target_atr_mult=trial.suggest_float("target_atr_mult", 0.25, 4.00, step=0.05),
        use_1h_filter=trial.suggest_categorical("use_1h_filter", [False, True]),
        h1_fast_ema=trial.suggest_int("h1_fast_ema", 5, 20),
        h1_slow_ema=trial.suggest_int("h1_slow_ema", 10, 40),
        max_trades_per_day=trial.suggest_int("max_trades_per_day", 1, 3),
        last_entry_time=trial.suggest_categorical("last_entry_time", list(LAST_ENTRY_CHOICES)),
        session_exit_time=trial.suggest_categorical("session_exit_time", list(SESSION_EXIT_CHOICES)),
    )


class StalkerDataset:
    def __init__(self, bars_15m: pd.DataFrame, bars_1h: pd.DataFrame, bars_1m: pd.DataFrame | None = None):
        self.bars_15m = bars_15m.copy()
        self.bars_15m["session_date"] = self.bars_15m.index.normalize()
        self.bars_15m["clock_time"] = self.bars_15m.index.time
        self.bars_15m["bar_index_in_day"] = self.bars_15m.groupby("session_date").cumcount()

        self.bars_1h = bars_1h.copy()
        self.bars_1h["session_date"] = self.bars_1h.index.normalize()

        self.bars_1m = bars_1m.copy() if bars_1m is not None else None
        self.trade_dates = pd.Index(sorted(self.bars_15m["session_date"].unique()))

        self.daily = self._build_daily_frame()
        self._rolling_range_cache: dict[int, pd.Series] = {}
        self._contract_range_cache: dict[int, pd.Series] = {}
        self._atr_cache: dict[tuple[str, int], pd.Series] = {}
        self._trend_cache: dict[tuple[int, int], pd.Series] = {}

    @classmethod
    def from_disk(cls) -> "StalkerDataset":
        bars_15m = load_parquet("15m")
        bars_1h = load_parquet("1h")
        bars_1m = load_parquet("1m")
        return cls(bars_15m=bars_15m, bars_1h=bars_1h, bars_1m=bars_1m)

    def _build_daily_frame(self) -> pd.DataFrame:
        daily = self.bars_15m.groupby("session_date").agg(
            session_open=("Open", "first"),
            session_high=("High", "max"),
            session_low=("Low", "min"),
            session_close=("Close", "last"),
            volume=("Volume", "sum"),
        )
        daily["range_points"] = daily["session_high"] - daily["session_low"]
        daily["contract_id"] = daily.index.to_period("M").astype(str)
        daily["contract_day"] = daily.groupby("contract_id").cumcount() + 1
        daily["current_contract_avg_prev"] = daily.groupby("contract_id")["range_points"].transform(
            lambda series: series.expanding().mean().shift(1)
        )

        contract_means = daily.groupby("contract_id")["range_points"].mean().sort_index()
        previous_contract_means = contract_means.shift(1)
        daily["previous_contract_avg"] = daily["contract_id"].map(previous_contract_means)
        daily["global_avg_prev"] = daily["range_points"].expanding().mean().shift(1)
        return daily

    def get_range_reference(self, mode: str, lookback_days: int, prev_contract_days: int) -> pd.Series:
        if mode == "rolling_n":
            if lookback_days not in self._rolling_range_cache:
                series = self.daily["range_points"].rolling(window=lookback_days, min_periods=3).mean().shift(1)
                series = series.fillna(self.daily["global_avg_prev"])
                self._rolling_range_cache[lookback_days] = series
            return self._rolling_range_cache[lookback_days]

        if prev_contract_days not in self._contract_range_cache:
            series = pd.Series(
                np.where(
                    self.daily["contract_day"] <= prev_contract_days,
                    self.daily["previous_contract_avg"],
                    self.daily["current_contract_avg_prev"],
                ),
                index=self.daily.index,
                dtype=float,
            )
            series = series.fillna(self.daily["global_avg_prev"])
            self._contract_range_cache[prev_contract_days] = series
        return self._contract_range_cache[prev_contract_days]

    def get_atr_series(self, timeframe: str, period: int) -> pd.Series:
        key = (timeframe, period)
        if key in self._atr_cache:
            return self._atr_cache[key]

        if timeframe == "15m":
            series = atr_wilder(self.bars_15m, period)
        elif timeframe == "1h":
            atr_h1 = atr_wilder(self.bars_1h, period)
            series = atr_h1.shift(1).reindex(self.bars_15m.index, method="ffill")
        else:
            raise ValueError(f"Unsupported ATR timeframe: {timeframe}")

        self._atr_cache[key] = series
        return series

    def get_h1_trend(self, fast_ema: int, slow_ema: int) -> pd.Series:
        key = (fast_ema, slow_ema)
        if key in self._trend_cache:
            return self._trend_cache[key]

        fast = ema(self.bars_1h["Close"], fast_ema)
        slow = ema(self.bars_1h["Close"], slow_ema)
        state = pd.Series(
            np.where(fast > slow, 1, np.where(fast < slow, -1, 0)),
            index=self.bars_1h.index,
            dtype=float,
        ).shift(1)
        mapped = state.reindex(self.bars_15m.index, method="ffill").fillna(0).astype(int)
        self._trend_cache[key] = mapped
        return mapped

    def minute_coverage(self) -> dict[str, Any] | None:
        if self.bars_1m is None or self.bars_1m.empty:
            return None
        trade_dates = pd.Index(sorted(self.bars_1m.index.normalize().unique()))
        return {
            "path": str(self.bars_1m.attrs.get("source_path", locate_data_file("1m"))),
            "start_date": trade_dates[0].date().isoformat(),
            "end_date": trade_dates[-1].date().isoformat(),
            "trading_days": int(len(trade_dates)),
        }


def run_backtest(
    dataset: StalkerDataset,
    params: StrategyParams,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if params.use_1h_filter and params.h1_fast_ema >= params.h1_slow_ema:
        raise ValueError("When the 1h filter is enabled, h1_fast_ema must be < h1_slow_ema.")
    if parse_clock_time(params.session_exit_time) <= parse_clock_time(params.last_entry_time):
        raise ValueError("session_exit_time must be later than last_entry_time.")

    date_set = set(pd.Index(pd.to_datetime(trade_dates)))
    frame = dataset.bars_15m[dataset.bars_15m["session_date"].isin(date_set)].copy()
    if frame.empty:
        return pd.DataFrame(), calculate_metrics(pd.DataFrame(), trade_dates)

    atr_series = dataset.get_atr_series(params.atr_timeframe, params.atr_period).reindex(frame.index)
    if params.use_1h_filter:
        trend_series = dataset.get_h1_trend(params.h1_fast_ema, params.h1_slow_ema).reindex(frame.index)
    else:
        trend_series = pd.Series(0, index=frame.index, dtype=int)

    range_reference = dataset.get_range_reference(
        mode=params.range_reference_mode,
        lookback_days=params.range_lookback_days,
        prev_contract_days=params.prev_contract_days,
    )
    range_reference_map = range_reference.to_dict()

    opens = frame["Open"].to_numpy(dtype=float)
    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    closes = frame["Close"].to_numpy(dtype=float)
    atr_values = atr_series.to_numpy(dtype=float)
    trend_values = trend_series.to_numpy(dtype=int)
    times = frame["clock_time"].to_numpy()
    dates = frame["session_date"].to_numpy()
    index = frame.index

    last_entry_time = parse_clock_time(params.last_entry_time)
    session_exit_time = parse_clock_time(params.session_exit_time)
    min_tick_move = TICK_SIZE / 2

    trades: list[Trade] = []
    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    stop_points = 0.0
    target_points = 0.0
    active_signal_time = pd.NaT
    active_entry_time = pd.NaT
    active_retracement_price = 0.0
    active_reference_range = 0.0
    active_atr_points = 0.0
    active_fill_reason = ""

    pending_order: dict[str, Any] | None = None
    blocked_long_above: float | None = None
    blocked_short_below: float | None = None

    current_date = None
    session_open = 0.0
    session_high = 0.0
    session_low = 0.0
    trades_today = 0
    previous_close = 0.0
    previous_timestamp = pd.NaT

    for i in range(len(frame)):
        bar_time = times[i]
        bar_date = dates[i]
        bar_open = opens[i]
        bar_high = highs[i]
        bar_low = lows[i]
        bar_close = closes[i]
        bar_timestamp = index[i]

        if current_date is None or bar_date != current_date:
            if position != 0:
                exit_price = round_to_tick(previous_close)
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                trades.append(
                    Trade(
                        session_date=pd.Timestamp(current_date).date().isoformat(),
                        signal_time=str(active_signal_time),
                        entry_time=str(active_entry_time),
                        exit_time=str(previous_timestamp),
                        direction="long" if position == 1 else "short",
                        signal_direction=position,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        stop_points=stop_points,
                        target_points=target_points,
                        retracement_price=active_retracement_price,
                        reference_range_points=active_reference_range,
                        atr_points=active_atr_points,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=active_fill_reason or "forced_day_change",
                        exit_reason="forced_day_change",
                    )
                )
                position = 0
                pending_order = None

            current_date = bar_date
            session_open = bar_open
            session_high = bar_high
            session_low = bar_low
            blocked_long_above = None
            blocked_short_below = None
            trades_today = 0
            pending_order = None
            previous_close = bar_close
            previous_timestamp = bar_timestamp
            continue

        updated_session_high = max(session_high, bar_high)
        updated_session_low = min(session_low, bar_low)
        is_new_high = bar_high > session_high + FLOAT_EPS
        is_new_low = bar_low < session_low - FLOAT_EPS

        if position != 0:
            exit_price, exit_reason = resolve_exit_on_bar(
                direction=position,
                bar_high=bar_high,
                bar_low=bar_low,
                bar_close=bar_close,
                stop_price=stop_price,
                target_price=target_price,
                is_session_exit_bar=bar_time >= session_exit_time,
            )
            if exit_price is not None and exit_reason is not None:
                exit_price = round_to_tick(exit_price)
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                trades.append(
                    Trade(
                        session_date=pd.Timestamp(bar_date).date().isoformat(),
                        signal_time=str(active_signal_time),
                        entry_time=str(active_entry_time),
                        exit_time=str(bar_timestamp),
                        direction="long" if position == 1 else "short",
                        signal_direction=position,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        stop_points=stop_points,
                        target_points=target_points,
                        retracement_price=active_retracement_price,
                        reference_range_points=active_reference_range,
                        atr_points=active_atr_points,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=active_fill_reason or "active_position",
                        exit_reason=exit_reason,
                    )
                )
                if exit_reason in {"stop_loss", "ambiguous_stop_first"}:
                    if position == 1:
                        blocked_long_above = updated_session_high
                    else:
                        blocked_short_below = updated_session_low
                position = 0
                pending_order = None

        if position == 0 and pending_order is not None and bar_time <= last_entry_time:
            fill_price, fill_reason = fill_limit_order(
                direction=int(pending_order["direction"]),
                limit_price=float(pending_order["limit_price"]),
                bar_open=bar_open,
                bar_high=bar_high,
                bar_low=bar_low,
            )
            if fill_price is not None and fill_reason is not None:
                atr_points = float(pending_order["atr_points"])
                stop_points = round_to_tick(max(TICK_SIZE, atr_points * params.stop_atr_mult))
                target_points = round_to_tick(max(TICK_SIZE, atr_points * params.target_atr_mult))
                position = int(pending_order["direction"])
                entry_price = fill_price
                active_entry_time = bar_timestamp
                active_fill_reason = fill_reason
                if position == 1:
                    stop_price = round_to_tick(entry_price - stop_points)
                    target_price = round_to_tick(entry_price + target_points)
                else:
                    stop_price = round_to_tick(entry_price + stop_points)
                    target_price = round_to_tick(entry_price - target_points)

                active_signal_time = pending_order["signal_time"]
                active_retracement_price = float(pending_order["limit_price"])
                active_reference_range = float(pending_order["reference_range"])
                active_atr_points = atr_points
                trades_today += 1
                pending_order = None

                exit_price, exit_reason = resolve_exit_on_bar(
                    direction=position,
                    bar_high=bar_high,
                    bar_low=bar_low,
                    bar_close=bar_close,
                    stop_price=stop_price,
                    target_price=target_price,
                    is_session_exit_bar=bar_time >= session_exit_time,
                )
                if exit_price is not None and exit_reason is not None:
                    exit_price = round_to_tick(exit_price)
                    pnl_points = (exit_price - entry_price) * position
                    pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                    trades.append(
                        Trade(
                            session_date=pd.Timestamp(bar_date).date().isoformat(),
                            signal_time=str(active_signal_time),
                            entry_time=str(active_entry_time),
                            exit_time=str(bar_timestamp),
                            direction="long" if position == 1 else "short",
                            signal_direction=position,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            stop_points=stop_points,
                            target_points=target_points,
                            retracement_price=active_retracement_price,
                            reference_range_points=active_reference_range,
                            atr_points=active_atr_points,
                            pnl_points=round(pnl_points, 2),
                            pnl_brl=round(pnl_brl, 2),
                            fill_reason=fill_reason,
                            exit_reason=exit_reason,
                        )
                    )
                    if exit_reason in {"stop_loss", "ambiguous_stop_first"}:
                        if position == 1:
                            blocked_long_above = updated_session_high
                        else:
                            blocked_short_below = updated_session_low
                    position = 0

        session_high = updated_session_high
        session_low = updated_session_low

        if blocked_long_above is not None and session_high > blocked_long_above + min_tick_move:
            blocked_long_above = None
        if blocked_short_below is not None and session_low < blocked_short_below - min_tick_move:
            blocked_short_below = None

        if position == 0 and pending_order is not None and bar_time > last_entry_time:
            pending_order = None

        if position == 0 and trades_today < params.max_trades_per_day and bar_time < last_entry_time:
            if is_new_high and is_new_low:
                pending_order = None
            else:
                reference_range = range_reference_map.get(pd.Timestamp(bar_date), np.nan)
                if pd.notna(reference_range) and float(reference_range) > 0.0:
                    candidate_direction = 1 if is_new_high else (-1 if is_new_low else 0)
                    if candidate_direction != 0:
                        activation_value = measure_activation_leg(
                            direction=candidate_direction,
                            session_open=session_open,
                            session_high=session_high,
                            session_low=session_low,
                            activation_basis=params.activation_basis,
                        )
                        day_range = session_high - session_low
                        threshold = float(reference_range) * params.activation_threshold_frac
                        blocked = (
                            candidate_direction == 1 and blocked_long_above is not None
                        ) or (
                            candidate_direction == -1 and blocked_short_below is not None
                        )
                        trend_allowed = not params.use_1h_filter or trend_values[i] == candidate_direction
                        atr_points = atr_values[i]
                        if (
                            not blocked
                            and trend_allowed
                            and activation_value >= threshold
                            and day_range >= params.min_range_points
                            and pd.notna(atr_points)
                            and atr_points > 0.0
                        ):
                            limit_price = compute_retracement_price(
                                direction=candidate_direction,
                                session_open=session_open,
                                session_high=session_high,
                                session_low=session_low,
                                retracement_frac=params.retracement_frac,
                                fib_basis=params.fib_basis,
                            )
                            pending_order = {
                                "direction": candidate_direction,
                                "limit_price": round_to_tick(limit_price),
                                "atr_points": float(atr_points),
                                "signal_time": bar_timestamp,
                                "reference_range": float(reference_range),
                            }
                        else:
                            pending_order = None

        previous_close = bar_close
        previous_timestamp = bar_timestamp

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df=trades_df, trade_dates=trade_dates)
    return trades_df, metrics


def objective_factory(dataset: StalkerDataset, train_dates: pd.Index):
    min_trades = max(8, int(len(train_dates) * 0.02))

    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial)
        if params.use_1h_filter and params.h1_fast_ema >= params.h1_slow_ema:
            return -1e9
        if parse_clock_time(params.session_exit_time) <= parse_clock_time(params.last_entry_time):
            return -1e9

        trades_df, metrics = run_backtest(dataset=dataset, params=params, trade_dates=train_dates)
        trial.set_user_attr("train_metrics", metrics)
        trial.set_user_attr("train_trade_count", int(metrics["total_trades"]))
        if not trades_df.empty:
            trial.set_user_attr("train_net_profit_brl", float(metrics["net_profit_brl"]))

        total_trades = int(metrics["total_trades"])
        if total_trades < min_trades:
            return -1000.0 + total_trades

        score = float(metrics["sharpe"])
        score += min(float(metrics["profit_factor"]), 5.0) * 0.05
        score -= float(metrics["max_drawdown_pct"]) * 0.02
        if float(metrics["net_profit_brl"]) <= 0.0:
            score -= 2.0
        return score

    return objective


def study_trials_to_dataframe(study: optuna.Study) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for trial in study.trials:
        row: dict[str, Any] = {
            "number": trial.number,
            "state": str(trial.state),
            "value": trial.value,
        }
        row.update(trial.params)
        train_metrics = trial.user_attrs.get("train_metrics", {})
        for key, value in train_metrics.items():
            row[f"train_{key}"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def optimize_split(
    dataset: StalkerDataset,
    train_dates: pd.Index,
    test_dates: pd.Index,
    trials: int,
    seed: int,
) -> tuple[optuna.Study, StrategyParams, pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective_factory(dataset, train_dates), n_trials=trials, show_progress_bar=False)

    best_params = params_from_mapping(study.best_params)
    train_trades, train_metrics = run_backtest(dataset=dataset, params=best_params, trade_dates=train_dates)
    test_trades, test_metrics = run_backtest(dataset=dataset, params=best_params, trade_dates=test_dates)
    return study, best_params, train_trades, train_metrics, test_trades, test_metrics


def run_walk_forward(
    dataset: StalkerDataset,
    train_ratio: float,
    window_total_days: int,
    trials_per_window: int,
    seed: int,
) -> tuple[list[WalkForwardWindowResult], pd.DataFrame, dict[str, Any]]:
    windows = generate_walk_forward_windows(
        dates=dataset.trade_dates,
        window_total_days=window_total_days,
        train_ratio=train_ratio,
    )
    if not windows:
        raise ValueError("No walk-forward windows were generated.")

    results: list[WalkForwardWindowResult] = []
    all_test_trades: list[pd.DataFrame] = []
    all_test_dates: list[pd.Index] = []

    for window_number, train_dates, test_dates in windows:
        study, best_params, _, train_metrics, test_trades, test_metrics = optimize_split(
            dataset=dataset,
            train_dates=train_dates,
            test_dates=test_dates,
            trials=trials_per_window,
            seed=seed + window_number,
        )

        if not test_trades.empty:
            test_trades = test_trades.copy()
            test_trades["walk_forward_window"] = window_number
            all_test_trades.append(test_trades)
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
    combined_test_dates = pd.Index(sorted(pd.concat([pd.Series(index) for index in all_test_dates]).unique()))
    aggregate_metrics = calculate_metrics(combined_test_trades, combined_test_dates)
    return results, combined_test_trades, aggregate_metrics


def build_report(summary: dict[str, Any]) -> str:
    holdout_train = summary["holdout"]["train_metrics"]
    holdout_test = summary["holdout"]["test_metrics"]
    wf_aggregate = summary["walk_forward"]["aggregate_metrics"]

    lines = [
        "# WDO Stalker Strategy Report",
        "",
        "## Setup",
        f"- 15m source: `{summary['data_sources']['15m']}`",
        f"- 1h source: `{summary['data_sources']['1h']}`",
        f"- 1m source: `{summary['data_sources']['1m']}`",
        f"- 15m sample: `{summary['dataset']['start_date']}` -> `{summary['dataset']['end_date']}` ({summary['dataset']['trading_days']} trading days)",
        f"- Holdout split: `{summary['holdout']['train_days']}` train days / `{summary['holdout']['test_days']}` test days",
        f"- Walk-forward windows: `{summary['walk_forward']['window_count']}` windows, `{summary['walk_forward']['window_total_days']}` total days each, `70/30` train/test inside each window",
        "- Signal bars are 15m, optional confirmation filter is previous completed 1h EMA trend, and execution is modeled with causal resting limit orders.",
        "- Entry orders are activated from the next 15m bar only; same-bar stop/target conflicts are resolved pessimistically with stop first.",
        "",
        "## Optimized Holdout Parameters",
    ]
    for key, value in summary["holdout"]["best_params"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Holdout Metrics",
            "",
            "| Metric | Train | Test |",
            "|---|---:|---:|",
            f"| Sharpe | {holdout_train['sharpe']} | {holdout_test['sharpe']} |",
            f"| Win rate | {holdout_train['win_rate'] * 100:.2f}% | {holdout_test['win_rate'] * 100:.2f}% |",
            f"| Net profit (BRL) | {holdout_train['net_profit_brl']:.2f} | {holdout_test['net_profit_brl']:.2f} |",
            f"| Max drawdown | {holdout_train['max_drawdown_pct']:.2f}% | {holdout_test['max_drawdown_pct']:.2f}% |",
            f"| Profit factor | {holdout_train['profit_factor']} | {holdout_test['profit_factor']} |",
            f"| Trades | {holdout_train['total_trades']} | {holdout_test['total_trades']} |",
            "",
            "## Walk-Forward Aggregate Metrics",
            "",
            f"- Sharpe: `{wf_aggregate['sharpe']}`",
            f"- Win rate: `{wf_aggregate['win_rate'] * 100:.2f}%`",
            f"- Net profit (BRL): `{wf_aggregate['net_profit_brl']:.2f}`",
            f"- Max drawdown: `{wf_aggregate['max_drawdown_pct']:.2f}%`",
            f"- Profit factor: `{wf_aggregate['profit_factor']}`",
            f"- Trades: `{wf_aggregate['total_trades']}`",
            "",
            "## Walk-Forward Windows",
            "",
            "| Window | Train | Test | Test Sharpe | Test PF | Test Trades | Test Net |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )

    for window in summary["walk_forward"]["windows"]:
        lines.append(
            "| {window} | {train_start} -> {train_end} | {test_start} -> {test_end} | {sharpe} | {pf} | {trades} | {net} |".format(
                window=window["window"],
                train_start=window["train_start"],
                train_end=window["train_end"],
                test_start=window["test_start"],
                test_end=window["test_end"],
                sharpe=window["test_metrics"]["sharpe"],
                pf=window["test_metrics"]["profit_factor"],
                trades=window["test_metrics"]["total_trades"],
                net=window["test_metrics"]["net_profit_brl"],
            )
        )

    return "\n".join(lines) + "\n"


def save_outputs(
    output_dir: Path,
    report_path: Path,
    summary: dict[str, Any],
    holdout_study: optuna.Study,
    holdout_train_trades: pd.DataFrame,
    holdout_test_trades: pd.DataFrame,
    walk_forward_test_trades: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "holdout_optuna_trials.csv").write_text(
        study_trials_to_dataframe(holdout_study).to_csv(index=False),
        encoding="utf-8",
    )
    holdout_train_trades.to_csv(output_dir / "holdout_train_trades.csv", index=False)
    holdout_test_trades.to_csv(output_dir / "holdout_test_trades.csv", index=False)
    walk_forward_test_trades.to_csv(output_dir / "walk_forward_test_trades.csv", index=False)
    pd.DataFrame(summary["walk_forward"]["windows"]).to_json(
        output_dir / "walk_forward_windows.json",
        orient="records",
        indent=2,
    )
    report_path.write_text(build_report(summary), encoding="utf-8")


def print_metrics_block(title: str, metrics: dict[str, Any]) -> None:
    print(title)
    print(f"  period: {metrics['start_date']} -> {metrics['end_date']}")
    print(f"  sharpe: {metrics['sharpe']}")
    print(f"  win_rate: {metrics['win_rate'] * 100:.2f}%")
    print(f"  net_profit_brl: {metrics['net_profit_brl']:.2f}")
    print(f"  max_drawdown_pct: {metrics['max_drawdown_pct']:.2f}%")
    print(f"  profit_factor: {metrics['profit_factor']}")
    print(f"  total_trades: {metrics['total_trades']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize and walk-forward test the WDO Stalker strategy.")
    parser.add_argument("--trials", type=int, default=400, help="Optuna trials for the full 70/30 holdout optimization.")
    parser.add_argument(
        "--wf-trials",
        type=int,
        default=60,
        help="Optuna trials per walk-forward training window.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Chronological train ratio.")
    parser.add_argument(
        "--window-total-days",
        type=int,
        default=252,
        help="Total trading days per walk-forward window. Each window uses 70/30 train/test internally.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for Optuna.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=artifact_output_dir("stalker_wdo"),
        help="Directory for JSON/CSV artifacts.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=artifact_report_path("stalker_wdo_report.md"),
        help="Where to write the Markdown report.",
    )
    args = parser.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    dataset = StalkerDataset.from_disk()
    train_dates, test_dates = split_dates_by_ratio(dataset.trade_dates, args.train_ratio)

    print("WDO Stalker Optimization")
    print(f"15m data: {locate_data_file('15m')}")
    print(f"1h data:  {locate_data_file('1h')}")
    minute_coverage = dataset.minute_coverage()
    if minute_coverage is not None:
        print(
            "1m coverage note: "
            f"{minute_coverage['start_date']} -> {minute_coverage['end_date']} "
            f"({minute_coverage['trading_days']} trading days, used for coverage audit only)"
        )
    print(f"Holdout split: {len(train_dates)} train days | {len(test_dates)} test days")
    print()

    holdout_study, best_params, holdout_train_trades, holdout_train_metrics, holdout_test_trades, holdout_test_metrics = optimize_split(
        dataset=dataset,
        train_dates=train_dates,
        test_dates=test_dates,
        trials=args.trials,
        seed=args.seed,
    )

    walk_forward_windows, walk_forward_test_trades, walk_forward_aggregate_metrics = run_walk_forward(
        dataset=dataset,
        train_ratio=args.train_ratio,
        window_total_days=args.window_total_days,
        trials_per_window=args.wf_trials,
        seed=args.seed,
    )

    summary = {
        "data_sources": {
            "15m": str(locate_data_file("15m")),
            "1h": str(locate_data_file("1h")),
            "1m": str(locate_data_file("1m")),
        },
        "dataset": {
            "start_date": dataset.trade_dates[0].date().isoformat(),
            "end_date": dataset.trade_dates[-1].date().isoformat(),
            "trading_days": int(len(dataset.trade_dates)),
            "minute_coverage": minute_coverage,
        },
        "holdout": {
            "train_ratio": args.train_ratio,
            "train_days": int(len(train_dates)),
            "test_days": int(len(test_dates)),
            "best_params": asdict(best_params),
            "best_objective": float(holdout_study.best_value),
            "optuna_trials": len(holdout_study.trials),
            "train_metrics": holdout_train_metrics,
            "test_metrics": holdout_test_metrics,
        },
        "walk_forward": {
            "window_total_days": args.window_total_days,
            "window_count": len(walk_forward_windows),
            "trials_per_window": args.wf_trials,
            "aggregate_metrics": walk_forward_aggregate_metrics,
            "windows": [asdict(window) for window in walk_forward_windows],
        },
    }

    save_outputs(
        output_dir=args.output_dir,
        report_path=args.report_path,
        summary=summary,
        holdout_study=holdout_study,
        holdout_train_trades=holdout_train_trades,
        holdout_test_trades=holdout_test_trades,
        walk_forward_test_trades=walk_forward_test_trades,
    )

    print("Optimized holdout parameters")
    for key, value in asdict(best_params).items():
        print(f"  {key}: {value}")
    print()

    print_metrics_block("Holdout train metrics", holdout_train_metrics)
    print()
    print_metrics_block("Holdout test metrics", holdout_test_metrics)
    print()
    print_metrics_block("Walk-forward aggregate metrics", walk_forward_aggregate_metrics)
    print()
    print(f"Artifacts saved to: {args.output_dir}")
    print(f"Report saved to: {args.report_path}")


if __name__ == "__main__":
    main()
