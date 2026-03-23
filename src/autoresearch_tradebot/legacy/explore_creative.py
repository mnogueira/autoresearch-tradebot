"""
explore_creative.py — Unconventional approaches beyond traditional indicators.
Entropy, wavelets, fractals, order flow, statistical patterns.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from .sweep_params import fast_backtest


# ============================================================
# UNCONVENTIONAL SIGNAL SOURCES
# ============================================================

def shannon_entropy(close, window=50):
    """Shannon entropy of return distribution. Low = predictable = trend."""
    returns = close.pct_change()
    def calc_entropy(x):
        x = x[~np.isnan(x)]
        if len(x) < 10: return np.nan
        # Discretize returns into bins
        hist, _ = np.histogram(x, bins=10, density=True)
        hist = hist[hist > 0]
        return -np.sum(hist * np.log2(hist + 1e-10))
    return returns.rolling(window).apply(calc_entropy, raw=True)


def approx_entropy(close, window=50, m=2, r_mult=0.2):
    """Approximate Entropy (ApEn) — low = regular/predictable, high = random."""
    def apen(series):
        x = np.array(series)
        if len(x) < m + 10: return np.nan
        N = len(x)
        r = r_mult * x.std()
        if r == 0: return np.nan

        def phi(m_val):
            patterns = np.array([x[i:i+m_val] for i in range(N - m_val + 1)])
            C = np.zeros(len(patterns))
            for i in range(len(patterns)):
                dist = np.max(np.abs(patterns - patterns[i]), axis=1)
                C[i] = np.sum(dist <= r) / len(patterns)
            return np.mean(np.log(C + 1e-10))

        return phi(m) - phi(m + 1)
    return close.rolling(window).apply(apen, raw=True)


def order_flow_imbalance(high, low, close, volume):
    """Approximate buy/sell volume from OHLCV bars (no tick data needed).
    Uses close position within bar: close near high = buying, near low = selling."""
    bar_range = high - low
    bar_range = bar_range.replace(0, np.nan)
    close_position = (close - low) / bar_range  # 0=close at low, 1=close at high
    buy_vol = close_position * volume
    sell_vol = (1 - close_position) * volume
    ofi = (buy_vol - sell_vol).rolling(20).sum()
    ofi_norm = ofi / volume.rolling(20).sum()
    return ofi_norm


def price_acceleration(close, fast=5, slow=20):
    """Rate of change of momentum — detects trend acceleration/deceleration."""
    mom_fast = close.pct_change(fast)
    mom_slow = close.pct_change(slow)
    accel = mom_fast - mom_slow
    return accel


def volatility_ratio(close, fast=5, slow=50):
    """Ratio of short-term to long-term volatility. >1 = expanding, <1 = contracting."""
    ret = close.pct_change()
    vol_fast = ret.rolling(fast).std()
    vol_slow = ret.rolling(slow).std()
    return vol_fast / vol_slow


def range_expansion(high, low, close, window=20):
    """Today's range vs average range — identifies breakout days."""
    daily_range = high - low
    avg_range = daily_range.rolling(window).mean()
    return daily_range / avg_range


def gap_momentum(df):
    """Opening gap direction + first 30min momentum."""
    # Compute daily open vs previous close
    daily_open = df.groupby("date")["Open"].first()
    daily_prev_close = df.groupby("date")["Close"].last().shift(1)
    gap = (daily_open - daily_prev_close) / daily_prev_close * 100
    return gap


