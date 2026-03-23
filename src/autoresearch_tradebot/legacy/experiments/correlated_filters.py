"""
test_correlated.py — Use DXY, VIX, USDBRL as regime filters.
CRITICAL: All external data uses PREVIOUS day (D-1) only — no lookahead.
"""
import numpy as np
import pandas as pd
import ta

from ...common.paths import DATA_DIR
from ..prepare import load_data, split_data, add_session_markers
from ..sweep_params import fast_backtest


def load_external():
    """Load and prepare external daily data."""
    dxy = pd.read_parquet(DATA_DIR / "dxy_daily.parquet")
    vix = pd.read_parquet(DATA_DIR / "vix_daily.parquet")
    usdbrl = pd.read_parquet(DATA_DIR / "usdbrl_daily.parquet")

    # Flatten multi-level columns
    dxy.columns = [c[0] for c in dxy.columns]
    vix.columns = [c[0] for c in vix.columns]
    usdbrl.columns = [c[0] for c in usdbrl.columns]

    return dxy, vix, usdbrl


def gen_with_external(df, dxy, vix, usdbrl, variant="baseline"):
    """Strategy with external data as regime filters."""
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    trend = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx_val = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = trend.values; av = adx_val.values; at_ = atr.values
    is_last = df["is_last_30min"].values; is_first = df["is_first_bar"].values
    br = df["bars_remaining"].values; dates = df["date"].values; times = df["time"].values

    # Prepare external signals — ALWAYS use D-1 (previous day)
    # DXY features
    dxy_ret = dxy["Close"].pct_change()
    dxy_sma20 = dxy["Close"].rolling(20).mean()
    dxy_above_sma = (dxy["Close"] > dxy_sma20).astype(int)
    dxy_ret_prev = dxy_ret.shift(1)  # D-1 return
    dxy_trend_prev = dxy_above_sma.shift(1)  # D-1 trend

    # VIX features
    vix_close = vix["Close"]
    vix_sma20 = vix_close.rolling(20).mean()
    vix_high = (vix_close > vix_sma20).shift(1)  # D-1: VIX above average
    vix_level_prev = vix_close.shift(1)

    # USDBRL features
    brl_ret = usdbrl["Close"].pct_change()
    brl_ret_prev = brl_ret.shift(1)  # D-1 return
    brl_sma20 = usdbrl["Close"].rolling(20).mean()
    brl_trend_prev = (usdbrl["Close"] > brl_sma20).shift(1).astype(float)

    # Map to trading dates
    def map_to_date(series, target_dates):
        """Map daily series to intraday dates using D-1 convention."""
        result = {}
        s_dict = series.to_dict()
        sorted_dates = sorted(s_dict.keys())
        for d in target_dates:
            d_ts = pd.Timestamp(d)
            val = np.nan
            for sd in reversed(sorted_dates):
                if sd < d_ts:
                    val = s_dict[sd]
                    break
            result[d] = val
        return result

    unique_dates = sorted(set(dates))
    dxy_ret_map = map_to_date(dxy_ret_prev, unique_dates)
    dxy_trend_map = map_to_date(dxy_trend_prev, unique_dates)
    vix_high_map = map_to_date(vix_high, unique_dates)
    vix_level_map = map_to_date(vix_level_prev, unique_dates)
    brl_ret_map = map_to_date(brl_ret_prev, unique_dates)
    brl_trend_map = map_to_date(brl_trend_prev, unique_dates)

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
        if av[i] < 20 or br[i] <= 36: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50

        # Get external signals for this date
        dr = dxy_ret_map.get(d, 0)
        dt_ = dxy_trend_map.get(d, 0)
        vh = vix_high_map.get(d, 0)
        vl = vix_level_map.get(d, 20)
        br_ = brl_ret_map.get(d, 0)
        bt = brl_trend_map.get(d, 0)

        # Handle NaN
        if dr is None or np.isnan(dr): dr = 0
        if dt_ is None or np.isnan(dt_): dt_ = 0
        if vh is None or np.isnan(vh): vh = 0
        if vl is None or np.isnan(vl): vl = 20
        if br_ is None or np.isnan(br_): br_ = 0
        if bt is None or np.isnan(bt): bt = 0

        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]

            long_ok = cross_up and close[i] > tv[i] and r > 65
            short_ok = cross_dn and close[i] < tv[i] and r < 45

            # Apply external filters based on variant
            if variant == "dxy_trend":
                # DXY rising = USD strengthening = good for WDO shorts (inverse)
                # DXY above SMA20: favor shorts. DXY below SMA20: favor longs
                if long_ok and dt_ == 1: long_ok = False  # DXY strong = bad for longs
                if short_ok and dt_ == 0: short_ok = False  # DXY weak = bad for shorts

            elif variant == "dxy_momentum":
                # DXY went up yesterday -> WDO likely goes up (same direction for USD assets)
                if long_ok and dr < 0: long_ok = False
                if short_ok and dr > 0: short_ok = False

            elif variant == "dxy_contrarian":
                # DXY went up -> WDO reverses (mean reversion across assets)
                if long_ok and dr > 0: long_ok = False
                if short_ok and dr < 0: short_ok = False

            elif variant == "vix_low":
                # Only trade when VIX is below average (low fear = stable trends)
                if vh == 1:
                    long_ok = False; short_ok = False

            elif variant == "vix_high":
                # Only trade when VIX is high (volatile = bigger moves)
                if vh == 0:
                    long_ok = False; short_ok = False

            elif variant == "vix_under_25":
                # Only trade when VIX < 25
                if vl >= 25:
                    long_ok = False; short_ok = False

            elif variant == "brl_momentum":
                # USDBRL went up = BRL weakened = WDO goes up
                if long_ok and br_ < 0: long_ok = False
                if short_ok and br_ > 0: short_ok = False

            elif variant == "brl_contrarian":
                # USDBRL went up = BRL weakened -> WDO reverses
                if long_ok and br_ > 0: long_ok = False
                if short_ok and br_ < 0: short_ok = False

            elif variant == "combined_momentum":
                # DXY up + BRL down = strong USD trend -> WDO longs
                if long_ok and (dr <= 0 or br_ >= 0): long_ok = False
                if short_ok and (dr >= 0 or br_ <= 0): short_ok = False

            if long_ok:
                sig[i] = 1; pos = 1; peak = close[i]
            elif short_ok:
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

    dxy, vix, usdbrl = load_external()

    variants = [
        "baseline",
        "dxy_trend",
        "dxy_momentum",
        "dxy_contrarian",
        "vix_low",
        "vix_high",
        "vix_under_25",
        "brl_momentum",
        "brl_contrarian",
        "combined_momentum",
    ]

    print(f"{'Variant':<25} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8}")
    print("-" * 70)
    for v in variants:
        try:
            sig_tr = gen_with_external(train_df, dxy, vix, usdbrl, variant=v)
            sig_te = gen_with_external(test_df, dxy, vix, usdbrl, variant=v)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            print(f"  {v:<23} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>6} {te[4]:>8.0f}  [{both}]")
        except Exception as e:
            print(f"  {v:<23} ERROR: {e}")


if __name__ == "__main__":
    main()
