"""
volume_bars.py — Resample M1 data into volume-based bars.
Each bar aggregates a fixed amount of volume (López de Prado method).
"""
import numpy as np
import pandas as pd
import ta

from ..common.paths import DATA_DIR
from .prepare import add_session_markers, POINT_VALUE, TOTAL_COST_RT


def make_volume_bars(df_m1, bar_volume=5000):
    """
    Resample M1 data into volume bars.
    Each bar contains approximately bar_volume units of traded volume.
    """
    bars = []
    cum_vol = 0
    bar_open = bar_high = bar_low = bar_close = None
    bar_start = None

    for idx, row in df_m1.iterrows():
        if bar_open is None:
            bar_open = row["Open"]
            bar_high = row["High"]
            bar_low = row["Low"]
            bar_start = idx
        else:
            bar_high = max(bar_high, row["High"])
            bar_low = min(bar_low, row["Low"])

        bar_close = row["Close"]
        cum_vol += row["Volume"]

        if cum_vol >= bar_volume:
            bars.append({
                "time": bar_start,
                "Open": bar_open,
                "High": bar_high,
                "Low": bar_low,
                "Close": bar_close,
                "Volume": cum_vol,
                "Spread": row.get("Spread", 0),
            })
            cum_vol = 0
            bar_open = None

    # Don't forget the last partial bar
    if bar_open is not None and cum_vol > 0:
        bars.append({
            "time": bar_start,
            "Open": bar_open,
            "High": bar_high,
            "Low": bar_low,
            "Close": bar_close,
            "Volume": cum_vol,
            "Spread": 0,
        })

    result = pd.DataFrame(bars)
    result.set_index("time", inplace=True)
    result.index = pd.DatetimeIndex(result.index)
    return result


def gen_signals(df):
    """Same honest strategy adapted for volume bars."""
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


def fast_bt(df, signals):
    """Quick backtest."""
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
        return 0, 0, 0, len(trades), 0, 0

    arr = np.array(trades)
    n = len(arr)
    wins = arr[arr > 0]; losses = arr[arr < 0]
    net = arr.sum()
    wr = len(wins) / n if n > 0 else 0
    gp = wins.sum() if len(wins) > 0 else 0
    gl = abs(losses.sum()) if len(losses) > 0 else 1e-9
    pf = gp / gl
    trading_days = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        tpd = n / max(trading_days, 1)
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpd * 252)
    else:
        sharpe = 0
    return round(sharpe, 4), round(pf, 4), round(wr, 4), n, round(net, 2), 0


def main():
    print("Loading M1 data...")
    df_m1 = pd.read_parquet(DATA_DIR / "wdo_m1.parquet")
    print(f"M1: {len(df_m1)} bars, {df_m1.index[0]} -> {df_m1.index[-1]}")

    # Test different volume bar sizes
    for vol_size in [2000, 3000, 5000, 8000, 10000, 15000]:
        vbars = make_volume_bars(df_m1, bar_volume=vol_size)
        n_bars = len(vbars)
        days = vbars.index.normalize().nunique()
        bpd = n_bars / days

        # Split 70/30
        dates = vbars.index.normalize().unique().sort_values()
        split_idx = int(len(dates) * 0.70)
        split_date = dates[split_idx]
        train = vbars[vbars.index < split_date].copy()
        test = vbars[vbars.index >= split_date].copy()

        train = add_session_markers(train)
        test = add_session_markers(test)

        sig_tr = gen_signals(train)
        sig_te = gen_signals(test)
        tr = fast_bt(train, sig_tr)
        te = fast_bt(test, sig_te)
        both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"

        print(f"  Vol={vol_size:>6}  bars={n_bars:>6}  bpd={bpd:>5.0f}  "
              f"test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  "
              f"trades={te[3]:>4}  net={te[4]:>8.0f}  [{both}]")


if __name__ == "__main__":
    main()
