"""
test_schaff_didi.py — Test Schaff Trend Cycle (STC) and DIDI Index.
STC = MACD + Stochastic cycle detection. DIDI = 3 MA relative distances.
"""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers
from ..sweep_params import fast_backtest


def schaff_trend_cycle(close, fast=23, slow=50, cycle=10):
    """Manual Schaff Trend Cycle implementation."""
    macd = ta.trend.ema_indicator(close, window=fast) - ta.trend.ema_indicator(close, window=slow)

    # First Stochastic of MACD
    lowest_macd = macd.rolling(cycle).min()
    highest_macd = macd.rolling(cycle).max()
    denom = highest_macd - lowest_macd
    denom = denom.replace(0, np.nan)
    stoch1 = ((macd - lowest_macd) / denom) * 100
    # EMA smooth
    pf = ta.trend.ema_indicator(stoch1, window=cycle)

    # Second Stochastic
    lowest_pf = pf.rolling(cycle).min()
    highest_pf = pf.rolling(cycle).max()
    denom2 = highest_pf - lowest_pf
    denom2 = denom2.replace(0, np.nan)
    stoch2 = ((pf - lowest_pf) / denom2) * 100
    stc = ta.trend.ema_indicator(stoch2, window=cycle)

    return stc


def didi_index(close, fast=3, medium=8, slow=20):
    """DIDI Index: fast/medium MA ratio and slow/medium MA ratio."""
    ma_fast = close.rolling(fast).mean()
    ma_medium = close.rolling(medium).mean()
    ma_slow = close.rolling(slow).mean()

    didi_fast = (ma_fast / ma_medium - 1) * 100
    didi_slow = (ma_slow / ma_medium - 1) * 100
    return didi_fast, didi_slow


def gen(df, variant="baseline"):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    trend = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx_val = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    # STC
    stc = schaff_trend_cycle(df["Close"])
    stc_v = stc.values

    # DIDI
    didi_f, didi_s = didi_index(df["Close"])
    didi_fv = didi_f.values
    didi_sv = didi_s.values

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = trend.values; av = adx_val.values; at_ = atr.values
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date:
            pos = 0; prev_date = d; continue
        if is_last[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        # Exit (always same)
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            ema_exit = False
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]: ema_exit = True
                elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]: ema_exit = True
            if ema_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if cur_atr > 0 and close[i] < peak - 2 * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if cur_atr > 0 and close[i] > peak + 2 * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        cur_time = times[i]
        if hasattr(cur_time, 'hour') and cur_time.hour == 13: prev_date = d; continue
        if br[i] <= 36: prev_date = d; continue

        if variant == "stc_entry":
            # STC as primary entry: cross above 25 = buy, cross below 75 = sell
            if i > 0 and not np.isnan(stc_v[i]) and not np.isnan(stc_v[i-1]):
                if stc_v[i] > 25 and stc_v[i-1] <= 25 and close[i] > tv[i]:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif stc_v[i] < 75 and stc_v[i-1] >= 75 and close[i] < tv[i]:
                    sig[i] = -1; pos = -1; peak = close[i]

        elif variant == "stc_confirm":
            # EMA crossover + STC confirmation
            if av[i] < 20: prev_date = d; continue
            r = rv[i] if not np.isnan(rv[i]) else 50
            sc = stc_v[i] if not np.isnan(stc_v[i]) else 50
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                if cross_up and close[i] > tv[i] and r > 65 and sc > 25:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < tv[i] and r < 45 and sc < 75:
                    sig[i] = -1; pos = -1; peak = close[i]

        elif variant == "stc_replace_rsi":
            # Replace RSI with STC
            if av[i] < 20: prev_date = d; continue
            sc = stc_v[i] if not np.isnan(stc_v[i]) else 50
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                if cross_up and close[i] > tv[i] and sc > 75:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < tv[i] and sc < 25:
                    sig[i] = -1; pos = -1; peak = close[i]

        elif variant == "didi_entry":
            # DIDI crossover: fast crosses above slow = bullish
            if i > 0 and not np.isnan(didi_fv[i]) and not np.isnan(didi_sv[i]):
                if not np.isnan(didi_fv[i-1]) and not np.isnan(didi_sv[i-1]):
                    didi_cross_up = didi_fv[i] > didi_sv[i] and didi_fv[i-1] <= didi_sv[i-1]
                    didi_cross_dn = didi_fv[i] < didi_sv[i] and didi_fv[i-1] >= didi_sv[i-1]
                    if didi_cross_up and close[i] > tv[i]:
                        sig[i] = 1; pos = 1; peak = close[i]
                    elif didi_cross_dn and close[i] < tv[i]:
                        sig[i] = -1; pos = -1; peak = close[i]

        elif variant == "didi_confirm":
            # EMA crossover + DIDI confirmation (fast > slow = trend confirmed)
            if av[i] < 20: prev_date = d; continue
            r = rv[i] if not np.isnan(rv[i]) else 50
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                df_ok = not np.isnan(didi_fv[i]) and not np.isnan(didi_sv[i])
                if cross_up and close[i] > tv[i] and r > 65 and df_ok and didi_fv[i] > didi_sv[i]:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < tv[i] and r < 45 and df_ok and didi_fv[i] < didi_sv[i]:
                    sig[i] = -1; pos = -1; peak = close[i]

        else:
            # Baseline
            if av[i] < 20: prev_date = d; continue
            r = rv[i] if not np.isnan(rv[i]) else 50
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                if cross_up and close[i] > tv[i] and r > 65:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < tv[i] and r < 45:
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

    variants = [
        "baseline",
        "stc_entry",
        "stc_confirm",
        "stc_replace_rsi",
        "didi_entry",
        "didi_confirm",
    ]

    print(f"{'Variant':<20} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8}")
    print("-" * 65)
    for v in variants:
        try:
            sig_tr = gen(train_df, variant=v)
            sig_te = gen(test_df, variant=v)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            print(f"  {v:<18} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>6} {te[4]:>8.0f}  [{both}]")
        except Exception as e:
            print(f"  {v:<18} ERROR: {e}")


if __name__ == "__main__":
    main()
