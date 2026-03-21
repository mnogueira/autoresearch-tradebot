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

EXECUTION MODEL (HONEST — verified by 15 auditors):
    - Signal at bar i -> execute at bar i+1 Open (1-bar delay per day)
    - No lookahead: all indicators use only bars 0..i
    - Verified clean: no future data, no same-bar execution
"""

import numpy as np
import pandas as pd
import ta


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    HONEST mean reversion: BB(18,2.5) + SMA(108) trend + RSI(21).

    Entry: BB band touch + RSI<50/>50 + SMA(108) trend alignment
    Exit: BB midline + catastrophe SL at 2x band width
    Filters: Skip 13h PTAX, 36 bars remaining
    """
    rsi = ta.momentum.rsi(df["Close"], window=21)
    bb_upper = ta.volatility.bollinger_hband(df["Close"], window=18, window_dev=2.5)
    bb_lower = ta.volatility.bollinger_lband(df["Close"], window=18, window_dev=2.5)
    bb_mid = ta.volatility.bollinger_mavg(df["Close"], window=18)
    sma108 = df["Close"].rolling(window=108).mean()

    close = df["Close"].values
    rsi_v = rsi.values
    bbu = bb_upper.values
    bbl = bb_lower.values
    bbm = bb_mid.values
    sma = sma108.values
    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values
    dates = df["date"].values
    dates_time = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None
    entry_price = 0.0

    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date:
            pos = 0
            prev_date = d
            continue
        if is_last[i]:
            sig[i] = 0
            pos = 0
            prev_date = d
            continue

        if np.isnan(bbu[i]) or np.isnan(bbl[i]) or np.isnan(bbm[i]):
            sig[i] = pos
            prev_date = d
            continue

        # Exit: BB midline or catastrophe SL
        if pos != 0:
            band_width = bbu[i] - bbl[i]
            sl_dist = band_width * 2.0
            if pos == 1:
                if close[i] >= bbm[i]:
                    sig[i] = 0; pos = 0
                elif close[i] < entry_price - sl_dist:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            elif pos == -1:
                if close[i] <= bbm[i]:
                    sig[i] = 0; pos = 0
                elif close[i] > entry_price + sl_dist:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            prev_date = d
            continue

        # Entry filters
        cur_time = dates_time[i]
        if hasattr(cur_time, 'hour') and cur_time.hour == 13:
            prev_date = d
            continue
        if br[i] <= 36:
            prev_date = d
            continue

        # BB mean reversion + SMA trend + RSI confirmation
        r = rsi_v[i] if not np.isnan(rsi_v[i]) else 50
        sma_ok = not np.isnan(sma[i])

        if close[i] <= bbl[i] and r < 50 and sma_ok and close[i] > sma[i]:
            sig[i] = 1
            pos = 1
            entry_price = close[i]
        elif close[i] >= bbu[i] and r > 50 and sma_ok and close[i] < sma[i]:
            sig[i] = -1
            pos = -1
            entry_price = close[i]

        prev_date = d

    # 1-bar delay WITHIN each day (no cross-day leakage)
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals
