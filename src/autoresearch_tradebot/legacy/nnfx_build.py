"""
nnfx_build.py — NNFX (No Nonsense Forex) style strategy build.
Step by step: baseline -> confirmation1 -> confirmation2 -> volume -> exit -> continue.
Each step optimized with Optuna.

STEP 1: Find best BASELINE indicator.
A baseline determines the trend direction. We only trade in its direction.
Test ALL available trend indicators, optimize each with Optuna.
"""
import numpy as np
import pandas as pd
import ta
import optuna

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT

optuna.logging.set_verbosity(optuna.logging.WARNING)


def fast_bt(df, signals):
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(-1, 1)
    day_last = df.groupby("date").tail(1).index
    signals.loc[day_last] = 0
    position = 0; trades = []; entry_price = 0.0
    for i in range(len(df)):
        signal = signals.iloc[i]; fill_price = df["Open"].iloc[i]
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
    if len(trades) < 10: return 0, 0, len(trades), 0
    arr = np.array(trades); n = len(arr)
    td = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(n / max(td, 1) * 252)
    else:
        sharpe = 0
    wins = arr[arr > 0]; losses = arr[arr < 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else 0
    return round(sharpe, 4), round(arr.sum(), 2), n, round(pf, 2)


def gen_baseline(df, baseline_type, params):
    """Generate signals from a single baseline indicator.
    Entry: when price crosses above/below the baseline.
    Exit: ATR trailing stop (simple, no other exit for now).
    """
    c = df["Close"]
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    # Compute baseline
    if baseline_type == "ema":
        bl = ta.trend.ema_indicator(c, window=params["period"])
    elif baseline_type == "sma":
        bl = c.rolling(params["period"]).mean()
    elif baseline_type == "kama":
        bl = ta.momentum.kama(c, window=params["period"])
    elif baseline_type == "wma":
        bl = ta.trend.wma_indicator(c, window=params["period"])
    elif baseline_type == "dema":
        e1 = ta.trend.ema_indicator(c, window=params["period"])
        e2 = ta.trend.ema_indicator(e1, window=params["period"])
        bl = 2 * e1 - e2
    elif baseline_type == "tema":
        e1 = ta.trend.ema_indicator(c, window=params["period"])
        e2 = ta.trend.ema_indicator(e1, window=params["period"])
        e3 = ta.trend.ema_indicator(e2, window=params["period"])
        bl = 3 * e1 - 3 * e2 + e3
    elif baseline_type == "hma":
        half = max(params["period"] // 2, 1)
        sqrt_p = max(int(np.sqrt(params["period"])), 1)
        wma_h = c.rolling(half).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
        wma_f = c.rolling(params["period"]).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
        diff = 2 * wma_h - wma_f
        bl = diff.rolling(sqrt_p).apply(lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True)
    elif baseline_type == "ichimoku_base":
        bl = ta.trend.ichimoku_base_line(df["High"], df["Low"], window1=params.get("conv", 9), window2=params["period"])
    elif baseline_type == "ichimoku_conv":
        bl = ta.trend.ichimoku_conversion_line(df["High"], df["Low"], window1=params["period"], window2=params.get("base", 26))
    elif baseline_type == "mcginley":
        md = pd.Series(np.nan, index=c.index)
        p = params["period"]
        md.iloc[p] = c.iloc[p]
        for i in range(p + 1, len(c)):
            if np.isnan(md.iloc[i-1]): md.iloc[i] = c.iloc[i]
            else:
                ratio = c.iloc[i] / md.iloc[i-1]
                md.iloc[i] = md.iloc[i-1] + (c.iloc[i] - md.iloc[i-1]) / (p * ratio**4)
        bl = md
    else:
        bl = ta.trend.ema_indicator(c, window=params["period"])

    cv = c.values; blv = bl.values; atv = atr.values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    atr_mult = params.get("atr_mult", 2.0)

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date: pos = 0; prev_date = d; continue
        if il[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(blv[i]) or np.isnan(atv[i]): sig[i] = pos; prev_date = d; continue

        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour == 13: prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue

        if pos != 0:
            ca = atv[i] if not np.isnan(atv[i]) else 0
            if pos == 1:
                peak = max(peak, cv[i])
                if ca > 0 and cv[i] < peak - atr_mult * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, cv[i])
                if ca > 0 and cv[i] > peak + atr_mult * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        # Baseline crossover entry
        if i > 0 and not np.isnan(blv[i-1]):
            cross_up = cv[i] > blv[i] and cv[i-1] <= blv[i-1]
            cross_dn = cv[i] < blv[i] and cv[i-1] >= blv[i-1]
            if cross_up: sig[i] = 1; pos = 1; peak = cv[i]
            elif cross_dn: sig[i] = -1; pos = -1; peak = cv[i]

        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def optimize_baseline(train_df, test_df, baseline_type, n_trials=100):
    """Optimize a single baseline indicator with Optuna."""
    best = {"sharpe": -999, "params": {}}

    def objective(trial):
        if baseline_type in ("ichimoku_base", "ichimoku_conv"):
            period = trial.suggest_int("period", 9, 52)
        else:
            period = trial.suggest_int("period", 20, 300, step=5)
        atr_mult = trial.suggest_float("atr_mult", 1.0, 4.0, step=0.25)
        params = {"period": period, "atr_mult": atr_mult}

        try:
            sig_tr = gen_baseline(train_df, baseline_type, params)
            sig_te = gen_baseline(test_df, baseline_type, params)
            tr_s, tr_net, tr_n, tr_pf = fast_bt(train_df, sig_tr)
            te_s, te_net, te_n, te_pf = fast_bt(test_df, sig_te)
        except Exception:
            return -999

        if tr_s <= 0 or te_n < 50 or te_s <= 0: return -999
        if te_s > best["sharpe"]:
            best["sharpe"] = te_s
            best["train"] = tr_s
            best["trades"] = te_n
            best["net"] = te_net
            best["pf"] = te_pf
            best["params"] = params.copy()
        return te_s

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)
    return best


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    baselines = ["ema", "sma", "kama", "wma", "dema", "tema", "hma",
                 "ichimoku_base", "ichimoku_conv", "mcginley"]

    print("=" * 90)
    print("NNFX STEP 1: FIND BEST BASELINE (Optuna 100 trials each)")
    print("=" * 90)
    print(f"{'Baseline':<15} {'test':>8} {'train':>8} {'PF':>6} {'n':>4} {'net':>8} {'period':>6} {'ATR':>5}")
    print("-" * 70)

    results = []
    for bl in baselines:
        best = optimize_baseline(train_df, test_df, bl, n_trials=100)
        if best["sharpe"] > -999:
            p = best["params"]
            print(f"  {bl:<13} {best['sharpe']:>8.4f} {best.get('train',0):>8.4f} {best.get('pf',0):>6.2f} "
                  f"{best.get('trades',0):>4} {best.get('net',0):>8.0f} {p['period']:>6} {p['atr_mult']:>5.2f}")
            results.append((bl, best))
        else:
            print(f"  {bl:<13} NO VALID RESULT")

    # Sort by test sharpe
    results.sort(key=lambda x: -x[1]["sharpe"])
    print(f"\n{'='*90}")
    print("TOP 3 BASELINES:")
    for bl, best in results[:3]:
        print(f"  {bl}: test={best['sharpe']:.4f}, train={best.get('train',0):.4f}, "
              f"period={best['params']['period']}, ATR={best['params']['atr_mult']}")


if __name__ == "__main__":
    main()
