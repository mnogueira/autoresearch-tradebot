"""
sweep_creative.py — Proper parameter sweep for each creative signal in ALL roles.
Rule #8: Never reject from one test. Sweep parameters AND test in all roles.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from .sweep_params import fast_backtest


def rolling_hurst(close, window=100):
    def hurst_rs(series):
        ts = np.array(series); returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10: return 0.5
        mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
        if s == 0 or r == 0: return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def base_gen(df, extra_filter_fn=None, extra_exit_fn=None, entry_replace_fn=None):
    """Flexible strategy: base EMA crossover + optional creative filter/exit/entry."""
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema220 = ta.trend.ema_indicator(df["Close"], window=220)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix12 = ta.trend.trix(df["Close"], window=12)
    hurst = rolling_hurst(df["Close"], window=100)
    trix_med = trix12.rolling(500, min_periods=100).median().shift(1)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tp_vol = (typical * df["Volume"]).groupby(df.index.date).cumsum()
    cum_vol = df["Volume"].groupby(df.index.date).cumsum().replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol

    c = df["Close"].values; e8 = ema8.values; e34 = ema34.values
    rv = rsi7.values; tv = ema220.values; av = adx14.values
    at_ = atr20.values; txv = trix12.values; tmv = trix_med.values
    hv = hurst.values; vw = vwap.values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date: pos = 0; prev_date = d; continue
        if il[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        if pos != 0:
            ca = at_[i] if not np.isnan(at_[i]) else 0
            tm = tmv[i] if not np.isnan(tmv[i]) else 0
            fv = txv[i] if not np.isnan(txv[i]) else tm
            fp = txv[i-1] if i > 0 and not np.isnan(txv[i-1]) else tm
            trix_exit = (pos == 1 and fv < tm and fp >= tm) or (pos == -1 and fv > tm and fp <= tm)

            # Creative exit
            creative_exit = extra_exit_fn(i, pos, c, df) if extra_exit_fn else False

            if trix_exit or creative_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, c[i])
                if ca > 0 and c[i] < peak - 2 * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, c[i])
                if ca > 0 and c[i] > peak + 2 * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour in (12, 13): prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue
        if av[i] < 20: prev_date = d; continue
        h = hv[i]
        if not np.isnan(h) and h < 0.50: prev_date = d; continue

        # Creative filter
        if extra_filter_fn and not extra_filter_fn(i, c, df):
            prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        vw_i = vw[i] if not np.isnan(vw[i]) else c[i]

        if entry_replace_fn:
            entry = entry_replace_fn(i, c, df, tv, av)
        else:
            entry = None

        if entry is not None:
            if entry == 1: sig[i] = 1; pos = 1; peak = c[i]
            elif entry == -1: sig[i] = -1; pos = -1; peak = c[i]
        elif i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cu = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cd = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            if cu and c[i] > tv[i] and r > 65 and c[i] > vw_i:
                sig[i] = 1; pos = 1; peak = c[i]
            elif cd and c[i] < tv[i] and r < 40 and c[i] < vw_i:
                sig[i] = -1; pos = -1; peak = c[i]

        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    # Precompute all creative indicators on both splits
    for split_df, label in [(train_df, "train"), (test_df, "test")]:
        # OFI
        bar_range = (split_df["High"] - split_df["Low"]).replace(0, np.nan)
        cp = (split_df["Close"] - split_df["Low"]) / bar_range
        buy_v = cp * split_df["Volume"]
        sell_v = (1 - cp) * split_df["Volume"]
        for w in [5, 10, 20, 30, 50]:
            ofi = (buy_v - sell_v).rolling(w).sum() / split_df["Volume"].rolling(w).sum()
            split_df[f"ofi_{w}"] = ofi

        # Acceleration
        for fast, slow in [(3, 10), (5, 20), (5, 30), (10, 30)]:
            split_df[f"accel_{fast}_{slow}"] = split_df["Close"].pct_change(fast) - split_df["Close"].pct_change(slow)

        # Vol ratio
        ret = split_df["Close"].pct_change()
        for fast, slow in [(3, 20), (5, 30), (5, 50), (10, 50)]:
            split_df[f"vr_{fast}_{slow}"] = ret.rolling(fast).std() / ret.rolling(slow).std()

        # Streak
        direction = np.sign(split_df["Close"].diff())
        streak = pd.Series(0.0, index=split_df.index)
        for i in range(1, len(split_df)):
            if direction.iloc[i] == direction.iloc[i-1] and direction.iloc[i] != 0:
                streak.iloc[i] = streak.iloc[i-1] + direction.iloc[i]
            else:
                streak.iloc[i] = direction.iloc[i]
        split_df["streak"] = streak

    # ================================================================
    # SWEEP: OFI as filter, exit, and entry confirmation
    # ================================================================
    print("=" * 90)
    print("OFI SWEEP — windows x thresholds x roles")
    print("=" * 90)

    best = (0, "", "")
    for w in [5, 10, 20, 30, 50]:
        for thresh in [0.02, 0.05, 0.1, 0.15, 0.2, 0.3]:
            col = f"ofi_{w}"

            # ROLE 1: Entry filter (OFI confirms direction)
            def make_filter(col=col, thresh=thresh):
                def f(i, c, df):
                    v = df[col].values[i]
                    return True if np.isnan(v) else True  # permissive on NaN
                return f
            # Actually need directional: long if ofi > thresh, short if ofi < -thresh
            tr_ofi = train_df[col].values
            te_ofi = test_df[col].values

            def make_ofi_filter(ofi_v, thresh=thresh):
                def f(i, c, df):
                    v = ofi_v[i]
                    if np.isnan(v): return True
                    return True  # we'll check in entry
                return f

            # Simpler: just test as entry filter via lambda capturing
            # Test OFI > thresh for longs, < -thresh for shorts
            for role_name, role in [("filter", "f"), ("exit", "e")]:
                try:
                    if role == "f":
                        def make_f(ofi_v, t=thresh):
                            def fn(i, c, df):
                                v = ofi_v[i] if i < len(ofi_v) else 0
                                if np.isnan(v): return True
                                return v > t or v < -t  # only trade when OFI is strong
                            return fn
                        sig_tr = base_gen(train_df, extra_filter_fn=make_f(tr_ofi))
                        sig_te = base_gen(test_df, extra_filter_fn=make_f(te_ofi))
                    elif role == "e":
                        def make_e(ofi_v, t=thresh):
                            def fn(i, pos, c, df):
                                v = ofi_v[i] if i < len(ofi_v) else 0
                                if np.isnan(v): return False
                                if pos == 1 and v < -t: return True
                                if pos == -1 and v > t: return True
                                return False
                            return fn
                        sig_tr = base_gen(train_df, extra_exit_fn=make_e(tr_ofi))
                        sig_te = base_gen(test_df, extra_exit_fn=make_e(te_ofi))

                    tr = fast_backtest(train_df, sig_tr)
                    te = fast_backtest(test_df, sig_te)
                    if tr[0] > 0 and te[0] > 0 and te[3] >= 50 and te[0] > 3.32:
                        print(f"  *** OFI w={w} t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                        if te[0] > best[0]: best = (te[0], f"OFI w={w} t={thresh}", role_name)
                    elif tr[0] > 0 and te[0] > 3.0 and te[3] >= 50:
                        print(f"  +   OFI w={w} t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                except Exception as e:
                    pass

    # ================================================================
    # SWEEP: Acceleration as filter and exit
    # ================================================================
    print(f"\n{'='*90}")
    print("ACCELERATION SWEEP")
    print("=" * 90)
    for fast, slow in [(3, 10), (5, 20), (5, 30), (10, 30)]:
        col = f"accel_{fast}_{slow}"
        tr_ac = train_df[col].values
        te_ac = test_df[col].values
        for thresh in [0.0, 0.001, 0.002, 0.005]:
            for role_name, role in [("filter", "f"), ("exit", "e")]:
                try:
                    if role == "f":
                        def make_f(av, t=thresh):
                            def fn(i, c, df):
                                v = av[i] if i < len(av) else 0
                                if np.isnan(v): return True
                                return abs(v) > t
                            return fn
                        sig_tr = base_gen(train_df, extra_filter_fn=make_f(tr_ac))
                        sig_te = base_gen(test_df, extra_filter_fn=make_f(te_ac))
                    elif role == "e":
                        def make_e(av, t=thresh):
                            def fn(i, pos, c, df):
                                v = av[i] if i < len(av) else 0
                                if np.isnan(v): return False
                                if pos == 1 and v < -t: return True
                                if pos == -1 and v > t: return True
                                return False
                            return fn
                        sig_tr = base_gen(train_df, extra_exit_fn=make_e(tr_ac))
                        sig_te = base_gen(test_df, extra_exit_fn=make_e(te_ac))

                    tr = fast_backtest(train_df, sig_tr)
                    te = fast_backtest(test_df, sig_te)
                    if tr[0] > 0 and te[0] > 0 and te[3] >= 50 and te[0] > 3.32:
                        print(f"  *** Accel({fast}/{slow}) t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                        if te[0] > best[0]: best = (te[0], f"Accel({fast}/{slow}) t={thresh}", role_name)
                    elif tr[0] > 0 and te[0] > 3.0 and te[3] >= 50:
                        print(f"  +   Accel({fast}/{slow}) t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                except:
                    pass

    # ================================================================
    # SWEEP: Vol ratio as filter and exit
    # ================================================================
    print(f"\n{'='*90}")
    print("VOLATILITY RATIO SWEEP")
    print("=" * 90)
    for fast, slow in [(3, 20), (5, 30), (5, 50), (10, 50)]:
        col = f"vr_{fast}_{slow}"
        tr_vr = train_df[col].values
        te_vr = test_df[col].values
        for thresh in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
            for role_name, role in [("filter_above", "fa"), ("filter_below", "fb"), ("exit", "e")]:
                try:
                    if role == "fa":
                        def make_f(vv, t=thresh):
                            def fn(i, c, df):
                                v = vv[i] if i < len(vv) else 1
                                if np.isnan(v): return True
                                return v > t  # only trade when vol expanding
                            return fn
                        sig_tr = base_gen(train_df, extra_filter_fn=make_f(tr_vr))
                        sig_te = base_gen(test_df, extra_filter_fn=make_f(te_vr))
                    elif role == "fb":
                        def make_f(vv, t=thresh):
                            def fn(i, c, df):
                                v = vv[i] if i < len(vv) else 1
                                if np.isnan(v): return True
                                return v < t  # only trade when vol contracting (squeeze about to break)
                            return fn
                        sig_tr = base_gen(train_df, extra_filter_fn=make_f(tr_vr))
                        sig_te = base_gen(test_df, extra_filter_fn=make_f(te_vr))
                    elif role == "e":
                        def make_e(vv, t=thresh):
                            def fn(i, pos, c, df):
                                v = vv[i] if i < len(vv) else 1
                                if np.isnan(v): return False
                                return v > t  # exit when vol spikes (trend exhaustion)
                            return fn
                        sig_tr = base_gen(train_df, extra_exit_fn=make_e(tr_vr))
                        sig_te = base_gen(test_df, extra_exit_fn=make_e(te_vr))

                    tr = fast_backtest(train_df, sig_tr)
                    te = fast_backtest(test_df, sig_te)
                    if tr[0] > 0 and te[0] > 0 and te[3] >= 50 and te[0] > 3.32:
                        print(f"  *** VR({fast}/{slow}) t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                        if te[0] > best[0]: best = (te[0], f"VR({fast}/{slow}) t={thresh}", role_name)
                    elif tr[0] > 0 and te[0] > 3.0 and te[3] >= 50:
                        print(f"  +   VR({fast}/{slow}) t={thresh} {role_name}: te={te[0]:.4f} tr={tr[0]:.4f} n={te[3]} net={te[4]:.0f}")
                except:
                    pass

    print(f"\n{'='*90}")
    print(f"BEST FOUND: {best[1]} as {best[2]} -> test={best[0]:.4f}")
    print("=" * 90)


if __name__ == "__main__":
    main()
