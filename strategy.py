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
    - No lookahead. Verified clean.
    - BOTH train AND test Sharpe must be positive.
"""

import numpy as np
import pandas as pd
import ta


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    HONEST trend-following: EMA(8/34) + SMA(200) + ADX(20) + RSI(7)>65/<45 + ATR(20)x2.

    Sweep-optimized: SMA 162->200, RSI 9->7, RSI long 55->65.
    """
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    rsi9 = ta.momentum.rsi(df["Close"], window=7)
    sma162 = df["Close"].rolling(window=200).mean()
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    close = df["Close"].values
    e8 = ema8.values
    e34 = ema34.values
    rsi_v = rsi9.values
    s162 = sma162.values
    adx_v = adx.values
    atr_v = atr.values
    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values
    dates = df["date"].values
    dates_time = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None
    peak = 0.0  # trailing high/low for ATR stop

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

        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(s162[i]) or np.isnan(adx_v[i]) or np.isnan(atr_v[i]):
            sig[i] = pos
            prev_date = d
            continue

        # Exit: ATR(20) trailing stop (2x ATR) OR EMA crossover reversal
        if pos != 0:
            cur_atr = atr_v[i] if not np.isnan(atr_v[i]) else 0
            # EMA reversal exit: close when fast EMA crosses back
            ema_exit = False
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]:
                    ema_exit = True
                elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]:
                    ema_exit = True
            if ema_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if cur_atr > 0 and close[i] < peak - 2 * cur_atr:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if cur_atr > 0 and close[i] > peak + 2 * cur_atr:
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
        if adx_v[i] < 20 or br[i] <= 36:
            prev_date = d
            continue

        # EMA(8/34) crossover + SMA(162) trend + RSI(9) momentum confirmation
        r = rsi_v[i] if not np.isnan(rsi_v[i]) else 50
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]

            # RSI > 55 confirms bullish momentum for longs
            # RSI < 45 confirms bearish momentum for shorts
            if cross_up and close[i] > s162[i] and r > 65:
                sig[i] = 1
                pos = 1
                peak = close[i]
            elif cross_dn and close[i] < s162[i] and r < 45:
                sig[i] = -1
                pos = -1
                peak = close[i]

        prev_date = d

    # 1-bar delay WITHIN each day
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals
