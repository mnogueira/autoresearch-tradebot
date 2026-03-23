"""test_regime_wf.py — Test regime-adaptive configs via walk-forward."""
import numpy as np
import pandas as pd
import ta

from ..prepare import load_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


def rolling_hurst(close, window=100):
    def hurst_rs(series):
        ts = np.array(series); returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10: return 0.5
        mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
        if s == 0 or r == 0: return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def gen(df, hurst_thresh=0.50, adx_thresh=20, use_slow_adx=False, slow_adx_thresh=25):
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema220 = ta.trend.ema_indicator(df["Close"], window=220)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)
    trix12 = ta.trend.trix(df["Close"], window=12)
    hurst = rolling_hurst(df["Close"], window=100)
    trix_med = trix12.rolling(500, min_periods=100).median().shift(1)

    if use_slow_adx:
        adx_slow = ta.trend.adx(df["High"], df["Low"], df["Close"], window=50)
        asv = adx_slow.values
    else:
        asv = None

    c = df["Close"].values; e8 = ema8.values; e34 = ema34.values
    rv = rsi7.values; tv = ema220.values; av = adx14.values
    at_ = atr20.values; txv = trix12.values; tmv = trix_med.values; hv = hurst.values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date:
            pos = 0; prev_date = d; continue
        if il[i]:
            sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

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

        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour in (12, 13): prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue
        if av[i] < adx_thresh: prev_date = d; continue
        h = hv[i]
        if not np.isnan(h) and h < hurst_thresh: prev_date = d; continue
        if use_slow_adx and asv is not None and not np.isnan(asv[i]) and asv[i] < slow_adx_thresh:
            prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        if i > 0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
            cu = e8[i] > e34[i] and e8[i-1] <= e34[i-1]
            cd = e8[i] < e34[i] and e8[i-1] >= e34[i-1]
            if cu and c[i] > tv[i] and r > 65:
                sig[i] = 1; pos = 1; peak = c[i]
            elif cd and c[i] < tv[i] and r < 40:
                sig[i] = -1; pos = -1; peak = c[i]
        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def walk_forward(df, months, gen_fn, **kw):
    results = []
    i = 0
    while i + 14 <= len(months):
        test_start = months[i + 12]
        test_end = months[min(i + 13, len(months) - 1)]
        test_mask = (df["month"] >= test_start) & (df["month"] <= test_end)
        test_df = df[test_mask].copy()
        if len(test_df) == 0: break

        signals = gen_fn(test_df, **kw)
        signals = signals.reindex(test_df.index).fillna(0).astype(int).clip(-1, 1)
        day_last = test_df.groupby("date").tail(1).index
        signals.loc[day_last] = 0

        position = 0; trades = []; entry_price = 0.0
        for j in range(len(test_df)):
            signal = signals.iloc[j]; fill_price = test_df["Open"].iloc[j]
            if j > 0 and test_df["date"].iloc[j] != test_df["date"].iloc[j-1] and position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                trades.append(pnl); position = 0
            if signal != position:
                if position != 0:
                    pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                    trades.append(pnl)
                if signal != 0: entry_price = fill_price
                position = signal
        if position != 0:
            pnl = (test_df["Open"].iloc[-1] - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
            trades.append(pnl)

        arr = np.array(trades) if trades else np.array([0.0])
        n = len(trades); td = test_df.index.normalize().nunique()
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(n / max(td, 1) * 252) if n > 1 and arr.std(ddof=1) > 0 else 0
        results.append(dict(sharpe=sharpe, net=arr.sum(), trades=n))
        i += 2
    return results


def main():
    df = load_data()
    df = add_session_markers(df)
    df["month"] = df.index.to_period("M")
    months = sorted(df["month"].unique())

    configs = [
        ("BASELINE (H>0.50, ADX>20)", dict(hurst_thresh=0.50, adx_thresh=20)),
        ("H>0.52, ADX>20", dict(hurst_thresh=0.52, adx_thresh=20)),
        ("H>0.50, ADX>22", dict(hurst_thresh=0.50, adx_thresh=22)),
        ("H>0.52, ADX>22", dict(hurst_thresh=0.52, adx_thresh=22)),
        ("H>0.50 + slowADX50>20", dict(hurst_thresh=0.50, use_slow_adx=True, slow_adx_thresh=20)),
        ("H>0.50 + slowADX50>25", dict(hurst_thresh=0.50, use_slow_adx=True, slow_adx_thresh=25)),
        ("H>0.48, ADX>20", dict(hurst_thresh=0.48, adx_thresh=20)),
        ("H>0.50, ADX>18", dict(hurst_thresh=0.50, adx_thresh=18)),
    ]

    print(f"{'Config':<30} {'pos':>5} {'avg':>6} {'med':>6} {'net':>8} {'trades':>6}")
    print("-" * 70)
    for name, kw in configs:
        results = walk_forward(df, months, gen, **kw)
        sharpes = [r["sharpe"] for r in results]
        nets = [r["net"] for r in results]
        pos = sum(1 for s in sharpes if s > 0)
        total_trades = sum(r["trades"] for r in results)
        print(f"  {name:<28} {pos:>2}/{len(results)}  {np.mean(sharpes):>6.2f} {np.median(sharpes):>6.2f} {sum(nets):>8,.0f} {total_trades:>6}")


if __name__ == "__main__":
    main()
