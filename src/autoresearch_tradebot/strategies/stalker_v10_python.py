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

from ..common.paths import DEFAULT_EXTERNAL_WDO_BAR_DIR, DATA_DIR, artifact_output_dir
from ..common.wdo_data import exported_m1_history_csv

TICK_SIZE = 0.5
POINT_VALUE_BRL = 10.0
ROUND_TRIP_COST_BRL = 0.0
BIG_NUMBER = 9_999_999.0
CONTINUOUS_SERIES_SYMBOL = "WDO$N"
DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_python")
DATA_CANDIDATES = [
    DATA_DIR / "wdo_m1_mt5_2021_2026.parquet",
    exported_m1_history_csv(),
    DEFAULT_EXTERNAL_WDO_BAR_DIR / "1m.parquet",
    DATA_DIR / "wdo_m1.parquet",
]


@dataclass(frozen=True)
class V10Params:
    ContractsPerTrade: float = 1.0
    FilterAsPercOfContractMARange: float = 0.30
    NumDaysToConsiderPreviousContractMARange: int = 5
    RetracementLevel: float = 0.25
    SL_ATRMultiplier: float = 0.78
    TP_ATRMultiplier: float = 0.36
    ATR_Length: int = 20
    MarketClose_Hour: int = 18
    MarketClose_Minute: int = 0
    MinutesBeforeMarketCloseToClosePositions: int = 5


@dataclass(frozen=True)
class TradeRecord:
    session_date: str
    signal_time: str
    entry_time: str
    exit_time: str
    direction: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    pnl_points: float
    pnl_brl: float
    fill_reason: str
    exit_reason: str


def round_to_tick(value: float) -> float:
    return round(value / TICK_SIZE) * TICK_SIZE


def locate_data_file(path_override: Path | None = None) -> Path:
    if path_override is not None:
        if path_override.exists():
            return path_override
        raise FileNotFoundError(f"Specified WDO M1 data file does not exist: {path_override}")

    for candidate in DATA_CANDIDATES:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in DATA_CANDIDATES)
    raise FileNotFoundError(f"Could not find WDO M1 data. Searched: {searched}")


def standardize_m1_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "tick_volume": "Volume",
        "spread": "Spread",
        "real_volume": "RealVolume",
    }
    renamed = frame.rename(columns={column: rename_map.get(column, column) for column in frame.columns})
    if "Volume" not in renamed.columns:
        if "RealVolume" in renamed.columns:
            renamed["Volume"] = renamed["RealVolume"]
        else:
            raise ValueError("Could not derive Volume column from M1 data.")
    return renamed


def load_m1_data(path_override: Path | None = None) -> pd.DataFrame:
    path = locate_data_file(path_override)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path).copy()
    else:
        frame = pd.read_parquet(path).copy()

    if "time" in frame.columns:
        frame["time"] = pd.to_datetime(frame["time"])
        frame = frame.set_index("time")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("Expected a DatetimeIndex or a 'time' column in the M1 data file.")

    frame = standardize_m1_columns(frame)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns in M1 data: {missing}")

    frame = frame.sort_index()
    frame.attrs["source_path"] = str(path)
    return frame[required].copy()


def date_only(value: pd.Timestamp) -> pd.Timestamp:
    return value.normalize()


def wilder_atr_from_tr(tr: pd.Series, period: int) -> pd.Series:
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


