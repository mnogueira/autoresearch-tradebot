"""
sweep_exit.py — Sweep exit-related parameters for the EMA reversal exit strategy.
Tests separate EMA periods for exit, ATR mult, and combinations.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from .sweep_params import fast_backtest


def gen_signals_exit_sweep(df, ema_fast=8, ema_slow=34, sma_trend=200,
                            adx_thresh=20, adx_window=14,
                            rsi_window=7, rsi_long=65, rsi_short=45,
                            atr_window=20, atr_mult=2.0,
                            skip_hour=13, bars_remaining_min=36,
                            exit_ema_fast=8, exit_ema_slow=34,
                            use_ema_exit=True):
    """Strategy with separate entry and exit EMA periods."""
    ema_f = ta.trend.ema_indicator(df["Close"], window=ema_fast)
    ema_s = ta.trend.ema_indicator(df["Close"], window=ema_slow)
    # Separate exit EMAs (may differ from entry)
    if exit_ema_fast != ema_fast:
        exit_ef = ta.trend.ema_indicator(df["Close"], window=exit_ema_fast)
    else:
        exit_ef = ema_f
    if exit_ema_slow != ema_slow:
        exit_es = ta.trend.ema_indicator(df["Close"], window=exit_ema_slow)
    else:
        exit_es = ema_s

    rsi = ta.momentum.rsi(df["Close"], window=rsi_window)
    sma = df["Close"].rolling(window=sma_trend).mean()
    adx_val = ta.trend.adx(df["High"], df["Low"], df["Close"], window=adx_window)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=atr_window)

    close = df["Close"].values
    ef = ema_f.values
    es = ema_s.values
    xef = exit_ef.values
    xes = exit_es.values
    rv = rsi.values
    sv = sma.values
    av = adx_val.values
    at = atr.values
    is_last = df["is_last_30min"].values
    is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values
    dates = df["date"].values
    times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0
    prev_date = None
    peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date:
            pos = 0; prev_date = d; continue
        if is_last[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue

        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(sv[i]) or np.isnan(av[i]) or np.isnan(at[i]):
            sig[i] = pos; prev_date = d; continue

        if pos != 0:
            cur_atr = at[i] if not np.isnan(at[i]) else 0
            ema_exit = False
            if use_ema_exit and i > 0 and not np.isnan(xef[i-1]) and not np.isnan(xes[i-1]):
                if pos == 1 and xef[i] < xes[i] and xef[i-1] >= xes[i-1]:
                    ema_exit = True
                elif pos == -1 and xef[i] > xes[i] and xef[i-1] <= xes[i-1]:
                    ema_exit = True
            if ema_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, close[i])
                if cur_atr > 0 and close[i] < peak - atr_mult * cur_atr:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            elif pos == -1:
                peak = min(peak, close[i])
                if cur_atr > 0 and close[i] > peak + atr_mult * cur_atr:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            prev_date = d; continue

        cur_time = times[i]
        if skip_hour is not None and hasattr(cur_time, 'hour') and cur_time.hour == skip_hour:
            prev_date = d; continue
        if av[i] < adx_thresh or br[i] <= bars_remaining_min:
            prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        if i > 0 and not np.isnan(ef[i-1]) and not np.isnan(es[i-1]):
            cross_up = ef[i] > es[i] and ef[i-1] <= es[i-1]
            cross_dn = ef[i] < es[i] and ef[i-1] >= es[i-1]
            if cross_up and close[i] > sv[i] and r > rsi_long:
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < sv[i] and r < rsi_short:
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

    print("=" * 90)
    print("EXIT PARAMETER SWEEP")
    print("=" * 90)

    # Test different exit EMA combinations
    exit_combos = [
        (5, 21), (5, 26), (5, 34),
        (8, 21), (8, 26), (8, 34), (8, 40),
        (10, 26), (10, 34), (10, 40),
        (12, 26), (12, 34), (12, 40),
        (3, 13), (3, 21), (3, 34),
    ]

    results = []
    for ef, es in exit_combos:
        sig_tr = gen_signals_exit_sweep(train_df, exit_ema_fast=ef, exit_ema_slow=es)
        sig_te = gen_signals_exit_sweep(test_df, exit_ema_fast=ef, exit_ema_slow=es)
        tr = fast_backtest(train_df, sig_tr)
        te = fast_backtest(test_df, sig_te)
        both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
        results.append((te[0], tr[0], te[1], te[3], te[4], ef, es, both))

    results.sort(reverse=True)
    print(f"\n{'Exit EMA':<12} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8} {'status':>6}")
    for te_s, tr_s, pf, n, net, ef, es, both in results:
        print(f"  ({ef:>2}/{es:>2})     {te_s:>8.4f} {tr_s:>8.4f} {pf:>6.2f} {n:>6} {net:>8.0f}   [{both}]")

    # Also sweep ATR mult with best exit EMA
    best_exit = results[0]
    best_ef, best_es = best_exit[5], best_exit[6]
    print(f"\n{'='*90}")
    print(f"ATR MULT SWEEP with exit EMA({best_ef}/{best_es})")
    print(f"{'='*90}")

    for mult in [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5]:
        sig_tr = gen_signals_exit_sweep(train_df, exit_ema_fast=best_ef, exit_ema_slow=best_es, atr_mult=mult)
        sig_te = gen_signals_exit_sweep(test_df, exit_ema_fast=best_ef, exit_ema_slow=best_es, atr_mult=mult)
        tr = fast_backtest(train_df, sig_tr)
        te = fast_backtest(test_df, sig_te)
        both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
        print(f"  ATR x{mult:<4}  test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  net={te[4]:>8.0f}  [{both}]")


if __name__ == "__main__":
    main()
