"""
backtest.py — Backtesting engine for WDO day-trading strategies.
READ-ONLY: The AI agent must NOT modify this file.

Runs the strategy from strategy.py, simulates execution with realistic costs,
and prints metrics in a parseable format for the autoresearch loop.

Usage: python backtest.py [--timeframe M5] [--train-ratio 0.70]
"""

import sys
import importlib
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from prepare import (
    TICK_SIZE, POINT_VALUE, TICK_VALUE, TOTAL_COST_RT,
    SESSION_START, SESSION_END,
    load_data, split_data, add_session_markers,
    DEFAULT_TIMEFRAME,
)

# ── Configuration ────────────────────────────────────────────────────────────
MIN_TRADES = 50          # minimum trades required for valid experiment
CONTRACTS = 1            # fixed position size for backtesting


@dataclass
class BacktestResult:
    """Container for backtest metrics."""
    sharpe: float
    profit_factor: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    net_profit_brl: float
    avg_profit_per_trade: float
    avg_win_brl: float
    avg_loss_brl: float
    max_consec_losses: int
    exposure_pct: float
    period: str  # "train" or "test"

    def print_metrics(self):
        """Print metrics in parseable format for the autoresearch loop."""
        print(f"{self.period}_sharpe: {self.sharpe:.4f}")
        print(f"{self.period}_profit_factor: {self.profit_factor:.4f}")
        print(f"{self.period}_max_drawdown_pct: {self.max_drawdown_pct:.2f}")
        print(f"{self.period}_win_rate: {self.win_rate:.4f}")
        print(f"{self.period}_total_trades: {self.total_trades}")
        print(f"{self.period}_net_profit_brl: {self.net_profit_brl:.2f}")
        print(f"{self.period}_avg_profit_per_trade: {self.avg_profit_per_trade:.2f}")
        print(f"{self.period}_avg_win_brl: {self.avg_win_brl:.2f}")
        print(f"{self.period}_avg_loss_brl: {self.avg_loss_brl:.2f}")
        print(f"{self.period}_max_consec_losses: {self.max_consec_losses}")
        print(f"{self.period}_exposure_pct: {self.exposure_pct:.2f}")


