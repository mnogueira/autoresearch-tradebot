from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

from ..common.paths import artifact_output_dir
from ..common.wdo_data import locate_wdo_bar_file

POINT_VALUE = 10.0
TICK_SIZE = 0.5
ROUND_TRIP_COST_BRL = 11.0
SESSION_START = time(9, 0)
LAST_SIGNAL_BAR = time(17, 30)
LAST_ENTRY_TIME = time(17, 45)
SESSION_EXIT_TIME = time(17, 55)
HTF_FAST_EMA = 8
HTF_SLOW_EMA = 21


@dataclass(frozen=True)
class StrategyParams:
    wick_tolerance_atr_frac: float
    atr_period: int
    stop_points: float
    target_points: float


@dataclass
class Trade:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    entry_price: float
    exit_price: float
    stop_points: float
    target_points: float
    pnl_points: float
    pnl_brl: float
    exit_reason: str


def locate_data_file(timeframe: str) -> Path:
    return locate_wdo_bar_file(timeframe)


def load_parquet(timeframe: str) -> pd.DataFrame:
    path = locate_data_file(timeframe)
    df = pd.read_parquet(path)
    df = df.sort_index()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.attrs["source_path"] = str(path)
    return df


def filter_intraday(df: pd.DataFrame, start: time, end: time) -> pd.DataFrame:
    mask = (df.index.time >= start) & (df.index.time <= end)
    return df.loc[mask].copy()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


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


def compute_trend_context(
    bars_15m: pd.DataFrame,
    bars_1h: pd.DataFrame,
    bars_1d: pd.DataFrame,
) -> pd.DataFrame:
    h1_fast = ema(bars_1h["Close"], HTF_FAST_EMA)
    h1_slow = ema(bars_1h["Close"], HTF_SLOW_EMA)
    h1_state = pd.Series(
        np.where(
            h1_fast > h1_slow,
            1,
            np.where(
                h1_fast < h1_slow,
                -1,
                0,
            ),
        ),
        index=bars_1h.index,
        name="h1_trend",
    ).shift(1)

    d1_fast = ema(bars_1d["Close"], HTF_FAST_EMA)
    d1_slow = ema(bars_1d["Close"], HTF_SLOW_EMA)
    d1_state = pd.Series(
        np.where(
            d1_fast > d1_slow,
            1,
            np.where(
                d1_fast < d1_slow,
                -1,
                0,
            ),
        ),
        index=bars_1d.index,
        name="d1_trend",
    ).shift(1)

    trend = pd.DataFrame(index=bars_15m.index)
    trend["h1_trend"] = h1_state.reindex(bars_15m.index, method="ffill")
    trend["d1_trend"] = d1_state.reindex(bars_15m.index, method="ffill")
    trend["trend"] = np.where(
        (trend["h1_trend"] == 1) & (trend["d1_trend"] == 1),
        1,
        np.where(
            (trend["h1_trend"] == -1) & (trend["d1_trend"] == -1),
            -1,
            0,
        ),
    )
    return trend


def build_base_frame(
    bars_15m: pd.DataFrame,
    bars_1h: pd.DataFrame,
    bars_1d: pd.DataFrame,
    minute_bars: pd.DataFrame,
) -> pd.DataFrame:
    base = filter_intraday(bars_15m, SESSION_START, LAST_ENTRY_TIME)
    base = base.copy()
    base["session_date"] = base.index.normalize()
    base["next_open_time"] = base.groupby("session_date").apply(
        lambda frame: pd.Series(frame.index, index=frame.index).shift(-1)
    ).reset_index(level=0, drop=True)
    base["can_signal"] = base.index.time <= LAST_SIGNAL_BAR
    base["minute_date_available"] = base["session_date"].isin(minute_bars.index.normalize().unique())

    trend = compute_trend_context(base, bars_1h, bars_1d)
    base = base.join(trend)
    return base


