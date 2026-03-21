"""
strategy.py — Trading strategy for WDO day trading.
AGENT-EDITABLE: The AI agent modifies this file each experiment.

Must define:
    generate_signals(df: pd.DataFrame) -> pd.Series
        Input:  DataFrame with columns Open, High, Low, Close, Volume, Spread,
                plus session markers: date, time, bar_of_day, is_first_bar,
                bars_remaining, is_last_30min
        Output: Series indexed like df with values in {-1, 0, +1}
                +1 = long, -1 = short, 0 = flat

Rules:
    - Only use libraries already in pyproject.toml (pandas, numpy, ta)
    - Do not add new dependencies
    - Signal must be deterministic (no random)
    - Strategy runs on 5-minute bars by default
    - Keep it simple: complexity must be justified by improvement
"""

import numpy as np
import pandas as pd
import ta


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    Baseline strategy: EMA crossover with RSI filter.

    - Go long when EMA(9) crosses above EMA(21) and RSI(14) < 70
    - Go short when EMA(9) crosses below EMA(21) and RSI(14) > 30
    - Flatten in the last 30 minutes of the session
    """
    signals = pd.Series(0, index=df.index)

    # Indicators
    ema_fast = ta.trend.ema_indicator(df["Close"], window=9)
    ema_slow = ta.trend.ema_indicator(df["Close"], window=21)
    rsi = ta.momentum.rsi(df["Close"], window=14)

    # Crossover detection
    ema_diff = ema_fast - ema_slow
    ema_diff_prev = ema_diff.shift(1)

    cross_up = (ema_diff > 0) & (ema_diff_prev <= 0)
    cross_down = (ema_diff < 0) & (ema_diff_prev >= 0)

    # Generate signals with RSI filter
    signals[cross_up & (rsi < 70)] = 1
    signals[cross_down & (rsi > 30)] = -1

    # Forward-fill signals (hold position until opposite signal)
    position = 0
    for i in range(len(signals)):
        if signals.iloc[i] != 0:
            position = signals.iloc[i]
        else:
            signals.iloc[i] = position

        # Force flat in last 30 min
        if df["is_last_30min"].iloc[i]:
            signals.iloc[i] = 0
            position = 0

        # Force flat on first bar (start fresh each day)
        if df["is_first_bar"].iloc[i]:
            position = 0
            if signals.iloc[i] == 0:
                pass  # already flat

    return signals
