"""
test_stalker.py — Proper Stalker strategy implementation with parameter sweeps.
Dynamic Fibonacci retracement from intraday high/low.
Test in ALL roles: standalone entry, entry confirmation, exit, trend filter.
Sweep: retracement level, ATR stop/target multipliers, meia perna threshold.
"""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from ..sweep_params import fast_backtest


def rolling_hurst(close, window=100):
    def hurst_rs(series):
        ts = np.array(series); returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10: return 0.5
        mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
        if s == 0 or r == 0: return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def gen_stalker(df, retrace=0.25, use_meia_perna=True, mp_thresh=0.30, mp_window=10,
                use_atr_tp=False, tp_mult=0.36, sl_mult=0.78,
                role="standalone", min_range_pts=0):
    """
    Stalker-style dynamic Fibonacci retracement.

    When price makes a new intraday high, compute retracement level = high - range*retrace.
    If price pulls back to that level, go long (trend continuation).
    Vice versa for shorts.

    Roles:
    - standalone: Stalker entry + our best exit (TRIX + ATR trailing)
    - confirm: EMA crossover must happen AND price is near Fib level
    - entry_only: Stalker entry replaces EMA crossover, keeps all filters
    """
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema220 = ta.trend.ema_indicator(df["Close"], window=220)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix12 = ta.trend.trix(df["Close"], window=12)
    hurst = rolling_hurst(df["Close"], window=100)
    trix_med = trix12.rolling(500, min_periods=100).median().shift(1)
    ret = df["Close"].pct_change()
    vr = ret.rolling(3).std() / ret.rolling(20).std()

    # Daily range for meia perna
    daily_ranges = df.groupby("date").apply(lambda g: g["High"].max() - g["Low"].min())
    avg_range = daily_ranges.rolling(window=mp_window, min_periods=3).mean().shift(1)
    avg_range_map = avg_range.to_dict()

    c = df["Close"].values; h = df["High"].values; l = df["Low"].values
    o = df["Open"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = ema220.values; av = adx14.values; at_ = atr20.values
    txv = trix12.values; tmv = trix_med.values; hv = hurst.values; vrv = vr.values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0
    day_high = 0.0; day_low = 1e9
    prev_day_high = 0.0; prev_day_low = 1e9
    made_new_high = False; made_new_low = False
    entry_price_for_tp = 0.0

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date:
            pos = 0; prev_date = d
            prev_day_high = day_high; prev_day_low = day_low
            day_high = h[i]; day_low = l[i]
            made_new_high = False; made_new_low = False
            continue
        if il[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue

        # Track intraday high/low
        if h[i] > day_high:
            day_high = h[i]; made_new_high = True
        if l[i] < day_low:
            day_low = l[i]; made_new_low = True

        if np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        # EXIT: TRIX + ATR trailing (same as best strategy)
        if pos != 0:
            ca = at_[i] if not np.isnan(at_[i]) else 0
            tm = tmv[i] if not np.isnan(tmv[i]) else 0
            fv = txv[i] if not np.isnan(txv[i]) else tm
            fp = txv[i-1] if i > 0 and not np.isnan(txv[i-1]) else tm
            trix_exit = (pos == 1 and fv < tm and fp >= tm) or (pos == -1 and fv > tm and fp <= tm)

            # ATR-based TP/SL (Stalker style)
            tp_exit = False
            if use_atr_tp and ca > 0:
                if pos == 1 and c[i] >= entry_price_for_tp + tp_mult * ca:
                    tp_exit = True
                elif pos == -1 and c[i] <= entry_price_for_tp - tp_mult * ca:
                    tp_exit = True

            if trix_exit or tp_exit:
                sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, c[i])
                if ca > 0 and c[i] < peak - 2 * ca:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            elif pos == -1:
                peak = min(peak, c[i])
                if ca > 0 and c[i] > peak + 2 * ca:
                    sig[i] = 0; pos = 0
                else:
                    sig[i] = pos
            prev_date = d; continue

        # ENTRY FILTERS
        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour in (12, 13): prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue
        if av[i] < 20: prev_date = d; continue
        hval = hv[i]
        if not np.isnan(hval) and hval < 0.50: prev_date = d; continue
        v = vrv[i]
        if not np.isnan(v) and v > 2.0: prev_date = d; continue

        # Meia perna: daily range must exceed threshold of avg range
        if use_meia_perna:
            avg_r = avg_range_map.get(d, None)
            if avg_r is not None and not np.isnan(avg_r):
                today_range = day_high - day_low
                if today_range < mp_thresh * avg_r:
                    prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        day_range = day_high - day_low

        if role == "standalone" or role == "entry_only":
            # Stalker entry: pullback to Fibonacci retracement level
            if day_range > min_range_pts:
                upper_retrace = day_high - day_range * retrace
                lower_retrace = day_low + day_range * retrace

                # Long: price made new high, then pulled back to retracement
                if made_new_high and c[i] > tv[i] and r > 55:
                    if l[i] <= upper_retrace and c[i] >= upper_retrace:
                        sig[i] = 1; pos = 1; peak = c[i]; entry_price_for_tp = c[i]
                # Short: price made new low, then bounced to retracement
                elif made_new_low and c[i] < tv[i] and r < 45:
                    if h[i] >= lower_retrace and c[i] <= lower_retrace:
                        sig[i] = -1; pos = -1; peak = c[i]; entry_price_for_tp = c[i]

        elif role == "confirm":
            # EMA crossover + pullback near Fib level
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cu = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cd = e8[i] < e34[i] and e8[i-1] >= e34[i-1]

                if day_range > 0:
                    upper_retrace = day_high - day_range * retrace
                    lower_retrace = day_low + day_range * retrace
                    # Long: crossover + price near upper retracement
                    near_retrace_long = abs(c[i] - upper_retrace) / day_range < 0.1 if day_range > 0 else False
                    near_retrace_short = abs(c[i] - lower_retrace) / day_range < 0.1 if day_range > 0 else False
                else:
                    near_retrace_long = True; near_retrace_short = True

                if cu and c[i] > tv[i] and r > 65:
                    sig[i] = 1; pos = 1; peak = c[i]; entry_price_for_tp = c[i]
                elif cd and c[i] < tv[i] and r < 40:
                    sig[i] = -1; pos = -1; peak = c[i]; entry_price_for_tp = c[i]

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
    print("STALKER STRATEGY — PROPER PARAMETER SWEEP IN ALL ROLES")
    print("=" * 90)

    configs = [
        # Standalone entry — sweep retracement levels
        ("Stalker ret=0.15 standalone", dict(retrace=0.15, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.20 standalone", dict(retrace=0.20, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.25 standalone", dict(retrace=0.25, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.30 standalone", dict(retrace=0.30, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.35 standalone", dict(retrace=0.35, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.40 standalone", dict(retrace=0.40, role="standalone", use_meia_perna=False)),
        ("Stalker ret=0.50 standalone", dict(retrace=0.50, role="standalone", use_meia_perna=False)),
        # With meia perna
        ("ret=0.25 + MP 30%", dict(retrace=0.25, role="standalone", use_meia_perna=True, mp_thresh=0.30)),
        ("ret=0.25 + MP 20%", dict(retrace=0.25, role="standalone", use_meia_perna=True, mp_thresh=0.20)),
        ("ret=0.25 + MP 40%", dict(retrace=0.25, role="standalone", use_meia_perna=True, mp_thresh=0.40)),
        ("ret=0.30 + MP 30%", dict(retrace=0.30, role="standalone", use_meia_perna=True, mp_thresh=0.30)),
        # With ATR target (Stalker style tight TP)
        ("ret=0.25 + TP 0.36xATR", dict(retrace=0.25, role="standalone", use_meia_perna=False, use_atr_tp=True, tp_mult=0.36)),
        ("ret=0.25 + TP 1.0xATR", dict(retrace=0.25, role="standalone", use_meia_perna=False, use_atr_tp=True, tp_mult=1.0)),
        ("ret=0.25 + TP 2.0xATR", dict(retrace=0.25, role="standalone", use_meia_perna=False, use_atr_tp=True, tp_mult=2.0)),
        # Wider retracement + meia perna + TP
        ("ret=0.35 + MP20 + TP1x", dict(retrace=0.35, role="standalone", use_meia_perna=True, mp_thresh=0.20, use_atr_tp=True, tp_mult=1.0)),
        ("ret=0.40 + MP20 + TP2x", dict(retrace=0.40, role="standalone", use_meia_perna=True, mp_thresh=0.20, use_atr_tp=True, tp_mult=2.0)),
        # As confirmation on EMA crossover
        ("ret=0.25 confirm", dict(retrace=0.25, role="confirm")),
        ("ret=0.30 confirm", dict(retrace=0.30, role="confirm")),
    ]

    print(f"{'Config':<30} {'test':>8} {'train':>8} {'PF':>6} {'n':>4} {'net':>8}")
    print("-" * 70)

    for name, kw in configs:
        try:
            sig_tr = gen_stalker(train_df, **kw)
            sig_te = gen_stalker(test_df, **kw)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            beat = "***" if te[0] > 3.56 and tr[0] > 0 and te[3] >= 50 else ("+" if te[0] > 2.0 and tr[0] > 0 else "")
            if te[3] > 0:  # Only print if any trades
                print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>4} {te[4]:>8.0f} [{both}] {beat}")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")


if __name__ == "__main__":
    main()
