"""
strategy_orb.py — Opening Range Breakout strategy for WDO.
Completely different approach from EMA crossover.

Concept: measure price range of first N minutes. Trade breakout.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import add_session_markers


def generate_signals(df: pd.DataFrame, opening_minutes=30,
                     use_atr_filter=True, atr_window=20, atr_mult=2.0,
                     use_adx=True, adx_thresh=20,
                     use_trix_exit=True, trix_window=12,
                     min_range_atr=0.3, max_range_atr=3.0) -> pd.Series:
    """
    Opening Range Breakout (ORB).

    1. Compute high/low of first `opening_minutes` minutes
    2. After opening period, if close > opening_high -> long
    3. If close < opening_low -> short
    4. Exit: TRIX + ATR trailing stop
    """
    opening_bars = opening_minutes // 5  # M5 bars

    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14) if use_adx else None
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=atr_window)
    trix = ta.trend.trix(df["Close"], window=trix_window) if use_trix_exit else None

    close = df["Close"].values
    high = df["High"].values
    low = df["Low"].values
    adx_v = adx.values if adx is not None else np.zeros(len(df))
    atr_v = atr.values
    trix_v = trix.values if trix is not None else np.zeros(len(df))
    if use_trix_exit:
        trix_med_s = trix.rolling(500, min_periods=100).median().shift(1)
        tmv = trix_med_s.values
    else:
        tmv = np.zeros(len(df))

    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    bar_of_day = df["bar_of_day"].values
    dates = df["date"].values
    times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None
    peak = 0.0
    or_high = 0.0
    or_low = 1e9
    or_complete = False
    traded_today = False

    for i in range(len(df)):
        d = dates[i]

        # New day
        if is_first[i] or d != prev_date:
            pos = 0
            prev_date = d
            or_high = high[i]
            or_low = low[i]
            or_complete = False
            traded_today = False
            continue

        if is_last[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue

        # Build opening range
        if bar_of_day[i] < opening_bars:
            or_high = max(or_high, high[i])
            or_low = min(or_low, low[i])
            sig[i] = pos
            prev_date = d
            continue

        # Mark opening range complete
        if not or_complete:
            or_complete = True

        # Check indicator validity
        if np.isnan(atr_v[i]):
            sig[i] = pos; prev_date = d; continue

        # EXIT
        if pos != 0:
            ca = atr_v[i] if not np.isnan(atr_v[i]) else 0

            # TRIX exit
            trix_exit = False
            if use_trix_exit and not np.isnan(trix_v[i]) and i > 0 and not np.isnan(trix_v[i-1]):
                tm = tmv[i] if not np.isnan(tmv[i]) else 0
                fv = trix_v[i]; fp = trix_v[i-1]
                if pos == 1 and fv < tm and fp >= tm: trix_exit = True
                elif pos == -1 and fv > tm and fp <= tm: trix_exit = True

            if trix_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if ca > 0 and close[i] < peak - atr_mult * ca:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if ca > 0 and close[i] > peak + atr_mult * ca:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            prev_date = d; continue

        # ENTRY FILTERS
        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour in (12, 13): prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue

        if use_adx and adx_v[i] < adx_thresh: prev_date = d; continue

        # Only one breakout trade per day
        if traded_today: prev_date = d; continue

        # Range size filter: not too small (noise) or too large (already moved)
        or_range = or_high - or_low
        cur_atr = atr_v[i] if not np.isnan(atr_v[i]) else 1
        if cur_atr > 0:
            range_ratio = or_range / cur_atr
            if range_ratio < min_range_atr or range_ratio > max_range_atr:
                prev_date = d; continue

        # BREAKOUT ENTRY
        if close[i] > or_high:
            sig[i] = 1; pos = 1; peak = close[i]; traded_today = True
        elif close[i] < or_low:
            sig[i] = -1; pos = -1; peak = close[i]; traded_today = True

        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals
