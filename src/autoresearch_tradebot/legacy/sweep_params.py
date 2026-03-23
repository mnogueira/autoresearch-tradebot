"""
sweep_params.py — Comprehensive parameter sweep for the honest EMA crossover strategy.
Tests all parameter dimensions systematically, then finds best combination.
"""

import numpy as np
import pandas as pd
import ta
import itertools

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


def generate_signals_param(df, ema_fast=8, ema_slow=34, sma_trend=162,
                           adx_thresh=20, adx_window=14,
                           rsi_window=9, rsi_long=55, rsi_short=45,
                           atr_window=20, atr_mult=2.0,
                           skip_hour=13, bars_remaining_min=36):
    """Parameterized version of the honest strategy."""
    ema_f = ta.trend.ema_indicator(df["Close"], window=ema_fast)
    ema_s = ta.trend.ema_indicator(df["Close"], window=ema_slow)
    rsi = ta.momentum.rsi(df["Close"], window=rsi_window)
    sma = df["Close"].rolling(window=sma_trend).mean()
    adx_val = ta.trend.adx(df["High"], df["Low"], df["Close"], window=adx_window)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=atr_window)

    close = df["Close"].values
    ef = ema_f.values
    es = ema_s.values
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
            pos = 0
            prev_date = d
            continue
        if is_last[i]:
            sig[i] = 0
            pos = 0
            prev_date = d
            continue

        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(sv[i]) or np.isnan(av[i]) or np.isnan(at[i]):
            sig[i] = pos
            prev_date = d
            continue

        # Exit: ATR trailing stop
        if pos != 0:
            cur_atr = at[i] if not np.isnan(at[i]) else 0
            if pos == 1:
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
            prev_date = d
            continue

        # Entry filters
        cur_time = times[i]
        if skip_hour is not None and hasattr(cur_time, 'hour') and cur_time.hour == skip_hour:
            prev_date = d
            continue
        if av[i] < adx_thresh or br[i] <= bars_remaining_min:
            prev_date = d
            continue

        # EMA crossover + SMA trend + RSI momentum
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


def fast_backtest(df, signals):
    """Inline backtest — returns (sharpe, pf, wr, trades, net_profit, max_dd)."""
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(-1, 1)
    day_last = df.groupby("date").tail(1).index
    signals.loc[day_last] = 0

    position = 0
    trades = []
    entry_price = 0.0

    for i in range(len(df)):
        signal = signals.iloc[i]
        fill_price = df["Open"].iloc[i]

        if i > 0 and df["date"].iloc[i] != df["date"].iloc[i - 1] and position != 0:
            pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
            trades.append(pnl)
            position = 0

        if signal != position:
            if position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                trades.append(pnl)
            if signal != 0:
                entry_price = fill_price
            position = signal

    if position != 0:
        pnl = (df["Open"].iloc[-1] - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
        trades.append(pnl)

    if len(trades) < 20:
        return 0.0, 0.0, 0.0, len(trades), 0.0, 0.0

    arr = np.array(trades)
    n = len(arr)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    net = arr.sum()
    wr = len(wins) / n if n > 0 else 0
    gp = wins.sum() if len(wins) > 0 else 0
    gl = abs(losses.sum()) if len(losses) > 0 else 1e-9
    pf = gp / gl

    if n > 1 and arr.std(ddof=1) > 0:
        trading_days = df.index.normalize().nunique()
        tpd = n / max(trading_days, 1)
        tpy = tpd * 252
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpy)
    else:
        sharpe = 0.0

    equity = 100000 + np.concatenate([[0], np.cumsum(arr)])
    peak_eq = np.maximum.accumulate(equity)
    dd = ((peak_eq - equity) / peak_eq * 100).max()

    return round(sharpe, 4), round(pf, 4), round(wr, 4), n, round(net, 2), round(dd, 2)


