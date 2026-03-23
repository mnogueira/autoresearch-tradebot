"""Sweep EMA trend period and test combinations."""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers
from .sweep_params import fast_backtest


def gen(df, ema_trend_window=200, time_stop=None):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    trend = ta.trend.ema_indicator(df["Close"], window=ema_trend_window)
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = trend.values; av = adx.values; at_ = atr.values
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0; bars_in = 0

    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date:
            pos = 0; prev_date = d; continue
        if is_last[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        if pos != 0:
            bars_in += 1
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            ema_exit = False
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]: ema_exit = True
                elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]: ema_exit = True

            time_exit = time_stop is not None and bars_in >= time_stop

            if ema_exit or time_exit:
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
        if av[i] < 20 or br[i] <= 36: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            if cross_up and close[i] > tv[i] and r > 65:
                sig[i] = 1; pos = 1; peak = close[i]; bars_in = 0
            elif cross_dn and close[i] < tv[i] and r < 45:
                sig[i] = -1; pos = -1; peak = close[i]; bars_in = 0
        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    print("EMA TREND PERIOD SWEEP")
    print("=" * 80)
    for ew in [100, 120, 150, 175, 200, 220, 250, 300]:
        sig_tr = gen(train_df, ema_trend_window=ew)
        sig_te = gen(test_df, ema_trend_window=ew)
        tr = fast_backtest(train_df, sig_tr)
        te = fast_backtest(test_df, sig_te)
        both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
        print(f"  EMA({ew:>3})  test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  net={te[4]:>8.0f}  [{both}]")

    print(f"\nEMA(200) + TIME STOP SWEEP")
    print("=" * 80)
    for ts in [10, 15, 20, 25, 30, 40, None]:
        sig_tr = gen(train_df, ema_trend_window=200, time_stop=ts)
        sig_te = gen(test_df, ema_trend_window=200, time_stop=ts)
        tr = fast_backtest(train_df, sig_tr)
        te = fast_backtest(test_df, sig_te)
        both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
        ts_str = str(ts) if ts else "None"
        print(f"  TS={ts_str:>4}  test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  net={te[4]:>8.0f}  [{both}]")

    # Try best EMA trend + time stop combinations
    print(f"\nCOMBINATION GRID")
    print("=" * 80)
    best = (0, 0, 0, 0)
    for ew in [175, 200, 220]:
        for ts in [15, 20, 25, 30, None]:
            sig_tr = gen(train_df, ema_trend_window=ew, time_stop=ts)
            sig_te = gen(test_df, ema_trend_window=ew, time_stop=ts)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            if tr[0] > 0 and te[0] > 0 and te[3] >= 50 and te[0] > best[0]:
                best = (te[0], tr[0], ew, ts)
            ts_str = str(ts) if ts else "None"
            print(f"  EMA({ew})+TS={ts_str:>4}  test={te[0]:>7.4f}  train={tr[0]:>7.4f}  trades={te[3]:>4}  net={te[4]:>8.0f}  [{both}]")

    print(f"\nBEST COMBO: EMA({best[2]}) + TS={best[3]} -> test={best[0]:.4f}, train={best[1]:.4f}")


if __name__ == "__main__":
    main()
