"""
test_promising_custom.py — Focus on most promising custom indicators.
Hurst (relaxed), Supertrend, Connors RSI, Chandelier Exit.
All tested on top of current best (skip12+13h, TRIX exit, test=2.98).
"""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from ..sweep_params import fast_backtest


def rolling_hurst(close, window=100):
    """Hurst exponent via R/S analysis. >0.5=trending."""
    def hurst_rs(series):
        ts = np.array(series)
        returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10: return 0.5
        mean_r = returns.mean()
        deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min()
        s = returns.std(ddof=1)
        if s == 0 or r == 0: return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def supertrend(high, low, close, period=10, multiplier=3.0):
    """Supertrend: direction (+1/-1) and stop level."""
    atr = ta.volatility.average_true_range(high, low, close, window=period)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    direction = np.ones(len(close))
    st_line = np.zeros(len(close))
    final_upper = upper_band.values.copy()
    final_lower = lower_band.values.copy()

    for i in range(1, len(close)):
        if np.isnan(final_upper[i]) or np.isnan(final_lower[i]):
            direction[i] = direction[i-1]
            st_line[i] = st_line[i-1]
            continue

        # Adjust bands
        if final_lower[i] < final_lower[i-1] and close.iloc[i-1] > final_lower[i-1]:
            final_lower[i] = final_lower[i-1]
        if final_upper[i] > final_upper[i-1] and close.iloc[i-1] < final_upper[i-1]:
            final_upper[i] = final_upper[i-1]

        # Direction
        if direction[i-1] == 1:  # was uptrend
            if close.iloc[i] < final_lower[i]:
                direction[i] = -1
                st_line[i] = final_upper[i]
            else:
                direction[i] = 1
                st_line[i] = final_lower[i]
        else:  # was downtrend
            if close.iloc[i] > final_upper[i]:
                direction[i] = 1
                st_line[i] = final_lower[i]
            else:
                direction[i] = -1
                st_line[i] = final_upper[i]

    return pd.Series(direction, index=close.index), pd.Series(st_line, index=close.index)


def connors_rsi(close, rsi_period=3, streak_period=2, roc_period=100):
    """Connors RSI: combines RSI(3) + streak RSI + ROC percentile rank."""
    # Component 1: Regular RSI
    rsi = ta.momentum.rsi(close, window=rsi_period)

    # Component 2: Streak RSI (RSI of consecutive up/down streak length)
    streak = pd.Series(0.0, index=close.index)
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i-1]:
            streak.iloc[i] = max(streak.iloc[i-1], 0) + 1
        elif close.iloc[i] < close.iloc[i-1]:
            streak.iloc[i] = min(streak.iloc[i-1], 0) - 1
        else:
            streak.iloc[i] = 0
    streak_rsi = ta.momentum.rsi(streak, window=streak_period)

    # Component 3: Percentile rank of ROC
    roc = close.pct_change(1)
    pct_rank = roc.rolling(roc_period).apply(lambda x: (x < x.iloc[-1]).sum() / len(x) * 100, raw=False)

    # Connors RSI = average of three components
    crsi = (rsi + streak_rsi + pct_rank) / 3
    return crsi


def chandelier_exit(high, low, close, period=22, multiplier=3.0):
    """Chandelier Exit: ATR from highest high (long) / lowest low (short)."""
    atr = ta.volatility.average_true_range(high, low, close, window=period)
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    long_stop = highest - multiplier * atr
    short_stop = lowest + multiplier * atr
    return long_stop, short_stop


