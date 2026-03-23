"""
Dedicated backtest runner for the WDO Opening Double Bar strategy.

Strategy rules:
1. Read the first two 15-minute bars of each B3 session (09:00 and 09:15).
2. Trade only when both bars are full-body candles on the same side:
   - Bullish full body: Open == Low and Close == High
   - Bearish full body: Open == High and Close == Low
3. Enter at the open of the 3rd bar (09:30).
4. Use a fixed 3-point stop loss and 7-point take profit.
5. If neither level is hit, close at the final bar close of the day.

Execution note:
If a single 15-minute bar touches both stop and target after entry, the
backtest assumes the stop was hit first. This is conservative because the
intrabar order is unknowable from 15-minute OHLC data alone.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.paths import ARTIFACT_REPORTS_DIR
from ..common.wdo_data import locate_wdo_bar_file

DEFAULT_TICK_SIZE = 0.5
DEFAULT_POINT_VALUE = 10.0
DEFAULT_ROUND_TRIP_COST_BRL = 11.0
DEFAULT_INITIAL_CAPITAL_BRL = 100_000.0
DEFAULT_TRAIN_RATIO = 0.70
OPEN_TIME = dt.time(9, 0)
SECOND_BAR_TIME = dt.time(9, 15)
ENTRY_BAR_TIME = dt.time(9, 30)


def default_data_path() -> Path:
    """Resolve the preferred raw storage path, with local parquet fallback."""
    return locate_wdo_bar_file("15m")


@dataclass(frozen=True)
class StrategyConfig:
    stop_points: float = 3.0
    target_points: float = 7.0
    tick_size: float = DEFAULT_TICK_SIZE
    point_value_brl: float = DEFAULT_POINT_VALUE
    round_trip_cost_brl: float = DEFAULT_ROUND_TRIP_COST_BRL
    initial_capital_brl: float = DEFAULT_INITIAL_CAPITAL_BRL


@dataclass(frozen=True)
class BacktestMetrics:
    period: str
    start_date: str
    end_date: str
    trading_days: int
    eligible_sessions: int
    missing_opening_bars: int
    first_bar_full_body: int
    second_bar_full_body: int
    qualifying_setups: int
    trades: int
    wins: int
    losses: int
    win_rate: float
    net_profit_brl: float
    total_return_pct: float
    sharpe: float
    max_drawdown_pct: float
    profit_factor: float
    gross_profit_brl: float
    gross_loss_brl: float
    avg_trade_brl: float
    avg_win_brl: float
    avg_loss_brl: float
    ambiguous_bars: int
    session_close_exits: int


def load_bars(path: Path) -> pd.DataFrame:
    """Load and normalize 15-minute OHLCV bars."""
    df = pd.read_parquet(path).copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("Expected parquet data indexed by time.")

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.sort_index()
    df["date"] = df.index.normalize()
    df["clock_time"] = df.index.time
    return df


def split_train_test(df: pd.DataFrame, train_ratio: float = DEFAULT_TRAIN_RATIO) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological 70/30-style split by trading date."""
    dates = pd.Index(sorted(df["date"].unique()))
    if len(dates) < 2:
        raise ValueError("Need at least two trading days for train/test split.")

    split_idx = int(len(dates) * train_ratio)
    split_idx = min(max(split_idx, 1), len(dates) - 1)
    split_date = dates[split_idx]

    train_df = df[df["date"] < split_date].copy()
    test_df = df[df["date"] >= split_date].copy()
    return train_df, test_df


def _is_close(a: float, b: float, tol: float = 1e-9) -> bool:
    return bool(np.isclose(a, b, atol=tol, rtol=0.0))


def classify_full_body(row: pd.Series) -> int:
    """
    Classify a bar as bullish/bearish full-body candle.

    Returns:
        1 for bullish full-body
       -1 for bearish full-body
        0 otherwise
    """
    if row["Close"] > row["Open"]:
        if _is_close(row["Open"], row["Low"]) and _is_close(row["Close"], row["High"]):
            return 1
    elif row["Close"] < row["Open"]:
        if _is_close(row["Open"], row["High"]) and _is_close(row["Close"], row["Low"]):
            return -1
    return 0


def _get_opening_rows(day_df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series] | None:
    """Fetch the 09:00, 09:15, and 09:30 bars for a session."""
    required_times = [OPEN_TIME, SECOND_BAR_TIME, ENTRY_BAR_TIME]
    lookup = {}
    for time_value in required_times:
        matches = day_df[day_df["clock_time"] == time_value]
        if len(matches) != 1:
            return None
        lookup[time_value] = matches.iloc[0]
    if any(time_value not in lookup for time_value in required_times):
        return None
    return tuple(lookup[time_value] for time_value in required_times)  # type: ignore[return-value]


def _scan_exit(
    trade_bars: pd.DataFrame,
    side: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> tuple[pd.Timestamp, float, str, bool]:
    """
    Walk forward through bars until the trade exits.

    Returns:
        exit_time, exit_price, exit_reason, ambiguous_bar
    """
    for ts, bar in trade_bars.iterrows():
        high = float(bar["High"])
        low = float(bar["Low"])

        if side == 1:
            stop_hit = low <= stop_price
            target_hit = high >= target_price
        else:
            stop_hit = high >= stop_price
            target_hit = low <= target_price

        if stop_hit and target_hit:
            return ts, stop_price, "stop_first_ambiguous_bar", True
        if stop_hit:
            return ts, stop_price, "stop_loss", False
        if target_hit:
            return ts, target_price, "take_profit", False

    last_ts = trade_bars.index[-1]
    last_close = float(trade_bars["Close"].iloc[-1])
    return last_ts, last_close, "session_close", False


def run_backtest(df: pd.DataFrame, config: StrategyConfig, period: str) -> tuple[pd.DataFrame, BacktestMetrics]:
    """Run the Opening Double Bar strategy over a DataFrame of 15-minute bars."""
    trades: list[dict[str, object]] = []
    diagnostics = {
        "eligible_sessions": 0,
        "missing_opening_bars": 0,
        "first_bar_full_body": 0,
        "second_bar_full_body": 0,
        "qualifying_setups": 0,
    }

    for session_date, day_df in df.groupby("date", sort=True):
        day_df = day_df.sort_index().copy()
        opening_rows = _get_opening_rows(day_df)
        if opening_rows is None:
            diagnostics["missing_opening_bars"] += 1
            continue

        diagnostics["eligible_sessions"] += 1
        first_bar, second_bar, entry_bar = opening_rows
        first_side = classify_full_body(first_bar)
        second_side = classify_full_body(second_bar)
        if first_side != 0:
            diagnostics["first_bar_full_body"] += 1
        if second_side != 0:
            diagnostics["second_bar_full_body"] += 1
        if first_side == 0 or second_side == 0 or first_side != second_side:
            continue

        diagnostics["qualifying_setups"] += 1
        side = first_side
        entry_time = entry_bar.name
        entry_price = float(entry_bar["Open"])
        stop_price = entry_price - config.stop_points if side == 1 else entry_price + config.stop_points
        target_price = entry_price + config.target_points if side == 1 else entry_price - config.target_points

        trade_bars = day_df.loc[day_df.index >= entry_time]
        if trade_bars.empty:
            continue

        exit_time, exit_price, exit_reason, ambiguous_bar = _scan_exit(
            trade_bars=trade_bars,
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

        pnl_points = (exit_price - entry_price) * side
        pnl_brl = pnl_points * config.point_value_brl - config.round_trip_cost_brl

        trades.append(
            {
                "period": period,
                "trade_date": pd.Timestamp(session_date).date().isoformat(),
                "side": "long" if side == 1 else "short",
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "pnl_points": pnl_points,
                "pnl_brl": pnl_brl,
                "exit_reason": exit_reason,
                "ambiguous_bar": ambiguous_bar,
                "bars_held": int(trade_bars.index.get_loc(exit_time)) + 1,
            }
        )

    trades_df = pd.DataFrame(trades)
    metrics = calculate_metrics(
        df=df,
        trades_df=trades_df,
        config=config,
        period=period,
        diagnostics=diagnostics,
    )
    return trades_df, metrics


def calculate_metrics(
    df: pd.DataFrame,
    trades_df: pd.DataFrame,
    config: StrategyConfig,
    period: str,
    diagnostics: dict[str, int],
) -> BacktestMetrics:
    """Compute user-facing performance metrics."""
    trading_days = int(df["date"].nunique())
    start_date = df.index.min().date().isoformat()
    end_date = df.index.max().date().isoformat()

    if trades_df.empty:
        return BacktestMetrics(
            period=period,
            start_date=start_date,
            end_date=end_date,
            trading_days=trading_days,
            eligible_sessions=diagnostics["eligible_sessions"],
            missing_opening_bars=diagnostics["missing_opening_bars"],
            first_bar_full_body=diagnostics["first_bar_full_body"],
            second_bar_full_body=diagnostics["second_bar_full_body"],
            qualifying_setups=diagnostics["qualifying_setups"],
            trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            net_profit_brl=0.0,
            total_return_pct=0.0,
            sharpe=0.0,
            max_drawdown_pct=0.0,
            profit_factor=0.0,
            gross_profit_brl=0.0,
            gross_loss_brl=0.0,
            avg_trade_brl=0.0,
            avg_win_brl=0.0,
            avg_loss_brl=0.0,
            ambiguous_bars=0,
            session_close_exits=0,
        )

    pnl = trades_df["pnl_brl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.abs().sum())
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    net_profit = float(pnl.sum())
    total_return_pct = (net_profit / config.initial_capital_brl) * 100.0

    daily_pnl = (
        trades_df.assign(trade_date=pd.to_datetime(trades_df["trade_date"]))
        .groupby("trade_date")["pnl_brl"]
        .sum()
        .reindex(pd.Index(sorted(df["date"].unique())), fill_value=0.0)
    )
    daily_returns = daily_pnl / config.initial_capital_brl
    if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0:
        sharpe = float(np.sqrt(252) * daily_returns.mean() / daily_returns.std(ddof=1))
    else:
        sharpe = 0.0

    equity = config.initial_capital_brl + daily_pnl.cumsum()
    peak = equity.cummax()
    drawdown = (peak - equity) / peak.replace(0.0, np.nan)
    max_drawdown_pct = float(drawdown.max() * 100.0) if len(drawdown) else 0.0

    return BacktestMetrics(
        period=period,
        start_date=start_date,
        end_date=end_date,
        trading_days=trading_days,
        eligible_sessions=diagnostics["eligible_sessions"],
        missing_opening_bars=diagnostics["missing_opening_bars"],
        first_bar_full_body=diagnostics["first_bar_full_body"],
        second_bar_full_body=diagnostics["second_bar_full_body"],
        qualifying_setups=diagnostics["qualifying_setups"],
        trades=int(len(trades_df)),
        wins=int((pnl > 0).sum()),
        losses=int((pnl < 0).sum()),
        win_rate=float((pnl > 0).mean()),
        net_profit_brl=net_profit,
        total_return_pct=total_return_pct,
        sharpe=sharpe,
        max_drawdown_pct=max_drawdown_pct,
        profit_factor=profit_factor,
        gross_profit_brl=gross_profit,
        gross_loss_brl=gross_loss,
        avg_trade_brl=float(pnl.mean()),
        avg_win_brl=float(wins.mean()) if not wins.empty else 0.0,
        avg_loss_brl=float(losses.mean()) if not losses.empty else 0.0,
        ambiguous_bars=int(trades_df["ambiguous_bar"].sum()),
        session_close_exits=int((trades_df["exit_reason"] == "session_close").sum()),
    )


def _format_metric_value(value: float | int | str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, np.integer)):
        return f"{int(value)}"
    if np.isinf(value):
        return "inf"
    return f"{float(value):.4f}"


def build_report(
    data_path: Path,
    config: StrategyConfig,
    full_metrics: BacktestMetrics,
    train_metrics: BacktestMetrics,
    test_metrics: BacktestMetrics,
) -> str:
    """Render a compact Markdown report."""
    rows = [
        ("Start date", full_metrics.start_date, train_metrics.start_date, test_metrics.start_date),
        ("End date", full_metrics.end_date, train_metrics.end_date, test_metrics.end_date),
        ("Trading days", full_metrics.trading_days, train_metrics.trading_days, test_metrics.trading_days),
        ("Eligible sessions", full_metrics.eligible_sessions, train_metrics.eligible_sessions, test_metrics.eligible_sessions),
        ("Missing opening bars", full_metrics.missing_opening_bars, train_metrics.missing_opening_bars, test_metrics.missing_opening_bars),
        ("1st bar full-body", full_metrics.first_bar_full_body, train_metrics.first_bar_full_body, test_metrics.first_bar_full_body),
        ("2nd bar full-body", full_metrics.second_bar_full_body, train_metrics.second_bar_full_body, test_metrics.second_bar_full_body),
        ("Qualifying setups", full_metrics.qualifying_setups, train_metrics.qualifying_setups, test_metrics.qualifying_setups),
        ("Trades", full_metrics.trades, train_metrics.trades, test_metrics.trades),
        ("Win rate", f"{full_metrics.win_rate * 100:.2f}%", f"{train_metrics.win_rate * 100:.2f}%", f"{test_metrics.win_rate * 100:.2f}%"),
        ("Net profit (BRL)", f"{full_metrics.net_profit_brl:.2f}", f"{train_metrics.net_profit_brl:.2f}", f"{test_metrics.net_profit_brl:.2f}"),
        ("Total return", f"{full_metrics.total_return_pct:.2f}%", f"{train_metrics.total_return_pct:.2f}%", f"{test_metrics.total_return_pct:.2f}%"),
        ("Sharpe", _format_metric_value(full_metrics.sharpe), _format_metric_value(train_metrics.sharpe), _format_metric_value(test_metrics.sharpe)),
        ("Max drawdown", f"{full_metrics.max_drawdown_pct:.2f}%", f"{train_metrics.max_drawdown_pct:.2f}%", f"{test_metrics.max_drawdown_pct:.2f}%"),
        ("Profit factor", _format_metric_value(full_metrics.profit_factor), _format_metric_value(train_metrics.profit_factor), _format_metric_value(test_metrics.profit_factor)),
        ("Ambiguous bars", full_metrics.ambiguous_bars, train_metrics.ambiguous_bars, test_metrics.ambiguous_bars),
        ("Session-close exits", full_metrics.session_close_exits, train_metrics.session_close_exits, test_metrics.session_close_exits),
    ]

    lines = [
        "# WDO Opening Double Bar Report",
        "",
        "## Setup",
        f"- Data path: `{data_path}`",
        "- Timeframe: `15m`",
        "- Entry: open of the 3rd bar (09:30 BRT)",
        f"- Stop loss: `{config.stop_points:.1f}` points",
        f"- Take profit: `{config.target_points:.1f}` points",
        f"- Point value: `R$ {config.point_value_brl:.2f}` per point",
        f"- Round-trip cost: `R$ {config.round_trip_cost_brl:.2f}` per trade",
        f"- Initial capital for return/DD/Sharpe: `R$ {config.initial_capital_brl:,.2f}`",
        "- Same-bar stop/target conflicts on 15m candles are resolved as stop-first.",
        "",
        "## Metrics",
        "",
        "| Metric | Full | Train (70%) | Test (30%) |",
        "|---|---:|---:|---:|",
    ]
    for label, full_value, train_value, test_value in rows:
        lines.append(f"| {label} | {full_value} | {train_value} | {test_value} |")

    return "\n".join(lines) + "\n"


def write_outputs(
    output_dir: Path,
    data_path: Path,
    config: StrategyConfig,
    full_trades: pd.DataFrame,
    train_trades: pd.DataFrame,
    test_trades: pd.DataFrame,
    full_metrics: BacktestMetrics,
    train_metrics: BacktestMetrics,
    test_metrics: BacktestMetrics,
) -> None:
    """Persist report artifacts for later inspection."""
    output_dir.mkdir(parents=True, exist_ok=True)

    report_text = build_report(
        data_path=data_path,
        config=config,
        full_metrics=full_metrics,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
    )
    (output_dir / "opening_double_bar_report.md").write_text(report_text, encoding="utf-8")

    metrics_payload = {
        "config": asdict(config),
        "full": asdict(full_metrics),
        "train": asdict(train_metrics),
        "test": asdict(test_metrics),
    }
    (output_dir / "opening_double_bar_metrics.json").write_text(
        json.dumps(metrics_payload, indent=2),
        encoding="utf-8",
    )

    full_trades.to_csv(output_dir / "opening_double_bar_trades_full.csv", index=False)
    train_trades.to_csv(output_dir / "opening_double_bar_trades_train.csv", index=False)
    test_trades.to_csv(output_dir / "opening_double_bar_trades_test.csv", index=False)


def print_summary(full_metrics: BacktestMetrics, train_metrics: BacktestMetrics, test_metrics: BacktestMetrics) -> None:
    """Print a compact CLI summary."""
    for metrics in (full_metrics, train_metrics, test_metrics):
        print(f"\n{metrics.period.upper()} [{metrics.start_date} -> {metrics.end_date}]")
        print(f"  eligible_sessions: {metrics.eligible_sessions}")
        print(f"  missing_opening_bars: {metrics.missing_opening_bars}")
        print(f"  qualifying_setups: {metrics.qualifying_setups}")
        print(f"  trades: {metrics.trades}")
        print(f"  win_rate: {metrics.win_rate * 100:.2f}%")
        print(f"  net_profit_brl: {metrics.net_profit_brl:.2f}")
        print(f"  total_return_pct: {metrics.total_return_pct:.2f}%")
        print(f"  sharpe: {_format_metric_value(metrics.sharpe)}")
        print(f"  max_drawdown_pct: {metrics.max_drawdown_pct:.2f}%")
        print(f"  profit_factor: {_format_metric_value(metrics.profit_factor)}")
        print(f"  ambiguous_bars: {metrics.ambiguous_bars}")
        print(f"  session_close_exits: {metrics.session_close_exits}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the WDO Opening Double Bar strategy.")
    parser.add_argument("--data-path", type=Path, default=None, help="Path to the WDO 15m parquet file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACT_REPORTS_DIR / "opening_double_bar",
        help="Directory for report artifacts.",
    )
    parser.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO, help="Chronological train ratio.")
    parser.add_argument("--stop-points", type=float, default=3.0, help="Stop loss in points.")
    parser.add_argument("--target-points", type=float, default=7.0, help="Take profit in points.")
    parser.add_argument("--point-value", type=float, default=DEFAULT_POINT_VALUE, help="BRL per point.")
    parser.add_argument("--round-trip-cost", type=float, default=DEFAULT_ROUND_TRIP_COST_BRL, help="Round-trip cost in BRL.")
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL_BRL, help="Initial capital in BRL.")
    args = parser.parse_args()

    data_path = args.data_path or default_data_path()
    config = StrategyConfig(
        stop_points=args.stop_points,
        target_points=args.target_points,
        point_value_brl=args.point_value,
        round_trip_cost_brl=args.round_trip_cost,
        initial_capital_brl=args.initial_capital,
    )

    df = load_bars(data_path)
    train_df, test_df = split_train_test(df, train_ratio=args.train_ratio)

    full_trades, full_metrics = run_backtest(df, config=config, period="full")
    train_trades, train_metrics = run_backtest(train_df, config=config, period="train")
    test_trades, test_metrics = run_backtest(test_df, config=config, period="test")

    write_outputs(
        output_dir=args.output_dir,
        data_path=data_path,
        config=config,
        full_trades=full_trades,
        train_trades=train_trades,
        test_trades=test_trades,
        full_metrics=full_metrics,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
    )
    print_summary(full_metrics, train_metrics, test_metrics)


if __name__ == "__main__":
    main()
