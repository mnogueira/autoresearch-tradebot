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


def _rolling_hurst(close, window=100):
    """Hurst exponent via R/S analysis. >0.5=trending, <0.5=mean-reverting."""
    def hurst_rs(series):
        ts = np.array(series)
        returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10:
            return 0.5
        mean_r = returns.mean()
        deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min()
        s = returns.std(ddof=1)
        if s == 0 or r == 0:
            return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    EMA(8/34) crossover + EMA(200) trend + ADX(14)>20 + RSI(7)>65/<45.
    ATR(20)x2 trailing stop + TRIX(15) median crossover exit.
    Skip 12h+13h. Hurst(100) > 0.50 regime filter.

    Hurst exponent filters out ranging/mean-reverting regimes where
    trend-following generates false signals.
    """
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix = ta.trend.trix(df["Close"], window=15)
    hurst = _rolling_hurst(df["Close"], window=100)

    close = df["Close"].values
    e8 = ema8.values
    e34 = ema34.values
    rsi_v = rsi7.values
    tv = ema200.values
    adx_v = adx.values
    atr_v = atr.values
    trix_v = trix.values
    hurst_v = hurst.values
    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values
    dates = df["date"].values
    dates_time = df["time"].values

    # Rolling TRIX median — NO lookahead (past 500 bars, shifted to exclude current)
    trix_rolling_med = trix.rolling(window=500, min_periods=100).median().shift(1)
    trix_med_v = trix_rolling_med.values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None
    peak = 0.0

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

        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(adx_v[i]) or np.isnan(atr_v[i]):
            sig[i] = pos
            prev_date = d
            continue

        # Exit: ATR(20) trailing stop OR TRIX median crossover
        if pos != 0:
            cur_atr = atr_v[i] if not np.isnan(atr_v[i]) else 0
            trix_exit = False
            tm = trix_med_v[i] if not np.isnan(trix_med_v[i]) else 0.0
            fv = trix_v[i] if not np.isnan(trix_v[i]) else tm
            fv_prev = trix_v[i-1] if i > 0 and not np.isnan(trix_v[i-1]) else tm
            if pos == 1 and fv < tm and fv_prev >= tm:
                trix_exit = True
            elif pos == -1 and fv > tm and fv_prev <= tm:
                trix_exit = True

            if trix_exit:
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
        if hasattr(cur_time, 'hour') and cur_time.hour in (12, 13):
            prev_date = d
            continue
        # Time-based cutoff: no entries after 14:55 (replaces bars_remaining lookahead)
        if hasattr(cur_time, 'hour') and (cur_time.hour > 14 or (cur_time.hour == 14 and cur_time.minute >= 55)):
            prev_date = d
            continue
        if adx_v[i] < 20:
            prev_date = d
            continue

        # Hurst regime filter: only trade in trending regimes
        hv = hurst_v[i]
        if not np.isnan(hv) and hv < 0.50:
            prev_date = d
            continue

        # EMA(8/34) crossover + EMA(200) trend + RSI(7) momentum
        r = rsi_v[i] if not np.isnan(rsi_v[i]) else 50
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]

            if cross_up and close[i] > tv[i] and r > 65:
                sig[i] = 1
                pos = 1
                peak = close[i]
            elif cross_dn and close[i] < tv[i] and r < 45:
                sig[i] = -1
                pos = -1
                peak = close[i]

        prev_date = d

    # 1-bar delay WITHIN each day
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals
