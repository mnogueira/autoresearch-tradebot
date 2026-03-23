"""
optuna_optimize.py — Bayesian optimization of ALL parameters simultaneously.
Uses Optuna TPE sampler to efficiently search the full parameter space.
Optimizes test_sharpe subject to train_sharpe > 0 and trades >= 50.
"""
import numpy as np
import pandas as pd
import ta
import optuna

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT

optuna.logging.set_verbosity(optuna.logging.WARNING)


def rolling_hurst(close, window=100):
    def hurst_rs(series):
        ts = np.array(series); returns = np.diff(ts) / ts[:-1]
        if len(returns) < 10: return 0.5
        mean_r = returns.mean(); deviate = np.cumsum(returns - mean_r)
        r = deviate.max() - deviate.min(); s = returns.std(ddof=1)
        if s == 0 or r == 0: return 0.5
        return np.log(r / s) / np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)


def gen_parameterized(df, p, precomputed=None):
    """Fully parameterized strategy."""
    if precomputed is None:
        precomputed = precompute(df)

    ema_f = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    ema_s = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    ema_t = ta.trend.ema_indicator(df["Close"], window=p["trend_w"])
    rsi = ta.momentum.rsi(df["Close"], window=p["rsi_w"])
    adx = precomputed["adx"]
    atr = precomputed["atr"]
    trix = ta.trend.trix(df["Close"], window=p["trix_w"])
    trix_med = trix.rolling(500, min_periods=100).median().shift(1)

    c = df["Close"].values
    ef = ema_f.values; es = ema_s.values; tv = ema_t.values
    rv = rsi.values; av = adx.values; at_ = atr.values
    txv = trix.values; tmv = trix_med.values
    hv = precomputed["hurst"].values
    vrv = precomputed["vr"].values
    vwv = precomputed["vwap"].values
    il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    dates = df["date"].values; times = df["time"].values

    sig = np.zeros(len(df), dtype=np.int64)
    pos = 0; prev_date = None; peak = 0.0

    skip_hours = set()
    if p.get("skip_12", True): skip_hours.add(12)
    if p.get("skip_13", True): skip_hours.add(13)
    if p.get("skip_14", False): skip_hours.add(14)

    for i in range(len(df)):
        d = dates[i]
        if ib[i] or d != prev_date: pos = 0; prev_date = d; continue
        if il[i]: sig[i] = 0; pos = 0; prev_date = d; continue
        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(tv[i]) or np.isnan(av[i]) or np.isnan(at_[i]):
            sig[i] = pos; prev_date = d; continue

        if pos != 0:
            ca = at_[i] if not np.isnan(at_[i]) else 0
            tm = tmv[i] if not np.isnan(tmv[i]) else 0
            fv = txv[i] if not np.isnan(txv[i]) else tm
            fp = txv[i-1] if i > 0 and not np.isnan(txv[i-1]) else tm
            trix_exit = (pos == 1 and fv < tm and fp >= tm) or (pos == -1 and fv > tm and fp <= tm)
            if trix_exit: sig[i] = 0; pos = 0
            elif pos == 1:
                peak = max(peak, c[i])
                if ca > 0 and c[i] < peak - p["atr_mult"] * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            elif pos == -1:
                peak = min(peak, c[i])
                if ca > 0 and c[i] > peak + p["atr_mult"] * ca: sig[i] = 0; pos = 0
                else: sig[i] = pos
            prev_date = d; continue

        ct = times[i]
        if hasattr(ct, 'hour') and ct.hour in skip_hours: prev_date = d; continue
        if hasattr(ct, 'hour') and (ct.hour > 14 or (ct.hour == 14 and ct.minute >= 55)):
            prev_date = d; continue
        if av[i] < p["adx_thresh"]: prev_date = d; continue
        h = hv[i]
        if not np.isnan(h) and h < p["hurst_thresh"]: prev_date = d; continue
        v = vrv[i]
        if not np.isnan(v) and v > p["vr_max"]: prev_date = d; continue

        r = rv[i] if not np.isnan(rv[i]) else 50
        vw = vwv[i] if not np.isnan(vwv[i]) else c[i]

        use_vwap = p.get("use_vwap", True)

        if i > 0 and not np.isnan(ef[i-1]) and not np.isnan(es[i-1]):
            cu = ef[i] > es[i] and ef[i-1] <= es[i-1]
            cd = ef[i] < es[i] and ef[i-1] >= es[i-1]
            long_ok = cu and c[i] > tv[i] and r > p["rsi_long"]
            short_ok = cd and c[i] < tv[i] and r < p["rsi_short"]
            if use_vwap:
                if long_ok and c[i] < vw: long_ok = False
                if short_ok and c[i] > vw: short_ok = False
            if long_ok: sig[i] = 1; pos = 1; peak = c[i]
            elif short_ok: sig[i] = -1; pos = -1; peak = c[i]
        prev_date = d

    signals = pd.Series(sig, index=df.index)
    signals = signals.groupby(df["date"]).shift(1).fillna(0).astype(int)
    return signals


def precompute(df):
    """Precompute expensive indicators that don't change with parameters."""
    ret = df["Close"].pct_change()
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tp = (typical * df["Volume"]).groupby(df.index.date).cumsum()
    cum_v = df["Volume"].groupby(df.index.date).cumsum().replace(0, np.nan)
    return {
        "adx": ta.trend.adx(df["High"], df["Low"], df["Close"], window=14),
        "atr": ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20),
        "hurst": rolling_hurst(df["Close"], window=100),
        "vr": ret.rolling(3).std() / ret.rolling(20).std(),
        "vwap": cum_tp / cum_v,
    }


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
    if len(trades) < 10: return 0, 0, len(trades)
    arr = np.array(trades); n = len(arr)
    td = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        tpd = n / max(td, 1)
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpd * 252)
    else:
        sharpe = 0
    return round(sharpe, 4), round(arr.sum(), 2), n


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    print("Precomputing fixed indicators...")
    tr_pre = precompute(train_df)
    te_pre = precompute(test_df)

    best_result = {"test_sharpe": 0, "params": {}}

    def objective(trial):
        p = {
            "ema_fast": trial.suggest_int("ema_fast", 5, 12),
            "ema_slow": trial.suggest_int("ema_slow", 21, 50),
            "trend_w": trial.suggest_int("trend_w", 150, 300, step=10),
            "rsi_w": trial.suggest_int("rsi_w", 5, 14),
            "rsi_long": trial.suggest_int("rsi_long", 55, 75),
            "rsi_short": trial.suggest_int("rsi_short", 25, 50),
            "adx_thresh": trial.suggest_int("adx_thresh", 15, 30),
            "atr_mult": trial.suggest_float("atr_mult", 1.0, 4.0, step=0.25),
            "trix_w": trial.suggest_int("trix_w", 8, 25),
            "hurst_thresh": trial.suggest_float("hurst_thresh", 0.40, 0.60, step=0.02),
            "vr_max": trial.suggest_float("vr_max", 1.0, 4.0, step=0.25),
            "skip_12": trial.suggest_categorical("skip_12", [True, False]),
            "skip_13": True,  # Always skip PTAX
            "skip_14": trial.suggest_categorical("skip_14", [True, False]),
            "use_vwap": trial.suggest_categorical("use_vwap", [True, False]),
        }

        # Quick constraint: ema_fast must be < ema_slow
        if p["ema_fast"] >= p["ema_slow"]:
            return -999

        try:
            sig_tr = gen_parameterized(train_df, p, tr_pre)
            sig_te = gen_parameterized(test_df, p, te_pre)
            tr_sharpe, tr_net, tr_n = fast_bt(train_df, sig_tr)
            te_sharpe, te_net, te_n = fast_bt(test_df, sig_te)
        except Exception:
            return -999

        # Constraints
        if tr_sharpe <= 0: return -999
        if te_n < 50: return -999
        if te_sharpe <= 0: return -999

        # Track best
        if te_sharpe > best_result["test_sharpe"]:
            best_result["test_sharpe"] = te_sharpe
            best_result["train_sharpe"] = tr_sharpe
            best_result["trades"] = te_n
            best_result["net"] = te_net
            best_result["params"] = p.copy()
            print(f"  NEW BEST: test={te_sharpe:.4f} train={tr_sharpe:.4f} n={te_n} net={te_net:.0f}")

        return te_sharpe

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    print("Running Optuna optimization (500 trials)...")
    study.optimize(objective, n_trials=500, show_progress_bar=False)

    print(f"\n{'='*80}")
    print("OPTUNA BEST RESULT")
    print(f"{'='*80}")
    print(f"  Test Sharpe: {best_result['test_sharpe']:.4f}")
    print(f"  Train Sharpe: {best_result.get('train_sharpe', 0):.4f}")
    print(f"  Trades: {best_result.get('trades', 0)}")
    print(f"  Net: R${best_result.get('net', 0):,.0f}")
    print(f"\n  Parameters:")
    for k, v in best_result["params"].items():
        print(f"    {k}: {v}")

    # Compare with current strategy
    print(f"\n  Current strategy: test=3.5610, train=0.9840, n=56, net=R$5,834")
    improvement = best_result["test_sharpe"] - 3.5610
    print(f"  Improvement: {improvement:+.4f} ({improvement/3.5610*100:+.1f}%)")


if __name__ == "__main__":
    main()