class V10Dataset:
    def __init__(self, bars_m1: pd.DataFrame):
        self.bars_m1 = bars_m1.copy()
        self.bars_m1["session_date"] = self.bars_m1.index.normalize()
        self.bars_m1["clock_time"] = self.bars_m1.index.time
        self.bars_m1["m15_bucket"] = self.bars_m1.index.floor("15min")
        self.trade_dates = pd.Index(sorted(self.bars_m1["session_date"].unique()))

        self._build_daily_frame()
        self._build_open_state()
        self._build_m15_reference()
        self._signal_range_cache: dict[tuple[float, int], np.ndarray] = {}
        self._atr_cache: dict[int, np.ndarray] = {}

    @classmethod
    def from_disk(cls, path_override: Path | None = None) -> "V10Dataset":
        return cls(load_m1_data(path_override))

    def _build_daily_frame(self) -> None:
        daily = self.bars_m1.groupby("session_date").agg(
            day_high=("High", "max"),
            day_low=("Low", "min"),
        )
        daily["range_points"] = daily["day_high"] - daily["day_low"]
        daily["contract_id"] = daily.index.to_period("M").astype(str)
        daily["contract_day_number"] = daily.groupby("contract_id").cumcount() + 1

        contract_means = daily.groupby("contract_id")["range_points"].mean().sort_index()
        previous_contract_means = contract_means.shift(1)
        daily["previous_contract_average"] = daily["contract_id"].map(previous_contract_means)
        daily["current_contract_average_prev"] = daily.groupby("contract_id")["range_points"].transform(
            lambda series: series.expanding().mean().shift(1)
        )
        self.daily = daily

    def _build_open_state(self) -> None:
        day_high_open: list[float] = []
        day_low_open: list[float] = []
        partial_tr_open: list[float] = []

        current_day: pd.Timestamp | None = None
        session_high_close = 0.0
        session_low_close = 0.0
        current_bucket: pd.Timestamp | None = None
        bucket_high_close = 0.0
        bucket_low_close = 0.0
        current_bucket_open = 0.0
        prev_bucket_close = np.nan

        complete_buckets: list[dict[str, Any]] = []
        last_bucket_open = 0.0
        last_bucket_high = 0.0
        last_bucket_low = 0.0
        last_bucket_close = 0.0
        last_bucket_start: pd.Timestamp | None = None

        for timestamp, row in self.bars_m1.iterrows():
            bar_open = float(row["Open"])
            bar_high = float(row["High"])
            bar_low = float(row["Low"])
            bar_close = float(row["Close"])
            session_date = date_only(timestamp)
            bucket_start = timestamp.floor("15min")

            if current_day is None or session_date != current_day:
                current_day = session_date
                session_high_close = bar_open
                session_low_close = bar_open
            day_high = max(session_high_close, bar_open)
            day_low = min(session_low_close, bar_open)
            day_high_open.append(day_high)
            day_low_open.append(day_low)

            if current_bucket is None or bucket_start != current_bucket:
                if last_bucket_start is not None:
                    complete_buckets.append(
                        {
                            "bucket_start": last_bucket_start,
                            "Open": last_bucket_open,
                            "High": last_bucket_high,
                            "Low": last_bucket_low,
                            "Close": last_bucket_close,
                        }
                    )
                    prev_bucket_close = last_bucket_close

                current_bucket = bucket_start
                current_bucket_open = bar_open
                bucket_high_close = bar_open
                bucket_low_close = bar_open
                partial_high = bar_open
                partial_low = bar_open
            else:
                partial_high = max(bucket_high_close, bar_open)
                partial_low = min(bucket_low_close, bar_open)

            if pd.isna(prev_bucket_close):
                current_tr = partial_high - partial_low
            else:
                current_tr = max(
                    partial_high - partial_low,
                    abs(partial_high - prev_bucket_close),
                    abs(partial_low - prev_bucket_close),
                )
            partial_tr_open.append(float(current_tr))

            session_high_close = max(day_high, bar_high)
            session_low_close = min(day_low, bar_low)
            bucket_high_close = max(partial_high, bar_high)
            bucket_low_close = min(partial_low, bar_low)

            last_bucket_start = bucket_start
            last_bucket_open = current_bucket_open
            last_bucket_high = bucket_high_close
            last_bucket_low = bucket_low_close
            last_bucket_close = bar_close

        if last_bucket_start is not None:
            complete_buckets.append(
                {
                    "bucket_start": last_bucket_start,
                    "Open": last_bucket_open,
                    "High": last_bucket_high,
                    "Low": last_bucket_low,
                    "Close": last_bucket_close,
                }
            )

        self.bars_m1["day_high_open"] = day_high_open
        self.bars_m1["day_low_open"] = day_low_open
        self.bars_m1["partial_tr_open"] = partial_tr_open

        self.m15_complete = pd.DataFrame(complete_buckets).set_index("bucket_start")
        prev_close = self.m15_complete["Close"].shift(1)
        tr = pd.concat(
            [
                self.m15_complete["High"] - self.m15_complete["Low"],
                (self.m15_complete["High"] - prev_close).abs(),
                (self.m15_complete["Low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        self.m15_complete["tr"] = tr

    def _build_m15_reference(self) -> None:
        previous_bucket = pd.Series(self.m15_complete.index, index=self.m15_complete.index).shift(1)
        previous_bucket.name = "previous_bucket"
        previous_bucket_map = previous_bucket.to_dict()
        self.bars_m1["previous_m15_bucket"] = self.bars_m1["m15_bucket"].map(previous_bucket_map)

    def get_signal_range(self, perc_of_signal_range: float, prev_contract_days: int) -> np.ndarray:
        key = (round(float(perc_of_signal_range), 8), int(prev_contract_days))
        if key in self._signal_range_cache:
            return self._signal_range_cache[key]

        daily_signal = np.where(
            self.daily["contract_day_number"] <= prev_contract_days,
            self.daily["previous_contract_average"],
            self.daily["current_contract_average_prev"],
        )
        daily_signal = np.where(pd.isna(daily_signal), 0.0, daily_signal)
        mapped = self.bars_m1["session_date"].map(
            pd.Series(daily_signal * perc_of_signal_range, index=self.daily.index)
        )
        values = mapped.fillna(0.0).to_numpy(dtype=float)
        self._signal_range_cache[key] = values
        return values

    def get_atr_open(self, period: int) -> np.ndarray:
        period = int(period)
        if period in self._atr_cache:
            return self._atr_cache[period]

        atr_complete = wilder_atr_from_tr(self.m15_complete["tr"], period)
        prev_atr = self.bars_m1["previous_m15_bucket"].map(atr_complete).to_numpy(dtype=float)
        partial_tr = self.bars_m1["partial_tr_open"].to_numpy(dtype=float)
        alpha = 1.0 / period
        atr_open = alpha * partial_tr + (1.0 - alpha) * prev_atr
        atr_open[np.isnan(prev_atr)] = np.nan
        self._atr_cache[period] = atr_open
        return atr_open


def resolve_open_gap_exit(
    direction: int,
    bar_open: float,
    stop_price: float,
    target_price: float,
) -> tuple[float | None, str | None]:
    if direction == 1:
        if bar_open <= stop_price:
            return round_to_tick(bar_open), "stop_gap_open"
        if bar_open >= target_price:
            return round_to_tick(bar_open), "take_profit_gap_open"
    else:
        if bar_open >= stop_price:
            return round_to_tick(bar_open), "stop_gap_open"
        if bar_open <= target_price:
            return round_to_tick(bar_open), "take_profit_gap_open"
    return None, None


def resolve_intrabar_exit(
    direction: int,
    bar_high: float,
    bar_low: float,
    stop_price: float,
    target_price: float,
) -> tuple[float | None, str | None]:
    if direction == 1:
        stop_hit = bar_low <= stop_price
        target_hit = bar_high >= target_price
    else:
        stop_hit = bar_high >= stop_price
        target_hit = bar_low <= target_price

    if stop_hit and target_hit:
        return stop_price, "ambiguous_stop_first"
    if stop_hit:
        return stop_price, "stop_loss"
    if target_hit:
        return target_price, "take_profit"
    return None, None


def calculate_metrics(trades_df: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    if len(trade_dates) == 0:
        raise ValueError("trade_dates cannot be empty.")
    start_date = pd.Timestamp(trade_dates[0]).date().isoformat()
    end_date = pd.Timestamp(trade_dates[-1]).date().isoformat()

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
            "max_drawdown_pct": 0.0,
            "expected_payoff": 0.0,
            "on_tester_value": 0.0,
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
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
    )
    equity = 10_000.0 + daily_pnl.cumsum()
    peaks = equity.cummax()
    drawdowns = (peaks - equity) / peaks.replace(0.0, np.nan) * 100.0
    max_drawdown_pct = float(drawdowns.max()) if len(drawdowns) else 0.0
    on_tester_value = float(pnl.sum()) / max_drawdown_pct if max_drawdown_pct > 0.0 else 0.0

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
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "expected_payoff": round(float(pnl.mean()), 2),
        "on_tester_value": round(on_tester_value, 6),
    }


def run_backtest(
    dataset: V10Dataset,
    params: V10Params,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    date_set = set(pd.to_datetime(trade_dates))
    mask_series = dataset.bars_m1["session_date"].isin(date_set)
    mask = mask_series.to_numpy()
    frame = dataset.bars_m1.loc[
        mask_series,
        ["Open", "High", "Low", "Close", "session_date", "day_high_open", "day_low_open"],
    ].copy()
    if frame.empty:
        metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return pd.DataFrame(), metrics

    signal_range = dataset.get_signal_range(
        params.FilterAsPercOfContractMARange,
        params.NumDaysToConsiderPreviousContractMARange,
    )
    atr_open = dataset.get_atr_open(params.ATR_Length)

    frame = frame.assign(
        signal_range=signal_range[mask],
        atr_open=atr_open[mask],
    )

    trades: list[TradeRecord] = []
    previous_high = 0.0
    previous_low = BIG_NUMBER
    current_date: pd.Timestamp | None = None

    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_time = pd.NaT
    signal_time = pd.NaT
    fill_reason = ""

    pending_order: dict[str, Any] | None = None

    cutoff_time = (
        dt.datetime(2000, 1, 1, params.MarketClose_Hour, params.MarketClose_Minute)
        - dt.timedelta(minutes=params.MinutesBeforeMarketCloseToClosePositions)
    ).time()

    for row in frame.itertuples(index=True):
        timestamp = row.Index
        session_date = row.session_date
        if current_date is None or session_date != current_date:
            if position != 0:
                exit_price = round_to_tick(float(row.Open))
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
                trades.append(
                    TradeRecord(
                        session_date=pd.Timestamp(current_date).date().isoformat(),
                        signal_time=str(signal_time),
                        entry_time=str(entry_time),
                        exit_time=str(timestamp),
                        direction="long" if position == 1 else "short",
                        entry_price=entry_price,
                        exit_price=exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=fill_reason or "carried_position",
                        exit_reason="forced_day_change",
                    )
                )

            current_date = session_date
            previous_high = 0.0
            previous_low = BIG_NUMBER
            position = 0
            pending_order = None

        bar_open = round_to_tick(float(row.Open))
        bar_high = round_to_tick(float(row.High))
        bar_low = round_to_tick(float(row.Low))
        bar_close = round_to_tick(float(row.Close))
        bar_time = timestamp.time()

        if position != 0:
            open_exit_price, open_exit_reason = resolve_open_gap_exit(position, bar_open, stop_price, target_price)
            if open_exit_price is not None and open_exit_reason is not None:
                pnl_points = (open_exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
                trades.append(
                    TradeRecord(
                        session_date=pd.Timestamp(session_date).date().isoformat(),
                        signal_time=str(signal_time),
                        entry_time=str(entry_time),
                        exit_time=str(timestamp),
                        direction="long" if position == 1 else "short",
                        entry_price=entry_price,
                        exit_price=open_exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=fill_reason or "active_position",
                        exit_reason=open_exit_reason,
                    )
                )
                position = 0
                pending_order = None

        if position == 0 and pending_order is not None:
            direction = int(pending_order["direction"])
            limit_price = float(pending_order["limit_price"])
            if (direction == 1 and bar_open <= limit_price) or (direction == -1 and bar_open >= limit_price):
                position = direction
                entry_price = bar_open
                stop_price = float(pending_order["stop_price"])
                target_price = float(pending_order["target_price"])
                entry_time = timestamp
                signal_time = pending_order["signal_time"]
                fill_reason = "better_open"
                pending_order = None

                open_exit_price, open_exit_reason = resolve_open_gap_exit(position, bar_open, stop_price, target_price)
                if open_exit_price is not None and open_exit_reason is not None:
                    pnl_points = (open_exit_price - entry_price) * position
                    pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
                    trades.append(
                        TradeRecord(
                            session_date=pd.Timestamp(session_date).date().isoformat(),
                            signal_time=str(signal_time),
                            entry_time=str(entry_time),
                            exit_time=str(timestamp),
                            direction="long" if position == 1 else "short",
                            entry_price=entry_price,
                            exit_price=open_exit_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            pnl_points=round(pnl_points, 2),
                            pnl_brl=round(pnl_brl, 2),
                            fill_reason=fill_reason,
                            exit_reason=open_exit_reason,
                        )
                    )
                    position = 0

        if bar_time >= cutoff_time:
            if position != 0:
                exit_price = bar_open
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
                trades.append(
                    TradeRecord(
                        session_date=pd.Timestamp(session_date).date().isoformat(),
                        signal_time=str(signal_time),
                        entry_time=str(entry_time),
                        exit_time=str(timestamp),
                        direction="long" if position == 1 else "short",
                        entry_price=entry_price,
                        exit_price=exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=fill_reason or "active_position",
                        exit_reason="time_cutoff",
                    )
                )
                position = 0
            pending_order = None
            continue

        current_day_high = float(row.day_high_open)
        current_day_low = float(row.day_low_open)
        current_day_range = current_day_high - current_day_low
        contract_range_filter_value = float(row.signal_range)
        atr_value = float(row.atr_open) if pd.notna(row.atr_open) else np.nan

        upper_retracement = round_to_tick(
            current_day_high - (current_day_range * params.RetracementLevel)
        )
        lower_retracement = round_to_tick(
            current_day_low + (current_day_range * params.RetracementLevel)
        )

        has_open_position = position != 0
        is_daily_range_big_enough = (
            current_day_range > 0.0
            and contract_range_filter_value > 0.0
            and current_day_range >= contract_range_filter_value
        )

        if not has_open_position and is_daily_range_big_enough and pd.notna(atr_value) and atr_value > 0.0:
            if current_day_high > previous_high:
                if pending_order is not None and int(pending_order["direction"]) == -1:
                    pending_order = None

                stop_loss = round_to_tick(upper_retracement - (atr_value * params.SL_ATRMultiplier))
                take_profit = round_to_tick(upper_retracement + (atr_value * params.TP_ATRMultiplier))
                pending_order = {
                    "direction": 1,
                    "limit_price": upper_retracement,
                    "stop_price": stop_loss,
                    "target_price": take_profit,
                    "signal_time": timestamp,
                }
            elif current_day_low < previous_low:
                if pending_order is not None and int(pending_order["direction"]) == 1:
                    pending_order = None

                stop_loss = round_to_tick(lower_retracement + (atr_value * params.SL_ATRMultiplier))
                take_profit = round_to_tick(lower_retracement - (atr_value * params.TP_ATRMultiplier))
                pending_order = {
                    "direction": -1,
                    "limit_price": lower_retracement,
                    "stop_price": stop_loss,
                    "target_price": take_profit,
                    "signal_time": timestamp,
                }

        if current_day_high > previous_high:
            previous_high = current_day_high
        if current_day_low < previous_low:
            previous_low = current_day_low

        if position == 0 and pending_order is not None:
            direction = int(pending_order["direction"])
            limit_price = float(pending_order["limit_price"])

            if direction == 1 and bar_low <= limit_price <= bar_high and bar_open > limit_price:
                position = 1
                entry_price = limit_price
                stop_price = float(pending_order["stop_price"])
                target_price = float(pending_order["target_price"])
                entry_time = timestamp
                signal_time = pending_order["signal_time"]
                fill_reason = "limit_touch"
                pending_order = None
            elif direction == -1 and bar_low <= limit_price <= bar_high and bar_open < limit_price:
                position = -1
                entry_price = limit_price
                stop_price = float(pending_order["stop_price"])
                target_price = float(pending_order["target_price"])
                entry_time = timestamp
                signal_time = pending_order["signal_time"]
                fill_reason = "limit_touch"
                pending_order = None

        if position != 0:
            exit_price, exit_reason = resolve_intrabar_exit(
                direction=position,
                bar_high=bar_high,
                bar_low=bar_low,
                stop_price=stop_price,
                target_price=target_price,
            )
            if exit_price is not None and exit_reason is not None:
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL * params.ContractsPerTrade - ROUND_TRIP_COST_BRL
                trades.append(
                    TradeRecord(
                        session_date=pd.Timestamp(session_date).date().isoformat(),
                        signal_time=str(signal_time),
                        entry_time=str(entry_time),
                        exit_time=str(timestamp),
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
                position = 0

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def split_dates(dates: pd.Index, train_ratio: float) -> tuple[pd.Index, pd.Index]:
    split_at = int(len(dates) * train_ratio)
    split_at = min(max(split_at, 1), len(dates) - 1)
    return dates[:split_at], dates[split_at:]


def sample_params(trial: optuna.Trial, baseline: V10Params) -> V10Params:
    return V10Params(
        ContractsPerTrade=baseline.ContractsPerTrade,
        FilterAsPercOfContractMARange=trial.suggest_float(
            "FilterAsPercOfContractMARange", 0.15, 0.50, step=0.05
        ),
        NumDaysToConsiderPreviousContractMARange=trial.suggest_int(
            "NumDaysToConsiderPreviousContractMARange", 3, 7
        ),
        RetracementLevel=trial.suggest_float("RetracementLevel", 0.10, 0.40, step=0.01),
        SL_ATRMultiplier=trial.suggest_float("SL_ATRMultiplier", 0.50, 1.50, step=0.05),
        TP_ATRMultiplier=trial.suggest_float("TP_ATRMultiplier", 0.10, 1.50, step=0.05),
        ATR_Length=trial.suggest_int("ATR_Length", 10, 40),
        MarketClose_Hour=baseline.MarketClose_Hour,
        MarketClose_Minute=baseline.MarketClose_Minute,
        MinutesBeforeMarketCloseToClosePositions=baseline.MinutesBeforeMarketCloseToClosePositions,
    )


def objective_factory(dataset: V10Dataset, train_dates: pd.Index, baseline: V10Params):
    min_trades = max(8, int(len(train_dates) * 0.05))

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
    baseline: V10Params,
    train_dates: pd.Index,
    test_dates: pd.Index,
    trials: int,
    seed: int,
) -> dict[str, Any]:
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective_factory(dataset, train_dates, baseline), n_trials=trials, show_progress_bar=False)

    best_params = sample_params(optuna.trial.FixedTrial(study.best_params), baseline)
    train_trades, train_metrics = run_backtest(dataset, best_params, train_dates)
    test_trades, test_metrics = run_backtest(dataset, best_params, test_dates)

    trials_df = study.trials_dataframe()
    return {
        "study": study,
        "best_params": best_params,
        "train_trades": train_trades,
        "train_metrics": train_metrics,
        "test_trades": test_trades,
        "test_metrics": test_metrics,
        "trials_df": trials_df,
    }


def build_summary(
    dataset: V10Dataset,
    baseline: V10Params,
    base_metrics: dict[str, Any],
    optimization: dict[str, Any] | None,
    data_path: Path,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "symbol": CONTINUOUS_SERIES_SYMBOL,
        "data_source": str(dataset.bars_m1.attrs.get("source_path", data_path)),
        "dataset": {
            "start_date": pd.Timestamp(dataset.trade_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(dataset.trade_dates[-1]).date().isoformat(),
            "trading_days": int(len(dataset.trade_dates)),
        },
        "baseline_params": asdict(baseline),
        "baseline_metrics": base_metrics,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure Python port of WDO Stalker Strategy v10.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--optuna-trials", type=int, default=40)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
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

    baseline = V10Params()
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

    summary = build_summary(dataset, baseline, baseline_metrics, optimization, data_path)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
