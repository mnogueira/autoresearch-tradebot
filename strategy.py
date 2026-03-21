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
    HONEST trend-following v2: EMA crossover + SMA(162) + ADX + HiLo exit.

    Simplified: removed H1 trend (too stale with prev-bar fix).
    No external data (VIX/momentum were using lookahead — removed).
    Pure price-based, no lookahead, 1-bar delayed execution.
    """
    ema9 = ta.trend.ema_indicator(df["Close"], window=9)
    ema21 = ta.trend.ema_indicator(df["Close"], window=21)
    hilo_high = df["High"].rolling(window=13).mean()
    hilo_low = df["Low"].rolling(window=13).mean()
    sma162 = df["Close"].rolling(window=162).mean()
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)

    close = df["Close"].values
    e9 = ema9.values
    e21 = ema21.values
    hh = hilo_high.values
    hl = hilo_low.values
    s162 = sma162.values
    adx_v = adx.values
    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values
    dates = df["date"].values
    dates_time = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None

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

        if np.isnan(e9[i]) or np.isnan(e21[i]) or np.isnan(hh[i]) or np.isnan(s162[i]) or np.isnan(adx_v[i]):
            sig[i] = pos
            prev_date = d
            continue

        # Exit: HiLo Activator
        if pos != 0:
            if pos == 1 and close[i] < hl[i]:
                sig[i] = 0
                pos = 0
            elif pos == -1 and close[i] > hh[i]:
                sig[i] = 0
                pos = 0
            else:
                sig[i] = pos
            prev_date = d
            continue

        # Entry filters: skip 13h PTAX + ADX > 20 + 36 bars remaining
        cur_time = dates_time[i]
        if hasattr(cur_time, 'hour') and cur_time.hour == 13:
            prev_date = d
            continue
        if adx_v[i] < 20 or br[i] <= 36:
            prev_date = d
            continue

        # EMA crossover + SMA trend alignment
        if i > 0 and not np.isnan(e9[i-1]) and not np.isnan(e21[i-1]):
            cross_up = e9[i] > e21[i] and e9[i-1] <= e21[i-1]
            cross_dn = e9[i] < e21[i] and e9[i-1] >= e21[i-1]

            if cross_up and close[i] > s162[i]:
                sig[i] = 1
                pos = 1
            elif cross_dn and close[i] < s162[i]:
                sig[i] = -1
                pos = -1

        prev_date = d

    # 1-bar delay WITHIN each day (no cross-day leakage)
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals
