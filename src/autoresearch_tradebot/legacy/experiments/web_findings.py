"""
test_webfindings.py — Test top indicators from web research.
KER regime filter, KAMA crossover, TTM Squeeze, Choppiness Index, Supertrend.
"""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from ..sweep_params import fast_backtest


def efficiency_ratio(close, period=10):
    """Kaufman Efficiency Ratio: 0=choppy, 1=trending."""
    change = abs(close - close.shift(period))
    volatility = close.diff().abs().rolling(period).sum()
    return change / volatility


def choppiness_index(high, low, close, period=14):
    """Choppiness Index: <38.2=trending, >61.8=ranging."""
    atr1 = ta.volatility.average_true_range(high, low, close, window=1)
    atr_sum = atr1.rolling(period).sum()
    hl_range = high.rolling(period).max() - low.rolling(period).min()
    hl_range = hl_range.replace(0, np.nan)
    return 100 * np.log10(atr_sum / hl_range) / np.log10(period)


def ttm_squeeze(high, low, close):
    """TTM Squeeze: BB inside KC = squeeze on. Squeeze release = entry."""
    bb_h = ta.volatility.bollinger_hband(close, window=20, window_dev=2.0)
    bb_l = ta.volatility.bollinger_lband(close, window=20, window_dev=2.0)
    kc_h = ta.volatility.keltner_channel_hband(high, low, close, window=20)
    kc_l = ta.volatility.keltner_channel_lband(high, low, close, window=20)
    squeeze_on = (bb_l > kc_l) & (bb_h < kc_h)
    return squeeze_on


def supertrend(high, low, close, period=10, multiplier=3.0):
    """Supertrend indicator: 1=uptrend, -1=downtrend."""
    atr = ta.volatility.average_true_range(high, low, close, window=period)
    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    st = pd.Series(0.0, index=close.index)
    direction = pd.Series(1, index=close.index)

    for i in range(1, len(close)):
        if np.isnan(upper.iloc[i]) or np.isnan(lower.iloc[i]):
            st.iloc[i] = st.iloc[i-1]
            direction.iloc[i] = direction.iloc[i-1]
            continue

        if close.iloc[i] > upper.iloc[i-1] if direction.iloc[i-1] == -1 else close.iloc[i] > lower.iloc[i-1]:
            direction.iloc[i] = 1
            st.iloc[i] = max(lower.iloc[i], st.iloc[i-1] if direction.iloc[i-1] == 1 else lower.iloc[i])
        else:
            direction.iloc[i] = -1
            st.iloc[i] = min(upper.iloc[i], st.iloc[i-1] if direction.iloc[i-1] == -1 else upper.iloc[i])

    return direction, st


def gen(df, variant="baseline"):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix15 = ta.trend.trix(df["Close"], window=15)

    # Extra indicators based on variant
    if "ker" in variant:
        ker = efficiency_ratio(df["Close"], period=10)
        ker_v = ker.values
    if "chop" in variant:
        chop = choppiness_index(df["High"], df["Low"], df["Close"], period=14)
        chop_v = chop.values
    if "squeeze" in variant:
        sq = ttm_squeeze(df["High"], df["Low"], df["Close"])
        sq_v = sq.values
    if "kama" in variant:
        kama10 = ta.momentum.kama(df["Close"], window=10)
        kama_v = kama10.values
    if "psar" in variant:
        psar_u = ta.trend.psar_up(df["High"], df["Low"], df["Close"])
        psar_d = ta.trend.psar_down(df["High"], df["Low"], df["Close"])
        psar_uv = psar_u.values
        psar_dv = psar_d.values

    close = df["Close"].values
    e8 = ema8.values; e34 = ema34.values; rv = rsi7.values
    tv = ema200.values; av = adx14.values; at_ = atr20.values
    trix_v = trix15.values
    valid_trix = trix_v[~np.isnan(trix_v)]
    trix_med = float(np.median(valid_trix)) if len(valid_trix) > 0 else 0.0
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
            fv = trix_v[i] if not np.isnan(trix_v[i]) else trix_med
            fv_prev = trix_v[i-1] if i > 0 and not np.isnan(trix_v[i-1]) else trix_med
            trix_exit = False
            if pos == 1 and fv < trix_med and fv_prev >= trix_med: trix_exit = True
            elif pos == -1 and fv > trix_med and fv_prev <= trix_med: trix_exit = True

            # Parabolic SAR exit variant
            psar_exit = False
            if "psar_exit" in variant:
                if pos == 1 and not np.isnan(psar_dv[i]) and np.isnan(psar_uv[i]):
                    psar_exit = True  # SAR flipped to downtrend
                elif pos == -1 and not np.isnan(psar_uv[i]) and np.isnan(psar_dv[i]):
                    psar_exit = True

            if trix_exit or psar_exit: sig[i] = 0; pos = 0
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

        # KER regime filter: only trade when market is trending
        if "ker" in variant:
            k = ker_v[i] if not np.isnan(ker_v[i]) else 0
            thresh = float(variant.split("ker")[1].split("_")[0]) if "ker" in variant else 0.3
            if k < thresh: prev_date = d; continue

        # Choppiness filter
        if "chop" in variant:
            cv = chop_v[i] if not np.isnan(chop_v[i]) else 50
            if cv > 50: prev_date = d; continue

        # Squeeze timing
        if "squeeze" in variant:
            if i > 0:
                prev_sq = sq_v[i-1] if not np.isnan(sq_v[i-1]) else False
                curr_sq = sq_v[i] if not np.isnan(sq_v[i]) else False
                # Only enter on squeeze release (was on, now off)
                if not (prev_sq and not curr_sq):
                    prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50

        # KAMA crossover instead of EMA
        if "kama" in variant:
            if i > 0 and not np.isnan(kama_v[i]) and not np.isnan(kama_v[i-1]):
                cross_up = kama_v[i] > e34[i] and kama_v[i-1] <= e34[i-1] if not np.isnan(e34[i-1]) else False
                cross_dn = kama_v[i] < e34[i] and kama_v[i-1] >= e34[i-1] if not np.isnan(e34[i-1]) else False
            else:
                cross_up = cross_dn = False
        else:
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            else:
                cross_up = cross_dn = False

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

    experiments = [
        ("BASELINE (TRIX exit)", "baseline"),
        ("KER > 0.2 filter", "ker0.2"),
        ("KER > 0.3 filter", "ker0.3"),
        ("KER > 0.4 filter", "ker0.4"),
        ("Choppiness < 50 filter", "chop"),
        ("TTM Squeeze timing", "squeeze"),
        ("KAMA(10) crossover", "kama"),
        ("KAMA + KER > 0.3", "kama_ker0.3"),
        ("KER > 0.3 + Chop < 50", "ker0.3_chop"),
        ("PSAR exit added", "psar_exit"),
    ]

    print(f"{'Experiment':<30} {'test':>8} {'train':>8} {'PF':>6} {'trades':>6} {'net':>8}")
    print("-" * 75)
    for name, variant in experiments:
        try:
            sig_tr = gen(train_df, variant=variant)
            sig_te = gen(test_df, variant=variant)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            beat = "***" if te[0] > 2.9086 and tr[0] > 0 and te[3] >= 50 else ""
            print(f"  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>6} {te[4]:>8.0f}  [{both}] {beat}")
        except Exception as e:
            print(f"  {name:<28} ERROR: {e}")


if __name__ == "__main__":
    main()
