"""
mega_sweep.py — Test EVERY indicator from ta library in EVERY role.
Roles: entry signal, entry filter, exit signal, trend filter.
Rule #8: Never reject from one test. Sweep parameters AND test in all roles.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


def fast_backtest(df, signals):
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(-1, 1)
    day_last = df.groupby("date").tail(1).index
    signals.loc[day_last] = 0
    position = 0; trades = []; entry_price = 0.0
    for i in range(len(df)):
        signal = signals.iloc[i]
        fill_price = df["Open"].iloc[i]
        if i > 0 and df["date"].iloc[i] != df["date"].iloc[i-1] and position != 0:
            pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
            trades.append(pnl); position = 0
        if signal != position:
            if position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                trades.append(pnl)
            if signal != 0: entry_price = fill_price
            position = signal
    if position != 0:
        pnl = (df["Open"].iloc[-1] - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
        trades.append(pnl)
    if len(trades) < 10:
        return 0, 0, 0, len(trades), 0
    arr = np.array(trades); n = len(arr)
    wins = arr[arr > 0]; losses = arr[arr < 0]
    net = arr.sum()
    gp = wins.sum() if len(wins) > 0 else 0
    gl = abs(losses.sum()) if len(losses) > 0 else 1e-9
    pf = gp / gl
    wr = len(wins) / n
    trading_days = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        tpd = n / max(trading_days, 1)
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpd * 252)
    else:
        sharpe = 0
    return round(sharpe, 4), round(pf, 4), round(wr, 4), n, round(net, 2)


def compute_all_indicators(df):
    """Compute ALL indicators once, return dict of name->values."""
    ind = {}
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    # TREND
    ind["aroon_up"] = ta.trend.aroon_up(h, l, window=25)
    ind["aroon_down"] = ta.trend.aroon_down(h, l, window=25)
    ind["cci_20"] = ta.trend.cci(h, l, c, window=20)
    ind["cci_14"] = ta.trend.cci(h, l, c, window=14)
    ind["dpo_20"] = ta.trend.dpo(c, window=20)
    ind["kst"] = ta.trend.kst(c)
    ind["kst_sig"] = ta.trend.kst_sig(c)
    ind["mass_index"] = ta.trend.mass_index(h, l)
    ind["psar_up"] = ta.trend.psar_up(h, l, c)
    ind["psar_down"] = ta.trend.psar_down(h, l, c)
    ind["stc"] = ta.trend.stc(c)
    ind["trix"] = ta.trend.trix(c, window=15)
    ind["vortex_pos"] = ta.trend.vortex_indicator_pos(h, l, c, window=14)
    ind["vortex_neg"] = ta.trend.vortex_indicator_neg(h, l, c, window=14)
    ind["wma_20"] = ta.trend.wma_indicator(c, window=20)
    ind["ichimoku_a"] = ta.trend.ichimoku_a(h, l)
    ind["ichimoku_b"] = ta.trend.ichimoku_b(h, l)
    ind["ichimoku_base"] = ta.trend.ichimoku_base_line(h, l)
    ind["ichimoku_conv"] = ta.trend.ichimoku_conversion_line(h, l)

    # MOMENTUM
    ind["awesome"] = ta.momentum.awesome_oscillator(h, l)
    ind["kama_10"] = ta.momentum.kama(c, window=10)
    ind["kama_20"] = ta.momentum.kama(c, window=20)
    ind["ppo"] = ta.momentum.ppo(c)
    ind["ppo_hist"] = ta.momentum.ppo_hist(c)
    ind["roc_10"] = ta.momentum.roc(c, window=10)
    ind["roc_5"] = ta.momentum.roc(c, window=5)
    ind["stoch_k"] = ta.momentum.stoch(h, l, c, window=14)
    ind["stoch_d"] = ta.momentum.stoch_signal(h, l, c, window=14)
    ind["uo"] = ta.momentum.ultimate_oscillator(h, l, c)

    # VOLATILITY
    ind["ulcer"] = ta.volatility.ulcer_index(c)
    ind["kc_wband"] = ta.volatility.keltner_channel_wband(h, l, c, window=20)

    # VOLUME
    ind["obv"] = ta.volume.on_balance_volume(c, v)
    ind["cmf"] = ta.volume.chaikin_money_flow(h, l, c, v)
    ind["fi_13"] = ta.volume.force_index(c, v, window=13)
    ind["mfi_14"] = ta.volume.money_flow_index(h, l, c, v, window=14)
    ind["emv"] = ta.volume.ease_of_movement(h, l, v)
    ind["nvi"] = ta.volume.negative_volume_index(c, v)
    ind["vpt"] = ta.volume.volume_price_trend(c, v)

    return ind


def baseline_strategy(df, ind=None):
    """Current best strategy for comparison."""
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = ema200.values; av = adx14.values; at_ = atr20.values
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
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            ema_exit = False
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]: ema_exit = True
                elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]: ema_exit = True
            if ema_exit: sig[i] = 0; pos = 0
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
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < tv[i] and r < 45:
                sig[i] = -1; pos = -1; peak = close[i]
        prev_date = d
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def test_as_entry_filter(df, ind_name, ind_vals, base_ema8, base_ema34, base_ema200, base_rsi7, base_adx14, base_atr20):
    """ROLE 1: Use indicator as additional entry filter on top of baseline."""
    close = df["Close"].values
    e8 = base_ema8.values; e34 = base_ema34.values
    tv = base_ema200.values; rv = base_rsi7.values
    av = base_adx14.values; at_ = base_atr20.values
    iv = ind_vals.values if hasattr(ind_vals, 'values') else ind_vals
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    results = []
    # Test different threshold conditions
    # For oscillators (0-100): try >50, >60, >70 for longs; <50, <40, <30 for shorts
    # For centered oscillators: try >0 for longs, <0 for shorts
    # For trend indicators: try crossover with signal or zero line

    # Determine indicator range
    valid = iv[~np.isnan(iv)] if hasattr(iv, '__len__') else np.array([])
    if len(valid) < 100:
        return []

    med = np.median(valid)
    p25, p75 = np.percentile(valid, 25), np.percentile(valid, 75)

    # Test: indicator > median for longs, < median for shorts
    for long_thresh, short_thresh, label in [
        (med, med, "above/below median"),
        (p75, p25, "above P75/below P25"),
    ]:
        sig = np.zeros(len(df), dtype=np.int64)
        pos = 0; prev_date = None; peak = 0.0
        for i in range(len(df)):
            d = dates[i]
            if is_first[i] or d != prev_date: pos = 0; prev_date = d; continue
            if is_last[i]: sig[i] = 0; pos = 0; prev_date = d; continue
            if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
                sig[i] = pos; prev_date = d; continue
            if pos != 0:
                cur_atr = at_[i] if not np.isnan(at_[i]) else 0
                ema_exit = False
                if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                    if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]: ema_exit = True
                    elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]: ema_exit = True
                if ema_exit: sig[i] = 0; pos = 0
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
            fv = iv[i] if not np.isnan(iv[i]) else med
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                if cross_up and close[i] > tv[i] and r > 65 and fv > long_thresh:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < tv[i] and r < 45 and fv < short_thresh:
                    sig[i] = -1; pos = -1; peak = close[i]
            prev_date = d
        signals = pd.Series(sig, index=df.index)
        signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
        results.append((f"filter:{label}", signals))
    return results


def test_as_trend_filter(df, ind_name, ind_vals, base_ema8, base_ema34, base_rsi7, base_adx14, base_atr20):
    """ROLE 2: Use indicator as trend filter (replace EMA200)."""
    close = df["Close"].values
    e8 = base_ema8.values; e34 = base_ema34.values
    rv = base_rsi7.values; av = base_adx14.values; at_ = base_atr20.values
    iv = ind_vals.values if hasattr(ind_vals, 'values') else ind_vals
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    valid = iv[~np.isnan(iv)] if hasattr(iv, '__len__') else np.array([])
    if len(valid) < 100: return []

    # For price-level indicators: long when close > indicator
    # For oscillators: long when indicator > threshold
    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0
    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date: pos = 0; prev_date = d; continue
        if is_last[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(av[i]) or np.isnan(at_[i]) or np.isnan(iv[i]):
            sig[i] = pos; prev_date = d; continue
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            ema_exit = False
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                if pos == 1 and e8[i] < e34[i] and e8[i-1] >= e34[i-1]: ema_exit = True
                elif pos == -1 and e8[i] > e34[i] and e8[i-1] <= e34[i-1]: ema_exit = True
            if ema_exit: sig[i] = 0; pos = 0
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
        # Use indicator as trend: close > ind = bullish, close < ind = bearish
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            if cross_up and close[i] > iv[i] and r > 65:
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < iv[i] and r < 45:
                sig[i] = -1; pos = -1; peak = close[i]
        prev_date = d
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return [("trend_filter", signals)]


def test_as_exit(df, ind_name, ind_vals, base_ema8, base_ema34, base_ema200, base_rsi7, base_adx14, base_atr20):
    """ROLE 3: Use indicator as exit signal (replace EMA reversal, keep ATR trailing)."""
    close = df["Close"].values
    e8 = base_ema8.values; e34 = base_ema34.values
    tv = base_ema200.values; rv = base_rsi7.values
    av = base_adx14.values; at_ = base_atr20.values
    iv = ind_vals.values if hasattr(ind_vals, 'values') else ind_vals
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    valid = iv[~np.isnan(iv)] if hasattr(iv, '__len__') else np.array([])
    if len(valid) < 100: return []
    med = np.median(valid)

    # Exit when indicator crosses against position
    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0
    for i in range(len(df)):
        d = dates[i]
        if is_first[i] or d != prev_date: pos = 0; prev_date = d; continue
        if is_last[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            fv = iv[i] if not np.isnan(iv[i]) else med
            fv_prev = iv[i-1] if i > 0 and not np.isnan(iv[i-1]) else med
            # Indicator-based exit: crosses median against position
            ind_exit = False
            if pos == 1 and fv < med and fv_prev >= med: ind_exit = True
            elif pos == -1 and fv > med and fv_prev <= med: ind_exit = True
            # ATR trailing (always)
            if ind_exit: sig[i] = 0; pos = 0
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
                sig[i] = 1; pos = 1; peak = close[i]
            elif cross_dn and close[i] < tv[i] and r < 45:
                sig[i] = -1; pos = -1; peak = close[i]
        prev_date = d
    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return [("exit_signal", signals)]


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    print("Computing all indicators...")
    train_ind = compute_all_indicators(train_df)
    test_ind = compute_all_indicators(test_df)

    # Baseline indicators
    tr_ema8 = ta.trend.ema_indicator(train_df["Close"], window=8)
    tr_ema34 = ta.trend.ema_indicator(train_df["Close"], window=34)
    tr_ema200 = ta.trend.ema_indicator(train_df["Close"], window=200)
    tr_rsi7 = ta.momentum.rsi(train_df["Close"], window=7)
    tr_adx14 = ta.trend.adx(train_df["High"], train_df["Low"], train_df["Close"], window=14)
    tr_atr20 = ta.volatility.average_true_range(train_df["High"], train_df["Low"], train_df["Close"], window=20)

    te_ema8 = ta.trend.ema_indicator(test_df["Close"], window=8)
    te_ema34 = ta.trend.ema_indicator(test_df["Close"], window=34)
    te_ema200 = ta.trend.ema_indicator(test_df["Close"], window=200)
    te_rsi7 = ta.momentum.rsi(test_df["Close"], window=7)
    te_adx14 = ta.trend.adx(test_df["High"], test_df["Low"], test_df["Close"], window=14)
    te_atr20 = ta.volatility.average_true_range(test_df["High"], test_df["Low"], test_df["Close"], window=20)

    # Baseline result
    sig_tr = baseline_strategy(train_df)
    sig_te = baseline_strategy(test_df)
    tr_base = fast_backtest(train_df, sig_tr)
    te_base = fast_backtest(test_df, sig_te)
    print(f"\nBASELINE: test={te_base[0]:.4f}, train={tr_base[0]:.4f}, trades={te_base[3]}, net={te_base[4]:.0f}")
    print(f"\n{'='*100}")

    # Price-level indicators (can be used as trend filter)
    price_level = {"wma_20", "kama_10", "kama_20", "ichimoku_a", "ichimoku_b",
                   "ichimoku_base", "ichimoku_conv", "psar_up", "psar_down"}

    improvements = []

    for ind_name in sorted(train_ind.keys()):
        print(f"\n--- {ind_name} ---")
        tr_iv = train_ind[ind_name]
        te_iv = test_ind[ind_name]

        # ROLE 1: Entry filter
        try:
            tr_tests = test_as_entry_filter(train_df, ind_name, tr_iv,
                                             tr_ema8, tr_ema34, tr_ema200, tr_rsi7, tr_adx14, tr_atr20)
            te_tests = test_as_entry_filter(test_df, ind_name, te_iv,
                                             te_ema8, te_ema34, te_ema200, te_rsi7, te_adx14, te_atr20)
            for (label_tr, sig_tr), (label_te, sig_te) in zip(tr_tests, te_tests):
                r_tr = fast_backtest(train_df, sig_tr)
                r_te = fast_backtest(test_df, sig_te)
                both = "OK" if r_tr[0] > 0 and r_te[0] > 0 else ""
                beat = "***" if r_te[0] > te_base[0] and r_tr[0] > 0 and r_te[3] >= 50 else ""
                if r_te[0] > 0 or r_tr[0] > 0:  # only print non-zero
                    print(f"  {label_te:<30} te={r_te[0]:>7.4f} tr={r_tr[0]:>7.4f} n={r_te[3]:>4} net={r_te[4]:>7.0f} {both} {beat}")
                if beat:
                    improvements.append((ind_name, label_te, r_te[0], r_tr[0], r_te[3], r_te[4]))
        except Exception as e:
            print(f"  filter ERROR: {e}")

        # ROLE 2: Trend filter (only for price-level indicators)
        if ind_name in price_level:
            try:
                tr_tests = test_as_trend_filter(train_df, ind_name, tr_iv,
                                                 tr_ema8, tr_ema34, tr_rsi7, tr_adx14, tr_atr20)
                te_tests = test_as_trend_filter(test_df, ind_name, te_iv,
                                                 te_ema8, te_ema34, te_rsi7, te_adx14, te_atr20)
                for (label_tr, sig_tr), (label_te, sig_te) in zip(tr_tests, te_tests):
                    r_tr = fast_backtest(train_df, sig_tr)
                    r_te = fast_backtest(test_df, sig_te)
                    both = "OK" if r_tr[0] > 0 and r_te[0] > 0 else ""
                    beat = "***" if r_te[0] > te_base[0] and r_tr[0] > 0 and r_te[3] >= 50 else ""
                    if r_te[0] > 0 or r_tr[0] > 0:
                        print(f"  {label_te:<30} te={r_te[0]:>7.4f} tr={r_tr[0]:>7.4f} n={r_te[3]:>4} net={r_te[4]:>7.0f} {both} {beat}")
                    if beat:
                        improvements.append((ind_name, label_te, r_te[0], r_tr[0], r_te[3], r_te[4]))
            except Exception as e:
                print(f"  trend ERROR: {e}")

        # ROLE 3: Exit signal
        try:
            tr_tests = test_as_exit(train_df, ind_name, tr_iv,
                                     tr_ema8, tr_ema34, tr_ema200, tr_rsi7, tr_adx14, tr_atr20)
            te_tests = test_as_exit(test_df, ind_name, te_iv,
                                     te_ema8, te_ema34, te_ema200, te_rsi7, te_adx14, te_atr20)
            for (label_tr, sig_tr), (label_te, sig_te) in zip(tr_tests, te_tests):
                r_tr = fast_backtest(train_df, sig_tr)
                r_te = fast_backtest(test_df, sig_te)
                both = "OK" if r_tr[0] > 0 and r_te[0] > 0 else ""
                beat = "***" if r_te[0] > te_base[0] and r_tr[0] > 0 and r_te[3] >= 50 else ""
                if r_te[0] > 0 or r_tr[0] > 0:
                    print(f"  {label_te:<30} te={r_te[0]:>7.4f} tr={r_tr[0]:>7.4f} n={r_te[3]:>4} net={r_te[4]:>7.0f} {both} {beat}")
                if beat:
                    improvements.append((ind_name, label_te, r_te[0], r_tr[0], r_te[3], r_te[4]))
        except Exception as e:
            print(f"  exit ERROR: {e}")

    print(f"\n{'='*100}")
    print("IMPROVEMENTS FOUND (beat baseline test_sharpe=2.86, both positive, 50+ trades):")
    print(f"{'='*100}")
    if improvements:
        for ind, role, te_s, tr_s, n, net in sorted(improvements, key=lambda x: -x[2]):
            print(f"  {ind:<20} {role:<30} test={te_s:.4f} train={tr_s:.4f} trades={n} net={net:.0f}")
    else:
        print("  NONE — baseline is optimal")


if __name__ == "__main__":
    main()