def generate_signal_frame(base: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    frame = base.copy()
    frame["atr"] = atr_wilder(frame, params.atr_period)

    upper_wick = frame["High"] - frame[["Open", "Close"]].max(axis=1)
    lower_wick = frame[["Open", "Close"]].min(axis=1) - frame["Low"]
    body = frame["Close"] - frame["Open"]

    wick_tolerance = np.maximum(TICK_SIZE, frame["atr"] * params.wick_tolerance_atr_frac)

    bullish_full_body = (body > 0) & (upper_wick <= wick_tolerance) & (lower_wick <= wick_tolerance)
    bearish_full_body = (body < 0) & (upper_wick <= wick_tolerance) & (lower_wick <= wick_tolerance)

    frame["long_signal"] = (
        bullish_full_body
        & (frame["trend"] == 1)
        & frame["can_signal"]
        & frame["minute_date_available"]
        & frame["next_open_time"].notna()
    )
    frame["short_signal"] = (
        bearish_full_body
        & (frame["trend"] == -1)
        & frame["can_signal"]
        & frame["minute_date_available"]
        & frame["next_open_time"].notna()
    )
    frame["signal_direction"] = np.where(frame["long_signal"], 1, np.where(frame["short_signal"], -1, 0))
    frame["upper_wick"] = upper_wick
    frame["lower_wick"] = lower_wick
    frame["wick_tolerance"] = wick_tolerance
    return frame


def simulate_trade(
    minute_slice: pd.DataFrame,
    direction: int,
    entry_price: float,
    stop_points: float,
    target_points: float,
) -> tuple[pd.Timestamp, float, str]:
    if minute_slice.empty:
        raise ValueError("Minute slice is empty for trade simulation.")

    stop_price = entry_price - stop_points if direction == 1 else entry_price + stop_points
    target_price = entry_price + target_points if direction == 1 else entry_price - target_points

    for minute in minute_slice.itertuples():
        if direction == 1:
            hit_stop = minute.Low <= stop_price
            hit_target = minute.High >= target_price
        else:
            hit_stop = minute.High >= stop_price
            hit_target = minute.Low <= target_price

        if hit_stop and hit_target:
            return minute.Index, stop_price, "ambiguous_stop_first"
        if hit_stop:
            return minute.Index, stop_price, "stop_loss"
        if hit_target:
            return minute.Index, target_price, "take_profit"

    last_bar = minute_slice.iloc[-1]
    return minute_slice.index[-1], float(last_bar["Close"]), "session_close"


def run_backtest(
    signal_frame: pd.DataFrame,
    minute_bars: pd.DataFrame,
    trade_dates: pd.Index,
    params: StrategyParams,
) -> tuple[pd.DataFrame, dict[str, float | int | str]]:
    minute_by_date = {
        date: frame
        for date, frame in minute_bars.groupby(minute_bars.index.normalize())
        if date in set(trade_dates)
    }

    frame = signal_frame[signal_frame["session_date"].isin(trade_dates)].copy()
    frame = frame[frame["signal_direction"] != 0]
    trades: list[Trade] = []
    next_entry_allowed_at = pd.Timestamp.min

    for signal in frame.itertuples():
        entry_time = signal.next_open_time
        if pd.isna(entry_time) or entry_time < next_entry_allowed_at:
            continue

        day_minutes = minute_by_date.get(signal.session_date)
        if day_minutes is None:
            continue

        minute_slice = day_minutes.loc[day_minutes.index >= entry_time]
        if minute_slice.empty:
            continue

        try:
            entry_price = float(minute_slice.loc[entry_time, "Open"])
        except KeyError:
            continue

        exit_time, exit_price, exit_reason = simulate_trade(
            minute_slice=minute_slice,
            direction=int(signal.signal_direction),
            entry_price=entry_price,
            stop_points=params.stop_points,
            target_points=params.target_points,
        )

        pnl_points = (exit_price - entry_price) * int(signal.signal_direction)
        pnl_brl = pnl_points * POINT_VALUE - ROUND_TRIP_COST_BRL

        trades.append(
            Trade(
                signal_time=signal.Index,
                entry_time=entry_time,
                exit_time=exit_time,
                direction=int(signal.signal_direction),
                entry_price=entry_price,
                exit_price=exit_price,
                stop_points=params.stop_points,
                target_points=params.target_points,
                pnl_points=pnl_points,
                pnl_brl=pnl_brl,
                exit_reason=exit_reason,
            )
        )
        next_entry_allowed_at = exit_time

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df, len(trade_dates))
    return trades_df, metrics


def calculate_metrics(trades_df: pd.DataFrame, trading_days: int) -> dict[str, float | int | str]:
    if trades_df.empty:
        return {
            "sharpe": 0.0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "net_profit_brl": 0.0,
            "avg_profit_brl": 0.0,
            "avg_win_brl": 0.0,
            "avg_loss_brl": 0.0,
            "max_drawdown_pct": 0.0,
            "total_trades": 0,
            "take_profit_trades": 0,
            "stop_loss_trades": 0,
            "session_close_trades": 0,
        }

    pnl = trades_df["pnl_brl"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total_trades = len(pnl)

    if total_trades > 1 and pnl.std(ddof=1) > 0:
        trades_per_day = total_trades / max(trading_days, 1)
        sharpe = (pnl.mean() / pnl.std(ddof=1)) * math.sqrt(trades_per_day * 252)
    else:
        sharpe = 0.0

    gross_profit = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0

    equity = 100_000 + np.concatenate([[0.0], np.cumsum(pnl)])
    peaks = np.maximum.accumulate(equity)
    drawdowns = (peaks - equity) / peaks * 100

    return {
        "sharpe": round(float(sharpe), 4),
        "profit_factor": round(float(profit_factor), 4) if np.isfinite(profit_factor) else float("inf"),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "net_profit_brl": round(float(pnl.sum()), 2),
        "avg_profit_brl": round(float(pnl.mean()), 2),
        "avg_win_brl": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss_brl": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "max_drawdown_pct": round(float(drawdowns.max()), 2),
        "total_trades": int(total_trades),
        "take_profit_trades": int((trades_df["exit_reason"] == "take_profit").sum()),
        "stop_loss_trades": int(trades_df["exit_reason"].isin(["stop_loss", "ambiguous_stop_first"]).sum()),
        "session_close_trades": int((trades_df["exit_reason"] == "session_close").sum()),
    }


def split_walk_forward_dates(base: pd.DataFrame, train_ratio: float) -> tuple[pd.Index, pd.Index]:
    common_dates = pd.Index(sorted(base.loc[base["minute_date_available"], "session_date"].unique()))
    split_at = max(1, int(len(common_dates) * train_ratio))
    split_at = min(split_at, len(common_dates) - 1)
    return common_dates[:split_at], common_dates[split_at:]


def prepare_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_15m = load_parquet("15m")
    bars_1h = load_parquet("1h")
    bars_1d = load_parquet("1d")
    minute_bars = filter_intraday(load_parquet("1m"), SESSION_START, SESSION_EXIT_TIME)

    base = build_base_frame(bars_15m, bars_1h, bars_1d, minute_bars)
    first_minute_date = minute_bars.index.normalize().min()
    base = base.loc[base["session_date"] >= first_minute_date].copy()
    return base, minute_bars


def objective_factory(base: pd.DataFrame, minute_bars: pd.DataFrame, train_dates: pd.Index):
    def objective(trial: optuna.Trial) -> float:
        params = StrategyParams(
            wick_tolerance_atr_frac=trial.suggest_float("wick_tolerance_atr_frac", 0.00, 0.20, step=0.01),
            atr_period=trial.suggest_int("atr_period", 5, 40),
            stop_points=trial.suggest_float("stop_points", 1.5, 6.0, step=0.5),
            target_points=trial.suggest_float("target_points", 3.0, 12.0, step=0.5),
        )

        if params.target_points <= params.stop_points:
            return -1e9

        signal_frame = generate_signal_frame(base, params)
        trades_df, metrics = run_backtest(signal_frame, minute_bars, train_dates, params)

        trial.set_user_attr("train_metrics", metrics)
        trial.set_user_attr("train_trade_count", int(metrics["total_trades"]))
        if not trades_df.empty:
            trial.set_user_attr("train_net_profit_brl", float(metrics["net_profit_brl"]))

        total_trades = int(metrics["total_trades"])
        if total_trades < 15:
            return -1000 + total_trades

        score = float(metrics["sharpe"])
        score += min(float(metrics["profit_factor"]), 5.0) * 0.02
        score -= float(metrics["max_drawdown_pct"]) * 0.01
        return score

    return objective


def metrics_to_printable(prefix: str, metrics: dict[str, float | int | str]) -> list[str]:
    ordered_keys = [
        "sharpe",
        "profit_factor",
        "win_rate",
        "net_profit_brl",
        "avg_profit_brl",
        "avg_win_brl",
        "avg_loss_brl",
        "max_drawdown_pct",
        "total_trades",
        "take_profit_trades",
        "stop_loss_trades",
        "session_close_trades",
    ]
    return [f"{prefix}_{key}: {metrics[key]}" for key in ordered_keys]


def save_results(
    output_dir: Path,
    best_params: StrategyParams,
    train_metrics: dict[str, float | int | str],
    test_metrics: dict[str, float | int | str],
    train_trades: pd.DataFrame,
    test_trades: pd.DataFrame,
    study: optuna.Study,
    train_dates: pd.Index,
    test_dates: pd.Index,
    base: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "data_sources": {
            "1m": str(locate_data_file("1m")),
            "15m": str(locate_data_file("15m")),
            "1h": str(locate_data_file("1h")),
            "1d": str(locate_data_file("1d")),
        },
        "dataset": {
            "first_trade_date": str(base["session_date"].min().date()),
            "last_trade_date": str(base["session_date"].max().date()),
            "trade_days": int(base["session_date"].nunique()),
            "train_days": int(len(train_dates)),
            "test_days": int(len(test_dates)),
            "train_start": str(train_dates[0].date()),
            "train_end": str(train_dates[-1].date()),
            "test_start": str(test_dates[0].date()),
            "test_end": str(test_dates[-1].date()),
        },
        "assumptions": {
            "trend": "Bullish when both previous closed H1 and previous closed D1 bars have EMA(8) above EMA(21); bearish when both are below.",
            "signal": "Bullish full-body candle in bullish higher-timeframe trend buys next 15m open; bearish full-body candle in bearish trend sells next 15m open.",
            "no_wick_tolerance": "Upper and lower wicks must each be <= max(0.5 point, ATR * wick_tolerance_atr_frac).",
            "execution": "Entry at next 15m bar open, intrabar SL/TP evaluated on 1m bars, ambiguous minute bars resolve pessimistically with stop first.",
        },
        "best_params": asdict(best_params),
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "optuna": {
            "trials": len(study.trials),
            "best_objective": study.best_value,
            "best_trial_number": study.best_trial.number,
        },
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    train_trades.to_csv(output_dir / "train_trades.csv", index=False)
    test_trades.to_csv(output_dir / "test_trades.csv", index=False)

    trials = []
    for trial in study.trials:
        row = {
            "number": trial.number,
            "value": trial.value,
            "state": str(trial.state),
            **trial.params,
        }
        train_metrics_attr = trial.user_attrs.get("train_metrics", {})
        for key, value in train_metrics_attr.items():
            row[f"train_{key}"] = value
        trials.append(row)

    pd.DataFrame(trials).to_csv(output_dir / "optuna_trials.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="WDO No-Wick Bar Momentum optimization and walk-forward test")
    parser.add_argument("--trials", type=int, default=300, help="Number of Optuna trials")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Chronological train/test split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for Optuna")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=artifact_output_dir("no_wick_bar_momentum_wdo"),
        help="Directory for JSON/CSV artifacts",
    )
    args = parser.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    base, minute_bars = prepare_dataset()
    train_dates, test_dates = split_walk_forward_dates(base, train_ratio=args.train_ratio)

    print("WDO No-Wick Bar Momentum")
    print(f"15m data: {locate_data_file('15m')}")
    print(f"1m execution data: {locate_data_file('1m')}")
    print(f"Tradeable date range: {train_dates[0].date()} -> {test_dates[-1].date()}")
    print(f"Train days: {len(train_dates)} | Test days: {len(test_dates)}")
    print()

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=args.seed),
    )
    study.optimize(objective_factory(base, minute_bars, train_dates), n_trials=args.trials, show_progress_bar=False)

    best_params = StrategyParams(
        wick_tolerance_atr_frac=float(study.best_params["wick_tolerance_atr_frac"]),
        atr_period=int(study.best_params["atr_period"]),
        stop_points=float(study.best_params["stop_points"]),
        target_points=float(study.best_params["target_points"]),
    )

    signal_frame = generate_signal_frame(base, best_params)
    train_trades, train_metrics = run_backtest(signal_frame, minute_bars, train_dates, best_params)
    test_trades, test_metrics = run_backtest(signal_frame, minute_bars, test_dates, best_params)

    print("Optimized parameters")
    for key, value in asdict(best_params).items():
        print(f"  {key}: {value}")
    print()

    print("Train metrics")
    for line in metrics_to_printable("train", train_metrics):
        print(f"  {line}")
    print()

    print("Walk-forward test metrics")
    for line in metrics_to_printable("test", test_metrics):
        print(f"  {line}")
    print()

    save_results(
        output_dir=args.output_dir,
        best_params=best_params,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        train_trades=train_trades,
        test_trades=test_trades,
        study=study,
        train_dates=train_dates,
        test_dates=test_dates,
        base=base,
    )

    print(f"Artifacts saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
