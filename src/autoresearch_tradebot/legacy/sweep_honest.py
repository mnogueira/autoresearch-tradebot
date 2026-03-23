"""Comprehensive honest sweep: both trend-following and mean reversion."""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT

df_all = load_data(timeframe="M5")
train_df, test_df = split_data(df_all, train_ratio=0.70)
train_df = add_session_markers(train_df)
test_df = add_session_markers(test_df)


def run_trend(df, fast=9, slow=21, sma_len=162, hilo_len=13, adx_thresh=20, min_br=36, skip13=True):
    ef = ta.trend.ema_indicator(df["Close"], window=fast).values
    es = ta.trend.ema_indicator(df["Close"], window=slow).values
    sma = df["Close"].rolling(window=sma_len).mean().values
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14).values
    hh = df["High"].rolling(window=hilo_len).mean().values
    hl = df["Low"].rolling(window=hilo_len).mean().values
    c = df["Close"].values; il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    br = df["bars_remaining"].values; dt = df["date"].values; tm = df["time"].values
    sig = np.zeros(len(df), dtype=np.int64); pos = 0; pd_ = None
    for i in range(len(df)):
        d = dt[i]
        if ib[i] or d != pd_: pos = 0; pd_ = d; continue
        if il[i]: sig[i] = 0; pos = 0; pd_ = d; continue
        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(sma[i]) or np.isnan(adx[i]) or np.isnan(hh[i]):
            sig[i] = pos; pd_ = d; continue
        if pos != 0:
            if pos == 1 and c[i] < hl[i]: sig[i] = 0; pos = 0
            elif pos == -1 and c[i] > hh[i]: sig[i] = 0; pos = 0
            else: sig[i] = pos
            pd_ = d; continue
        ct = tm[i]
        if skip13 and hasattr(ct, "hour") and ct.hour == 13: pd_ = d; continue
        if adx[i] < adx_thresh or br[i] <= min_br: pd_ = d; continue
        if i > 0 and not np.isnan(ef[i-1]) and not np.isnan(es[i-1]):
            cu = ef[i] > es[i] and ef[i-1] <= es[i-1]
            cd = ef[i] < es[i] and ef[i-1] >= es[i-1]
            if cu and c[i] > sma[i]: sig[i] = 1; pos = 1
            elif cd and c[i] < sma[i]: sig[i] = -1; pos = -1
        pd_ = d
    return pd.Series(sig, index=df.index).groupby(df["date"]).shift(1).fillna(0).astype(int).values


def run_meanrev(df, bb_win=18, bb_dev=2.0, exit_type="bb_mid", hilo_len=13, trail_len=13,
                min_br=36, skip13=True, rsi_len=0, sma_len=0):
    bbu = ta.volatility.bollinger_hband(df["Close"], window=bb_win, window_dev=bb_dev).values
    bbl = ta.volatility.bollinger_lband(df["Close"], window=bb_win, window_dev=bb_dev).values
    bbm = ta.volatility.bollinger_mavg(df["Close"], window=bb_win).values
    c = df["Close"].values; il = df["is_last_30min"].values; ib = df["is_first_bar"].values
    br = df["bars_remaining"].values; dt = df["date"].values; tm = df["time"].values
    rsi = ta.momentum.rsi(df["Close"], window=rsi_len).values if rsi_len > 0 else np.full(len(df), 50.0)
    sma = df["Close"].rolling(window=sma_len).mean().values if sma_len > 0 else None
    hh = df["High"].rolling(window=hilo_len).mean().values
    hl = df["Low"].rolling(window=hilo_len).mean().values
    ema_t = ta.trend.ema_indicator(df["Close"], window=trail_len).values
    sig = np.zeros(len(df), dtype=np.int64); pos = 0; pd_ = None; ep = 0
    for i in range(len(df)):
        d = dt[i]
        if ib[i] or d != pd_: pos = 0; pd_ = d; continue
        if il[i]: sig[i] = 0; pos = 0; pd_ = d; continue
        if np.isnan(bbu[i]) or np.isnan(bbl[i]) or np.isnan(bbm[i]):
            sig[i] = pos; pd_ = d; continue
        if pos != 0:
            exited = False
            if exit_type == "bb_mid":
                if pos == 1 and c[i] >= bbm[i]: sig[i] = 0; pos = 0; exited = True
                elif pos == -1 and c[i] <= bbm[i]: sig[i] = 0; pos = 0; exited = True
            elif exit_type == "hilo":
                if pos == 1 and c[i] < hl[i]: sig[i] = 0; pos = 0; exited = True
                elif pos == -1 and c[i] > hh[i]: sig[i] = 0; pos = 0; exited = True
            elif exit_type == "ema_trail":
                if pos == 1 and c[i] < ema_t[i]: sig[i] = 0; pos = 0; exited = True
                elif pos == -1 and c[i] > ema_t[i]: sig[i] = 0; pos = 0; exited = True
            # Catastrophe SL
            if not exited:
                bw = bbu[i] - bbl[i]
                if pos == 1 and c[i] < ep - bw * 2: sig[i] = 0; pos = 0; exited = True
                elif pos == -1 and c[i] > ep + bw * 2: sig[i] = 0; pos = 0; exited = True
            if not exited: sig[i] = pos
            pd_ = d; continue
        ct = tm[i]
        if skip13 and hasattr(ct, "hour") and ct.hour == 13: pd_ = d; continue
        if br[i] <= min_br: pd_ = d; continue
        r = rsi[i] if not np.isnan(rsi[i]) else 50
        if c[i] <= bbl[i] and (rsi_len == 0 or r < 50):
            if sma is None or (not np.isnan(sma[i]) and c[i] > sma[i]):
                sig[i] = 1; pos = 1; ep = c[i]
        elif c[i] >= bbu[i] and (rsi_len == 0 or r > 50):
            if sma is None or (not np.isnan(sma[i]) and c[i] < sma[i]):
                sig[i] = -1; pos = -1; ep = c[i]
        pd_ = d
    return pd.Series(sig, index=df.index).groupby(df["date"]).shift(1).fillna(0).astype(int).values