def run_backtest(df: pd.DataFrame, period: str = "test") -> BacktestResult:
    """
    Run strategy on data and return metrics.

    The strategy module must define:
        generate_signals(df: pd.DataFrame) -> pd.Series
            Returns signal per bar: +1 (long), -1 (short), 0 (flat).
    """
    # Import strategy fresh each time (agent modifies it between runs)
    if "strategy" in sys.modules:
        del sys.modules["strategy"]
    import strategy

    df = add_session_markers(df)

    # Generate signals
    signals = strategy.generate_signals(df)
    signals = signals.reindex(df.index).fillna(0).astype(int)
    signals = signals.clip(-1, 1)

    # Force flat on last bar of each day (day-trade rule)
    day_last_bar = df.groupby("date").tail(1).index
    signals.loc[day_last_bar] = 0

    # Force flat on first bar of each day (no overnight carry)
    day_first_bar = df.groupby("date").head(1).index
    # If signal is nonzero on first bar, that's an entry (fine).
    # But we must ensure we start flat each day.

    # ── Simulate trades ──────────────────────────────────────────────────
    position = 0  # current position: +1, -1, or 0
    trades = []   # list of completed trade P&Ls (in BRL)
    entry_price = 0.0
    entry_bar = None

    for i in range(len(df)):
        signal = signals.iloc[i]
        # FIX: Use Open price for fills (signal was generated on previous bar,
        # so execution happens at this bar's open, not close)
        fill_price = df["Open"].iloc[i]
        close_price = df["Close"].iloc[i]
        bar_date = df["date"].iloc[i]

        # Check if new day — force close any open position
        if i > 0 and df["date"].iloc[i] != df["date"].iloc[i - 1] and position != 0:
            pnl = (fill_price - entry_price) * position * POINT_VALUE * CONTRACTS
            pnl -= TOTAL_COST_RT * CONTRACTS
            trades.append(pnl)
            position = 0

        # Process signal
        if signal != position:
            # Close existing position
            if position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE * CONTRACTS
                pnl -= TOTAL_COST_RT * CONTRACTS
                trades.append(pnl)

            # Open new position
            if signal != 0:
                entry_price = fill_price
                entry_bar = i

            position = signal

    # Close any remaining position at last bar
    if position != 0:
        pnl = (df["Close"].iloc[-1] - entry_price) * position * POINT_VALUE * CONTRACTS
        pnl -= TOTAL_COST_RT * CONTRACTS
        trades.append(pnl)

    # ── Calculate metrics ────────────────────────────────────────────────
    trades_arr = np.array(trades) if trades else np.array([0.0])
    total_trades = len(trades)

    if total_trades == 0:
        return BacktestResult(
            sharpe=0.0, profit_factor=0.0, max_drawdown_pct=0.0,
            win_rate=0.0, total_trades=0, net_profit_brl=0.0,
            avg_profit_per_trade=0.0, avg_win_brl=0.0, avg_loss_brl=0.0,
            max_consec_losses=0, exposure_pct=0.0, period=period,
        )

    wins = trades_arr[trades_arr > 0]
    losses = trades_arr[trades_arr < 0]

    net_profit = trades_arr.sum()
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    avg_win = wins.mean() if len(wins) > 0 else 0.0
    avg_loss = losses.mean() if len(losses) > 0 else 0.0
    gross_profit = wins.sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 1e-9
    profit_factor = gross_profit / gross_loss

    # Sharpe: annualized from per-trade returns
    if total_trades > 1 and trades_arr.std(ddof=1) > 0:
        # Estimate trades per year: total_trades / years_of_data * annualization
        trading_days = df.index.normalize().nunique()
        trades_per_day = total_trades / max(trading_days, 1)
        trades_per_year = trades_per_day * 252
        sharpe = (trades_arr.mean() / trades_arr.std(ddof=1)) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0

    # Max drawdown (% of peak equity)
    initial_equity = 100_000.0
    equity = initial_equity + np.concatenate([[0], np.cumsum(trades_arr)])
    peak_equity = np.maximum.accumulate(equity)
    dd_pct = (peak_equity - equity) / peak_equity * 100
    max_dd_pct = dd_pct.max()

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades_arr:
        if t < 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    # Exposure: % of bars with a position
    position_bars = (signals != 0).sum()
    exposure_pct = (position_bars / len(df)) * 100

    return BacktestResult(
        sharpe=round(sharpe, 4),
        profit_factor=round(profit_factor, 4),
        max_drawdown_pct=round(max_dd_pct, 2),
        win_rate=round(win_rate, 4),
        total_trades=total_trades,
        net_profit_brl=round(net_profit, 2),
        avg_profit_per_trade=round(net_profit / total_trades, 2),
        avg_win_brl=round(avg_win, 2),
        avg_loss_brl=round(avg_loss, 2),
        max_consec_losses=max_consec,
        exposure_pct=round(exposure_pct, 2),
        period=period,
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run WDO backtest")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Bar timeframe")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Train/test split ratio")
    args = parser.parse_args()

    # Load data
    df = load_data(timeframe=args.timeframe)

    # Split
    train_df, test_df = split_data(df, train_ratio=args.train_ratio)

    # Run on both splits
    print("\n" + "=" * 60)
    print("TRAIN PERIOD")
    print("=" * 60)
    train_result = run_backtest(train_df, period="train")
    train_result.print_metrics()

    print("\n" + "=" * 60)
    print("TEST PERIOD (out-of-sample)")
    print("=" * 60)
    test_result = run_backtest(test_df, period="test")
    test_result.print_metrics()

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"primary_metric: {test_result.sharpe}")
    print(f"sufficient_trades: {'yes' if test_result.total_trades >= MIN_TRADES else 'no'}")

    # Overfitting check
    if train_result.sharpe > 0 and test_result.sharpe > 0:
        degradation = 1 - (test_result.sharpe / train_result.sharpe)
        print(f"train_test_degradation: {degradation:.2%}")
    else:
        print("train_test_degradation: N/A")

    print("status: ok")


if __name__ == "__main__":
    main()
