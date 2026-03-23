"""
test_custom.py — Test custom indicators from web research not in ta library.
Hull MA, Hurst exponent, autocorrelation, McGinley Dynamic.
"""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, split_data, add_session_markers
from ..sweep_params import fast_backtest


def hull_ma(close, period=9):
    """Hull Moving Average — near-zero lag."""
    half = period // 2
    sqrt_p = max(int(np.sqrt(period)), 1)
    wma_half = close.rolling(half).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
    wma_full = close.rolling(period).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
    diff = 2 * wma_half - wma_full
    hma = diff.rolling(sqrt_p).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
    return hma


def mcginley_dynamic(close, period=14):
    """McGinley Dynamic — self-adjusting MA."""
    md = pd.Series(np.nan, index=close.index)
    md.iloc[period] = close.iloc[period]
    for i in range(period + 1, len(close)):
        if np.isnan(md.iloc[i-1]):
            md.iloc[i] = close.iloc[i]
        else:
            ratio = close.iloc[i] / md.iloc[i-1]
            md.iloc[i] = md.iloc[i-1] + (close.iloc[i] - md.iloc[i-1]) / (period * ratio**4)
    return md


def rolling_hurst(close, window=100):
    """Rolling Hurst exponent via R/S analysis. >0.5=trending, <0.5=mean-reverting."""
    def hurst_rs(series):
        if len(series) < 20:
            return 0.5
        ts = np.array(series)
        returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10:
            return 0.5
        mean_r = returns.mean()
        deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min()
        s = returns.std(ddof=1)
        if s == 0 or r == 0:
            return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def rolling_autocorr(close, window=50, lag=1):
    """Rolling autocorrelation of returns. Positive = trending."""
    returns = close.pct_change()
    return returns.rolling(window).apply(lambda x: pd.Series(x).autocorr(lag=lag), raw=False)


def gen(df, variant="baseline"):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix15 = ta.trend.trix(df["Close"], window=15)

    # Custom indicators
    extras = {}
    if "hma" in variant:
        for p in [9, 14, 21]:
            extras[f"hma{p}"] = hull_ma(df["Close"], period=p)
    if "mcg" in variant:
        extras["mcg"] = mcginley_dynamic(df["Close"], period=14)
    if "hurst" in variant:
        extras["hurst"] = rolling_hurst(df["Close"], window=100)
    if "autocorr" in variant:
        extras["autocorr"] = rolling_autocorr(df["Close"], window=50)

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

        # Exit: TRIX + ATR trailing (same for all variants)
        if pos != 0:
            cur_atr = at_[i] if not np.isnan(at_[i]) else 0
            fv = trix_v[i] if not np.isnan(trix_v[i]) else trix_med
            fv_prev = trix_v[i-1] if i > 0 and not np.isnan(trix_v[i-1]) else trix_med
            trix_exit = False
            if pos == 1 and fv < trix_med and fv_prev >= trix_med: trix_exit = True
            elif pos == -1 and fv > trix_med and fv_prev <= trix_med: trix_exit = True
            if trix_exit: sig[i] = 0; pos = 0
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

        # Hurst regime filter
        if "hurst" in variant and "hurst" in extras:
            hv = extras["hurst"].values[i]
            if not np.isnan(hv) and hv < 0.55: prev_date = d; continue

        # Autocorrelation regime filter
        if "autocorr" in variant and "autocorr" in extras:
            acv = extras["autocorr"].values[i]
            if not np.isnan(acv) and acv < 0: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50

        # HMA crossover (replace EMA8 with HMA)
        if "hma_cross" in variant:
            p = int(variant.split("hma_cross")[1].split("_")[0]) if "hma_cross" in variant else 9
            hma_v = extras.get(f"hma{p}", extras.get("hma9"))
            if hma_v is not None:
                hv = hma_v.values
                if i > 0 and not np.isnan(hv[i]) and not np.isnan(hv[i-1]) and not np.isnan(e34[i-1]):
                    cross_up = hv[i] > e34[i] and hv[i-1] <= e34[i-1]
                    cross_dn = hv[i] < e34[i] and hv[i-1] >= e34[i-1]
                    if cross_up and close[i] > tv[i] and r > 65:
                        sig[i] = 1; pos = 1; peak = close[i]
                    elif cross_dn and close[i] < tv[i] and r < 45:
                        sig[i] = -1; pos = -1; peak = close[i]
        # McGinley as trend filter (replace EMA200)
        elif "mcg_trend" in variant and "mcg" in extras:
            mv = extras["mcg"].values[i]
            if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]) and not np.isnan(mv):
                cross_up = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
                cross_dn = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
                if cross_up and close[i] > mv and r > 65:
                    sig[i] = 1; pos = 1; peak = close[i]
                elif cross_dn and close[i] < mv and r < 45:
                    sig[i] = -1; pos = -1; peak = close[i]
        else:
            # Standard EMA crossover
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


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    experiments = [
        ("BASELINE (TRIX exit)", "baseline"),
        ("HMA(9)/EMA(34) cross", "hma_cross9_hma"),
        ("HMA(14)/EMA(34) cross", "hma_cross14_hma"),
        ("HMA(21)/EMA(34) cross", "hma_cross21_hma"),
        ("McGinley(14) trend", "mcg_trend_mcg"),
        ("Hurst > 0.55 filter", "hurst"),
        ("Autocorr > 0 filter", "autocorr"),
        ("Hurst + Autocorr", "hurst_autocorr"),
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