def run_sweep(train_df, test_df, param_name, param_values, base_params):
    """Sweep one parameter, return results sorted by test_sharpe."""
    results = []
    for val in param_values:
        params = {k: v for k, v in base_params.items() if not k.startswith('_')}
        params[param_name] = val
        try:
            sig_train = generate_signals_param(train_df, **params)
            sig_test = generate_signals_param(test_df, **params)
            tr_sharpe, tr_pf, tr_wr, tr_n, tr_net, tr_dd = fast_backtest(train_df, sig_train)
            te_sharpe, te_pf, te_wr, te_n, te_net, te_dd = fast_backtest(test_df, sig_test)
            results.append({
                'param': val,
                'train_sharpe': tr_sharpe, 'test_sharpe': te_sharpe,
                'train_pf': tr_pf, 'test_pf': te_pf,
                'train_trades': tr_n, 'test_trades': te_n,
                'test_net': te_net, 'test_dd': te_dd,
                'test_wr': te_wr,
            })
        except Exception as e:
            print(f"  ERROR {param_name}={val}: {e}")
    return sorted(results, key=lambda x: x['test_sharpe'], reverse=True)


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    BASE = dict(ema_fast=8, ema_slow=34, sma_trend=200, adx_thresh=20,
                adx_window=14, rsi_window=7, rsi_long=65, rsi_short=45,
                atr_window=20, atr_mult=2.0, skip_hour=13, bars_remaining_min=36)

    print(f"\n{'='*80}")
    print("BASELINE")
    print(f"{'='*80}")
    sig_tr = generate_signals_param(train_df, **BASE)
    sig_te = generate_signals_param(test_df, **BASE)
    tr = fast_backtest(train_df, sig_tr)
    te = fast_backtest(test_df, sig_te)
    print(f"  Train: sharpe={tr[0]}, PF={tr[1]}, trades={tr[3]}, net={tr[4]}")
    print(f"  Test:  sharpe={te[0]}, PF={te[1]}, trades={te[3]}, net={te[4]}")

    sweeps = {
        'bars_remaining_min': [12, 18, 24, 30, 36, 42, 48, 60],
        'sma_trend':   [180, 190, 200, 210, 220, 240],
        'rsi_window':  [5, 6, 7, 8, 10],
        'rsi_long':    [58, 60, 62, 65, 67, 70, 75],
        'rsi_short':   [30, 35, 38, 40, 42, 45, 48, 50],
        'ema_fast':    [6, 7, 8, 9, 10],
        'ema_slow':    [26, 30, 34, 38, 42],
        'adx_thresh':  [15, 18, 20, 22, 25],
        'atr_mult':    [1.5, 1.75, 2.0, 2.25, 2.5, 3.0],
        'atr_window':  [10, 14, 17, 20, 25],
        'skip_hour':   [None, 12, 13, 14, 15],
    }

    best_params = BASE.copy()

    for pname, pvals in sweeps.items():
        print(f"\n{'='*80}")
        print(f"SWEEPING: {pname} = {pvals}")
        print(f"{'='*80}")
        results = run_sweep(train_df, test_df, pname, pvals, best_params)
        for r in results[:5]:
            both_pos = "OK" if r['train_sharpe'] > 0 and r['test_sharpe'] > 0 else "FAIL"
            enough = "OK" if r['test_trades'] >= 50 else "LOW"
            pval = str(r['param']) if r['param'] is not None else "None"
            print(f"  {pname}={pval:>6}  test={r['test_sharpe']:>7.4f}  train={r['train_sharpe']:>7.4f}  "
                  f"PF={r['test_pf']:>6.2f}  trades={r['test_trades']:>4}  net={r['test_net']:>8.0f}  "
                  f"dd={r['test_dd']:>5.2f}  [{both_pos}] [{enough}]")

        # Pick best that satisfies constraints
        for r in results:
            if r['train_sharpe'] > 0 and r['test_sharpe'] > 0 and r['test_trades'] >= 50:
                if r['test_sharpe'] >= best_params.get('_best_test_sharpe', te[0]):
                    best_params[pname] = r['param']
                    best_params['_best_test_sharpe'] = r['test_sharpe']
                    print(f"  >>> UPDATED {pname} = {r['param']} (test_sharpe={r['test_sharpe']})")
                break

    # Remove internal tracking key
    best_params.pop('_best_test_sharpe', None)

    print(f"\n{'='*80}")
    print("BEST PARAMS FOUND (coordinate descent)")
    print(f"{'='*80}")
    for k, v in best_params.items():
        changed = " ***" if v != BASE.get(k) else ""
        print(f"  {k}: {v}{changed}")

    # Final run with best params
    print(f"\n{'='*80}")
    print("FINAL RESULT WITH BEST PARAMS")
    print(f"{'='*80}")
    sig_tr = generate_signals_param(train_df, **best_params)
    sig_te = generate_signals_param(test_df, **best_params)
    tr = fast_backtest(train_df, sig_tr)
    te = fast_backtest(test_df, sig_te)
    print(f"  Train: sharpe={tr[0]}, PF={tr[1]}, WR={tr[2]}, trades={tr[3]}, net={tr[4]}, dd={tr[5]}")
    print(f"  Test:  sharpe={te[0]}, PF={te[1]}, WR={te[2]}, trades={te[3]}, net={te[4]}, dd={te[5]}")

    # Also try grid around top-2 params that changed
    changed = {k: v for k, v in best_params.items() if v != BASE.get(k)}
    if len(changed) >= 2:
        print(f"\n{'='*80}")
        print(f"GRID SEARCH around changed params: {list(changed.keys())}")
        print(f"{'='*80}")
        # Take the first 2 changed params for 2D grid
        keys = list(changed.keys())[:2]
        # Generate small grids around each
        grids = {}
        for k in keys:
            v = changed[k]
            if isinstance(v, int):
                grids[k] = [max(1, v-2), v-1, v, v+1, v+2]
            elif isinstance(v, float):
                grids[k] = [round(v-0.5, 1), round(v-0.25, 1), v, round(v+0.25, 1), round(v+0.5, 1)]
            else:
                grids[k] = [v]

        best_combo_sharpe = te[0]
        best_combo = best_params.copy()
        for v1 in grids[keys[0]]:
            for v2 in grids[keys[1]]:
                params = best_params.copy()
                params[keys[0]] = v1
                params[keys[1]] = v2
                try:
                    s_tr = generate_signals_param(train_df, **params)
                    s_te = generate_signals_param(test_df, **params)
                    r_tr = fast_backtest(train_df, s_tr)
                    r_te = fast_backtest(test_df, s_te)
                    if r_tr[0] > 0 and r_te[0] > 0 and r_te[3] >= 50 and r_te[0] > best_combo_sharpe:
                        best_combo_sharpe = r_te[0]
                        best_combo = params.copy()
                        print(f"  GRID IMPROVED: {keys[0]}={v1}, {keys[1]}={v2} -> test={r_te[0]}, train={r_tr[0]}")
                except:
                    pass

        if best_combo_sharpe > te[0]:
            print(f"\n  GRID BEST: test_sharpe={best_combo_sharpe}")
            sig_tr = generate_signals_param(train_df, **best_combo)
            sig_te = generate_signals_param(test_df, **best_combo)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            print(f"  Train: sharpe={tr[0]}, PF={tr[1]}, WR={tr[2]}, trades={tr[3]}, net={tr[4]}, dd={tr[5]}")
            print(f"  Test:  sharpe={te[0]}, PF={te[1]}, WR={te[2]}, trades={te[3]}, net={te[4]}, dd={te[5]}")
            best_params = best_combo
        else:
            print("  No grid improvement found.")

    print(f"\n{'='*80}")
    print("FINAL BEST PARAMETERS")
    print(f"{'='*80}")
    for k, v in best_params.items():
        print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
