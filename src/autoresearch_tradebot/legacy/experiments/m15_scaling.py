"""Quick M15 parameter test — scale M5 params proportionally."""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers
from ..sweep_params import fast_backtest


def gen_m15(df, ema_fast=3, ema_slow=11, trend_window=67, adx_window=14,
            adx_thresh=20, rsi_window=7, rsi_long=65, rsi_short=45,
            atr_window=7, atr_mult=2.0, bars_min=12):
    """M15-adjusted strategy."""
    ema_f = ta.trend.ema_indicator(df["Close"], window=ema_fast)
    ema_s = ta.trend.ema_indicator(df["Close"], window=ema_slow)
    trend = ta.trend.ema_indicator(df["Close"], window=trend_window)
    rsi = ta.momentum.rsi(df["Close"], window=rsi_window)
    adx_val = ta.trend.adx(df["High"], df["Low"], df["Close"], window=adx_window)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=atr_window)

    close = df["Close"].values
    ef = ema_f.values; es = ema_s.values; rv = rsi.values
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
        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            ema_exit = False
            if i > 0 and not np.isnan(ef[i-1]) and not np.isnan(es[i-1]):
                if pos == 1 and ef[i] < es[i] and ef[i-1] >= es[i-1]: ema_exit = True
                elif pos == -1 and ef[i] > es[i] and ef[i-1] <= es[i-1]: ema_exit = True
            if ema_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if cur_atr > 0 and close[i] < peak - atr_mult * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if cur_atr > 0 and close[i] > peak + atr_mult * cur_atr: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        cur_time = times[i]
        if hasattr(cur_time, 'hour') and cur_time.hour == 13: prev_date = d; continue
        if av[i] < adx_thresh or br[i] <= bars_min: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        if i > 0 and not np.isnan(ef[i-1]) and not np.isnan(es[i-1]):
            cross_up = ef[i] > es[i] and ef[i-1] <= es[i-1]
            cross_dn = ef[i] < es[i] and ef[i-1] >= es[i-1]
            if cross_up and close[i] > tv[i] and r > rsi_long:
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < tv[i] and r < rsi_short:
                sig[i] = -1; pos = -1; peak = close[i]
        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def main():
    df = load_data(timeframe="M15")
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    # Proportional scaling: M5 -> M15 (3x)
    # EMA fast: 8 -> 3 (8/3≈3), slow: 34 -> 11 (34/3≈11)
    # Trend: 200 -> 67 (200/3≈67)
    # ATR: 20 -> 7 (20/3≈7)
    # Bars remaining: 36 -> 12
    configs = [
        ("Proportional (3/11/67)", dict(ema_fast=3, ema_slow=11, trend_window=67, atr_window=7, bars_min=12)),
        ("Wider EMAs (5/20/67)", dict(ema_fast=5, ema_slow=20, trend_window=67, atr_window=7, bars_min=12)),
        ("Wider EMAs (8/34/67)", dict(ema_fast=8, ema_slow=34, trend_window=67, atr_window=7, bars_min=12)),
        ("Same params as M5", dict(ema_fast=8, ema_slow=34, trend_window=200, atr_window=20, bars_min=36)),
        ("Adjusted (5/17/100)", dict(ema_fast=5, ema_slow=17, trend_window=100, atr_window=10, bars_min=12)),
        ("Loose RSI (55/45)", dict(ema_fast=3, ema_slow=11, trend_window=67, atr_window=7, bars_min=12, rsi_long=55, rsi_short=45)),
        ("No RSI", dict(ema_fast=3, ema_slow=11, trend_window=67, atr_window=7, bars_min=12, rsi_long=0, rsi_short=100)),
    ]

    print(f"{'Config':<30} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8}")
    print("-" * 75)
    for name, kwargs in configs:
        try:
            sig_tr = gen_m15(train_df, **kwargs)
            sig_te = gen_m15(test_df, **kwargs)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>6} {te[4]:>8.0f}  [{both}]")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")


if __name__ == "__main__":
    main()