def gen(df, variant="baseline"):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix15 = ta.trend.trix(df["Close"], window=15)

    extras = {}
    if "hurst" in variant:
        extras["hurst"] = rolling_hurst(df["Close"], window=100).values
    if "supertrend" in variant:
        for p, m in [(7, 2.0), (10, 3.0), (7, 3.0)]:
            d, s = supertrend(df["High"], df["Low"], df["Close"], period=p, multiplier=m)
            extras[f"st_dir_{p}_{m}"] = d.values
            extras[f"st_line_{p}_{m}"] = s.values
    if "crsi" in variant:
        extras["crsi"] = connors_rsi(df["Close"]).values
    if "chand" in variant:
        ls, ss = chandelier_exit(df["High"], df["Low"], df["Close"])
        extras["chand_long"] = ls.values
        extras["chand_short"] = ss.values

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = ema200.values; av = adx14.values; at_ = atr20.values
    trix_v = trix15.values
    valid_trix = trix_v[~np.isnan(trix_v)]
    trix_med = float(np.median(valid_trix)) if len(valid_trix) > 0 else 0.0
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date: pos = 0; prev_date = d; continue
        if is_last[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        # EXIT
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            fv = trix_v[i] if not np.isnan(trix_v[i]) else trix_med
            fv_prev = trix_v[i-1] if i > 0 and not np.isnan(trix_v[i-1]) else trix_med
            trix_exit = False
            if pos == 1 and fv < trix_med and fv_prev >= trix_med: trix_exit = True
            elif pos == -1 and fv > trix_med and fv_prev <= trix_med: trix_exit = True

            # Chandelier exit variant
            chand_exit = False
            if "chand_exit" in variant:
                cl = extras["chand_long"][i] if not np.isnan(extras["chand_long"][i]) else 0
                cs = extras["chand_short"][i] if not np.isnan(extras["chand_short"][i]) else 1e9
                if pos == 1 and close[i] < cl: chand_exit = True
                elif pos == -1 and close[i] > cs: chand_exit = True

            # Supertrend exit variant
            st_exit = False
            if "supertrend_exit" in variant:
                key = "st_dir_7_2.0" if "7_2" in variant else "st_dir_10_3.0"
                sd = extras.get(key, np.zeros(len(df)))
                if pos == 1 and sd[i] == -1 and (i == 0 or sd[i-1] == 1): st_exit = True
                elif pos == -1 and sd[i] == 1 and (i == 0 or sd[i-1] == -1): st_exit = True

            if trix_exit or chand_exit or st_exit: sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if cur_atr > 0 and close[i] < peak - 2 * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if cur_atr > 0 and close[i] > peak + 2 * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        # ENTRY FILTERS
        cur_time = times[i]
        if hasattr(cur_time, 'hour') and cur_time.hour in (12, 13): prev_date = d; continue
        if av[i] < 20 or br[i] <= 36: prev_date = d; continue

        # Hurst regime filter
        if "hurst" in variant:
            hv = extras["hurst"][i]
            thresh = 0.50 if "hurst50" in variant else (0.52 if "hurst52" in variant else 0.55)
            if not np.isnan(hv) and hv < thresh: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50

        # Connors RSI as momentum (replace or supplement RSI7)
        if "crsi_replace" in variant:
            cr = extras["crsi"][i] if not np.isnan(extras["crsi"][i]) else 50
            long_mom = cr > 70
            short_mom = cr < 30
        elif "crsi_confirm" in variant:
            cr = extras["crsi"][i] if not np.isnan(extras["crsi"][i]) else 50
            long_mom = r > 65 and cr > 50
            short_mom = r < 45 and cr < 50
        else:
            long_mom = r > 65
            short_mom = r < 45

        # Supertrend as entry confirmation
        if "supertrend_confirm" in variant:
            key = "st_dir_7_2.0" if "7_2" in variant else "st_dir_10_3.0"
            sd = extras.get(key, np.zeros(len(df)))
            st_long = sd[i] == 1
            st_short = sd[i] == -1
        else:
            st_long = True; st_short = True

        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            if cross_up and close[i] > tv[i] and long_mom and st_long:
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < tv[i] and short_mom and st_short:
                sig[i] = -1; pos = -1; peak = close[i]
        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    experiments = [
        ("BASELINE (2.98)", "baseline"),
        # Hurst as regime filter (relaxed thresholds)
        ("Hurst > 0.50 filter", "hurst50_hurst"),
        ("Hurst > 0.52 filter", "hurst52_hurst"),
        ("Hurst > 0.55 filter", "hurst_hurst"),
        # Supertrend as entry confirmation
        ("Supertrend(7,2) confirm", "supertrend_confirm_7_2_supertrend"),
        ("Supertrend(10,3) confirm", "supertrend_confirm_10_3_supertrend"),
        # Supertrend as additional exit
        ("Supertrend(7,2) exit", "supertrend_exit_7_2_supertrend"),
        ("Supertrend(10,3) exit", "supertrend_exit_10_3_supertrend"),
        # Connors RSI
        ("ConnorsRSI replace RSI7", "crsi_replace_crsi"),
        ("ConnorsRSI confirm", "crsi_confirm_crsi"),
        # Chandelier Exit
        ("Chandelier Exit added", "chand_exit_chand"),
        # Combos
        ("Hurst50 + ST(7,2) confirm", "hurst50_hurst_supertrend_confirm_7_2_supertrend"),
        ("Hurst50 + ConnorsRSI", "hurst50_hurst_crsi_confirm_crsi"),
    ]

    print(f"{'Experiment':<30} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8}")
    print("-" * 80)
    for name, variant in experiments:
        try:
            sig_tr = gen(train_df, variant=variant)
            sig_te = gen(test_df, variant=variant)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            beat = "***" if te[0] > 2.9838 and tr[0] > 0 and te[3] >= 50 else ""
            print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>6} {te[4]:>8.0f}  [{both}] {beat}")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")


if __name__ == "__main__":
    main()