def intraday_vwap_distance(df):
    """Distance from intraday VWAP — positive = above, negative = below."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tp_vol = (typical * df["Volume"]).groupby(df.index.date).cumsum()
    cum_vol = df["Volume"].groupby(df.index.date).cumsum().replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol
    dist = (df["Close"] - vwap) / df["Close"] * 100
    return dist


def consecutive_bars(close):
    """Count consecutive up/down bars. Streaks = momentum persistence."""
    direction = np.sign(close.diff())
    streak = pd.Series(0.0, index=close.index)
    for i in range(1, len(close)):
        if direction.iloc[i] == direction.iloc[i-1] and direction.iloc[i] != 0:
            streak.iloc[i] = streak.iloc[i-1] + direction.iloc[i]
        else:
            streak.iloc[i] = direction.iloc[i]
    return streak


# ============================================================
# STRATEGY GENERATOR WITH CREATIVE SIGNALS
# ============================================================

def gen(df, variant="baseline"):
    """Base strategy + creative signal overlay."""
    # Core indicators (same as best strategy)
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema220 = ta.trend.ema_indicator(df["Close"], window=220)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix12 = ta.trend.trix(df["Close"], window=12)

    def rolling_hurst(close, window=100):
        def hurst_rs(series):
            ts = np.array(series); returns = np.diff(ts) / ts[:-1]
            if len(returns) < 10: return 0.5
            mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
            r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
            if s == 0 or r == 0: return 0.5
            return np.log(r / s) / np.log(len(returns))
        return close.rolling(window).apply(hurst_rs, raw=True)

    hurst = rolling_hurst(df["Close"], window=100)
    trix_med = trix12.rolling(500, min_periods=100).median().shift(1)

    # Creative signals based on variant
    extras = {}
    if "entropy" in variant:
        extras["entropy"] = shannon_entropy(df["Close"], window=50).values
    if "apen" in variant:
        extras["apen"] = approx_entropy(df["Close"], window=30, m=2, r_mult=0.2).values
    if "ofi" in variant:
        extras["ofi"] = order_flow_imbalance(df["High"], df["Low"], df["Close"], df["Volume"]).values
    if "accel" in variant:
        extras["accel"] = price_acceleration(df["Close"], fast=5, slow=20).values
    if "volratio" in variant:
        extras["volratio"] = volatility_ratio(df["Close"], fast=5, slow=50).values
    if "rangeexp" in variant:
        extras["rangeexp"] = range_expansion(df["High"], df["Low"], df["Close"]).values
    if "vwap_dist" in variant:
        extras["vwap_dist"] = intraday_vwap_distance(df).values
    if "streak" in variant:
        extras["streak"] = consecutive_bars(df["Close"]).values

    c = df["Close"].values; e8 = ema8.values; e34 = ema34.values
    rv = rsi7.values; tv = ema220.values; av = adx14.values
    at_ = atr20.values; txv = trix12.values; tmv = trix_med.values; hv = hurst.values
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

        # EXIT (same for all)
        if pos != 0:
            ca = at_[i] if not np.isnan(at_[i]) else 0
            tm = tmv[i] if not np.isnan(tmv[i]) else 0
            fv = txv[i] if not np.isnan(txv[i]) else tm
            fp = txv[i-1] if i > 0 and not np.isnan(txv[i-1]) else tm
            trix_exit = (pos == 1 and fv < tm and fp >= tm) or (pos == -1 and fv > tm and fp <= tm)
            if trix_exit:
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

        r = rv[i] if not np.isnan(rv[i]) else 50

        # Creative entry filters
        if "entropy_filter" in variant and "entropy" in extras:
            ev = extras["entropy"][i]
            if not np.isnan(ev):
                # Low entropy = predictable = good for trend. Median split.
                if ev > 3.0: prev_date = d; continue  # high entropy = random, skip

        if "ofi_confirm" in variant and "ofi" in extras:
            ov = extras["ofi"][i]
            if not np.isnan(ov):
                # Only long if buy pressure > 0, short if sell pressure < 0
                pass  # applied in crossover block below

        if "volratio_filter" in variant and "volratio" in extras:
            vr = extras["volratio"][i]
            if not np.isnan(vr):
                if vr < 0.8: prev_date = d; continue  # volatility contracting, skip

        if "accel_confirm" in variant and "accel" in extras:
            ac = extras["accel"][i]
            if not np.isnan(ac):
                pass  # applied below

        # ENTRY
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cu = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cd = e8[i] < e34[i] and e8[i-1] >= e34[i-1]

            long_ok = cu and c[i] > tv[i] and r > 65
            short_ok = cd and c[i] < tv[i] and r < 40

            # Apply creative confirmations
            if "ofi_confirm" in variant and "ofi" in extras:
                ov = extras["ofi"][i]
                if not np.isnan(ov):
                    if long_ok and ov < 0: long_ok = False
                    if short_ok and ov > 0: short_ok = False

            if "accel_confirm" in variant and "accel" in extras:
                ac = extras["accel"][i]
                if not np.isnan(ac):
                    if long_ok and ac < 0: long_ok = False
                    if short_ok and ac > 0: short_ok = False

            if "streak_confirm" in variant and "streak" in extras:
                sk = extras["streak"][i]
                if not np.isnan(sk):
                    if long_ok and sk < 2: long_ok = False
                    if short_ok and sk > -2: short_ok = False

            if "vwap_confirm" in variant and "vwap_dist" in extras:
                vd = extras["vwap_dist"][i]
                if not np.isnan(vd):
                    if long_ok and vd < 0: long_ok = False  # only long above VWAP
                    if short_ok and vd > 0: short_ok = False

            if long_ok:
                sig[i] = 1; pos = 1; peak = c[i]
            elif short_ok:
                sig[i] = -1; pos = -1; peak = c[i]

        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


# ============================================================
# STANDALONE CREATIVE ENTRIES (replace EMA crossover entirely)
# ============================================================

def gen_standalone(df, variant="entropy_reversal"):
    """Completely different entry mechanisms — not EMA crossover based."""
    ema220 = ta.trend.ema_indicator(df["Close"], window=220)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix12 = ta.trend.trix(df["Close"], window=12)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)

    def rolling_hurst(close, window=100):
        def hurst_rs(series):
            ts = np.array(series); returns = np.diff(ts) / ts[:-1]
            if len(returns) < 10: return 0.5
            mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
            r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
            if s == 0 or r == 0: return 0.5
            return np.log(r / s) / np.log(len(returns))
        return close.rolling(window).apply(hurst_rs, raw=True)

    hurst = rolling_hurst(df["Close"], window=100)
    trix_med = trix12.rolling(500, min_periods=100).median().shift(1)

    ofi = order_flow_imbalance(df["High"], df["Low"], df["Close"], df["Volume"])
    accel = price_acceleration(df["Close"])
    streak = consecutive_bars(df["Close"])
    volratio = volatility_ratio(df["Close"])
    rsi7 = ta.momentum.rsi(df["Close"], window=7)

    c = df["Close"].values; tv = ema220.values; av = adx14.values
    at_ = atr20.values; txv = trix12.values; tmv = trix_med.values; hv = hurst.values
    ofi_v = ofi.values; ac_v = accel.values; sk_v = streak.values; vr_v = volratio.values
    rv = rsi7.values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date: pos = 0; prev_date = d; continue
        if il[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        # EXIT (same TRIX + ATR)
        if pos != 0:
            ca = at_[i] if not np.isnan(at_[i]) else 0
            tm = tmv[i] if not np.isnan(tmv[i]) else 0
            fv = txv[i] if not np.isnan(txv[i]) else tm
            fp = txv[i-1] if i > 0 and not np.isnan(txv[i-1]) else tm
            trix_exit = (pos == 1 and fv < tm and fp >= tm) or (pos == -1 and fv > tm and fp <= tm)
            if trix_exit: sig[i] = 0; pos = 0
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

        h = hv[i]
        if not np.isnan(h) and h < 0.50: prev_date = d; continue

        # STANDALONE ENTRIES
        if variant == "ofi_momentum":
            # Order flow imbalance momentum: strong buy pressure = long
            ov = ofi_v[i] if not np.isnan(ofi_v[i]) else 0
            ov_prev = ofi_v[i-1] if i > 0 and not np.isnan(ofi_v[i-1]) else 0
            if ov > 0.1 and ov_prev <= 0.1 and c[i] > tv[i] and av[i] > 20:
                sig[i] = 1; pos = 1; peak = c[i]
            elif ov < -0.1 and ov_prev >= -0.1 and c[i] < tv[i] and av[i] > 20:
                sig[i] = -1; pos = -1; peak = c[i]

        elif variant == "accel_breakout":
            # Price acceleration breakout: acceleration crosses zero = trend start
            ac = ac_v[i] if not np.isnan(ac_v[i]) else 0
            ac_prev = ac_v[i-1] if i > 0 and not np.isnan(ac_v[i-1]) else 0
            r = rv[i] if not np.isnan(rv[i]) else 50
            if ac > 0 and ac_prev <= 0 and c[i] > tv[i] and av[i] > 20 and r > 55:
                sig[i] = 1; pos = 1; peak = c[i]
            elif ac < 0 and ac_prev >= 0 and c[i] < tv[i] and av[i] > 20 and r < 45:
                sig[i] = -1; pos = -1; peak = c[i]

        elif variant == "streak_momentum":
            # Enter after 3+ consecutive bars in same direction
            sk = sk_v[i] if not np.isnan(sk_v[i]) else 0
            if sk >= 3 and c[i] > tv[i] and av[i] > 20:
                sig[i] = 1; pos = 1; peak = c[i]
            elif sk <= -3 and c[i] < tv[i] and av[i] > 20:
                sig[i] = -1; pos = -1; peak = c[i]

        elif variant == "volratio_breakout":
            # Volatility expansion + trend direction
            vr = vr_v[i] if not np.isnan(vr_v[i]) else 1
            vr_prev = vr_v[i-1] if i > 0 and not np.isnan(vr_v[i-1]) else 1
            r = rv[i] if not np.isnan(rv[i]) else 50
            if vr > 1.5 and vr_prev <= 1.5 and c[i] > tv[i] and av[i] > 20 and r > 55:
                sig[i] = 1; pos = 1; peak = c[i]
            elif vr > 1.5 and vr_prev <= 1.5 and c[i] < tv[i] and av[i] > 20 and r < 45:
                sig[i] = -1; pos = -1; peak = c[i]

        elif variant == "combined_creative":
            # OFI + acceleration + RSI all confirming
            ov = ofi_v[i] if not np.isnan(ofi_v[i]) else 0
            ac = ac_v[i] if not np.isnan(ac_v[i]) else 0
            r = rv[i] if not np.isnan(rv[i]) else 50
            if ov > 0 and ac > 0 and r > 60 and c[i] > tv[i] and av[i] > 20:
                sig[i] = 1; pos = 1; peak = c[i]
            elif ov < 0 and ac < 0 and r < 40 and c[i] < tv[i] and av[i] > 20:
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

    print("=" * 90)
    print("CREATIVE FILTERS ON TOP OF BEST STRATEGY")
    print("=" * 90)
    filter_variants = [
        ("BASELINE", "baseline"),
        ("Entropy < 3.0 filter", "entropy_filter_entropy"),
        ("OFI direction confirm", "ofi_confirm_ofi"),
        ("Price accel confirm", "accel_confirm_accel"),
        ("Vol ratio > 0.8 filter", "volratio_filter_volratio"),
        ("Streak >= 2 confirm", "streak_confirm_streak"),
        ("VWAP direction confirm", "vwap_confirm_vwap_dist"),
        ("OFI + accel combo", "ofi_confirm_accel_confirm_ofi_accel"),
    ]

    print(f"{'Variant':<30} {'test':>8} {'train':>8} {'PF':>6} {'n':>4} {'net':>8}")
    print("-" * 70)
    for name, v in filter_variants:
        try:
            sig_tr = gen(train_df, variant=v)
            sig_te = gen(test_df, variant=v)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            beat = "***" if te[0] > 3.3141 and tr[0] > 0 and te[3] >= 50 else ""
            print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>4} {te[4]:>8.0f} [{both}] {beat}")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")

    print(f"\n{'='*90}")
    print("STANDALONE CREATIVE ENTRIES (replace EMA crossover)")
    print("=" * 90)
    standalone_variants = [
        ("OFI momentum entry", "ofi_momentum"),
        ("Price accel breakout", "accel_breakout"),
        ("3-bar streak entry", "streak_momentum"),
        ("Vol ratio breakout", "volratio_breakout"),
        ("Combined creative", "combined_creative"),
    ]

    print(f"{'Variant':<30} {'test':>8} {'train':>8} {'PF':>6} {'n':>4} {'net':>8}")
    print("-" * 70)
    for name, v in standalone_variants:
        try:
            sig_tr = gen_standalone(train_df, variant=v)
            sig_te = gen_standalone(test_df, variant=v)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            beat = "***" if te[0] > 3.3141 and tr[0] > 0 and te[3] >= 50 else ""
            print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>4} {te[4]:>8.0f} [{both}] {beat}")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")


if __name__ == "__main__":
    main()