def bt(df, sig):
    c = df["Close"].values; o = df["Open"].values; dt = df["date"].values
    pos = 0; ep = 0; tr = []
    for i in range(len(df)):
        s = int(sig[i])
        if i > 0 and dt[i] != dt[i-1] and pos != 0:
            tr.append((o[i] - ep) * pos * POINT_VALUE - TOTAL_COST_RT); pos = 0
        if s != pos:
            if pos != 0: tr.append((o[i] - ep) * pos * POINT_VALUE - TOTAL_COST_RT)
            if s != 0: ep = o[i]
            pos = s
    if pos != 0: tr.append((o[-1] - ep) * pos * POINT_VALUE - TOTAL_COST_RT)
    if len(tr) < 30: return -10, 0, len(tr), 0, 0
    a = np.array(tr)
    w = a[a > 0]; l = a[a < 0]
    gp = w.sum() if len(w) > 0 else 0
    gl = abs(l.sum()) if len(l) > 0 else 1e-9
    d = len(np.unique(dt)); tpd = len(tr) / max(d, 1)
    sh = (a.mean() / a.std(ddof=1)) * np.sqrt(tpd * 252) if a.std(ddof=1) > 0 else 0
    return round(sh, 4), round(gp/gl, 4), len(tr), round(a.sum(), 2), round(len(w)/len(tr), 4)


print(f"{'Type':>8} {'Config':>50} | {'TrSh':>6} {'TeSh':>6} {'PF':>5} {'#Tr':>5} {'Net':>8} {'WR':>5}")
print("-" * 100)

res = []

# TREND-FOLLOWING sweep
for sma in [108, 144, 162, 200]:
    for hilo in [9, 13, 17]:
        for mbr in [24, 30, 36]:
            ts = run_trend(train_df, sma_len=sma, hilo_len=hilo, min_br=mbr)
            te = run_trend(test_df, sma_len=sma, hilo_len=hilo, min_br=mbr)
            trs, _, _, _, _ = bt(train_df, ts)
            tes, pf, nt, net, wr = bt(test_df, te)
            if nt >= 30:
                res.append((tes, "trend", f"SMA{sma} HiLo{hilo} br{mbr}", trs, pf, nt, net, wr))

# MEAN REVERSION sweep — multiple exits
for bbw in [14, 18, 24, 30]:
    for bbd in [1.5, 2.0, 2.5, 3.0]:
        for exit_t in ["bb_mid", "hilo", "ema_trail"]:
            for mbr in [24, 36]:
                ts = run_meanrev(train_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, min_br=mbr)
                te = run_meanrev(test_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, min_br=mbr)
                trs, _, _, _, _ = bt(train_df, ts)
                tes, pf, nt, net, wr = bt(test_df, te)
                if nt >= 30:
                    res.append((tes, "meanrev", f"BB({bbw},{bbd}) {exit_t} br{mbr}", trs, pf, nt, net, wr))

# MEAN REVERSION with RSI filter
for bbw in [18, 24]:
    for bbd in [2.0, 2.5, 3.0]:
        for rsi_l in [14, 21]:
            for exit_t in ["bb_mid", "hilo"]:
                ts = run_meanrev(train_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, rsi_len=rsi_l, min_br=36)
                te = run_meanrev(test_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, rsi_len=rsi_l, min_br=36)
                trs, _, _, _, _ = bt(train_df, ts)
                tes, pf, nt, net, wr = bt(test_df, te)
                if nt >= 30:
                    res.append((tes, "meanrev", f"BB({bbw},{bbd}) RSI{rsi_l} {exit_t} br36", trs, pf, nt, net, wr))

# MEAN REVERSION with SMA trend filter (buy dip in uptrend only)
for bbw in [18, 24]:
    for bbd in [2.0, 2.5]:
        for sma_l in [108, 162]:
            for exit_t in ["bb_mid", "hilo"]:
                ts = run_meanrev(train_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, sma_len=sma_l, min_br=36)
                te = run_meanrev(test_df, bb_win=bbw, bb_dev=bbd, exit_type=exit_t, sma_len=sma_l, min_br=36)
                trs, _, _, _, _ = bt(train_df, ts)
                tes, pf, nt, net, wr = bt(test_df, te)
                if nt >= 30:
                    res.append((tes, "meanrev", f"BB({bbw},{bbd}) SMA{sma_l} {exit_t} br36", trs, pf, nt, net, wr))

res.sort(key=lambda x: x[0], reverse=True)
print(f"\nTOP 25 HONEST RESULTS:")
print(f"{'Type':>8} {'Config':>50} | {'TrSh':>6} {'TeSh':>6} {'PF':>5} {'#Tr':>5} {'Net':>8} {'WR':>5}")
print("-" * 100)
for sh, tp, cfg, tr, pf, nt, net, wr in res[:25]:
    print(f"{tp:>8} {cfg:>50} | {tr:>6.2f} {sh:>6.2f} {pf:>5.2f} {nt:>5} {net:>8.0f} {wr:>5.3f}")
