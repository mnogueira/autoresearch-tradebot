"""
walkforward.py — Walk-forward validation of the current strategy.
Rolling window: train on N months, test on next M months, slide forward.
"""
import sys
import numpy as np
import pandas as pd

from .prepare import load_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


STRATEGY_MODULE = "autoresearch_tradebot.legacy.strategy"


def run_wf_backtest(df, signals):
    """Run backtest on a single window, return trade array."""
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(-1, 1)
    day_last = df.groupby("date").tail(1).index
    signals.loc[day_last] = 0

    position = 0; trades = []; entry_price = 0.0
    for i in range(len(df)):
        signal = signals.iloc[i]
        fill_price = df["Open"].iloc[i]
        if i > 0 and df["date"].iloc[i] != df["date"].iloc[i - 1] and position != 0:
            pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
            trades.append(pnl); position = 0
        if signal != position:
            if position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                trades.append(pnl)
            if signal != 0:
                entry_price = fill_price
            position = signal
    if position != 0:
        pnl = (df["Open"].iloc[-1] - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
        trades.append(pnl)
    return trades


def calc_sharpe(trades, trading_days):
    arr = np.array(trades) if trades else np.array([0.0])
    n = len(arr)
    if n <= 1 or arr.std(ddof=1) == 0:
        return 0.0
    tpd = n / max(trading_days, 1)
    tpy = tpd * 252
    return (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpy)


def main():
    if STRATEGY_MODULE in sys.modules:
        del sys.modules[STRATEGY_MODULE]
    from . import strategy

    df = load_data()
    df = add_session_markers(df)

    # Get unique months
    df["month"] = df.index.to_period("M")
    months = sorted(df["month"].unique())

    train_months = 12  # 12 months train
    test_months = 2    # 2 months test

    print(f"Walk-Forward: {train_months}mo train, {test_months}mo test, {len(months)} total months")
    print(f"{'Window':<10} {'Period':<25} {'Sharpe':>8} {'PF':>8} {'Trades':>8} {'Net':>10} {'WR':>8}")
    print("-" * 80)

    results = []
    window = 0
    i = 0
    while i + train_months + test_months <= len(months):
        train_start = months[i]
        train_end = months[i + train_months - 1]
        test_start = months[i + train_months]
        test_end = months[min(i + train_months + test_months - 1, len(months) - 1)]

        train_mask = (df["month"] >= train_start) & (df["month"] <= train_end)
        test_mask = (df["month"] >= test_start) & (df["month"] <= test_end)

        train_df = df[train_mask].copy()
        test_df = df[test_mask].copy()

        if len(test_df) == 0:
            break

        # Generate signals
        signals = strategy.generate_signals(test_df)
        trades = run_wf_backtest(test_df, signals)

        n_trades = len(trades)
        trading_days = test_df.index.normalize().nunique()
        sharpe = calc_sharpe(trades, trading_days)
        arr = np.array(trades) if trades else np.array([0.0])
        wins = arr[arr > 0]
        losses = arr[arr < 0]
        net = arr.sum()
        wr = len(wins) / n_trades if n_trades > 0 else 0
        gp = wins.sum() if len(wins) > 0 else 0
        gl = abs(losses.sum()) if len(losses) > 0 else 1e-9
        pf = gp / gl

        period = f"{test_start}..{test_end}"
        window += 1
        print(f"  W{window:<7} {period:<25} {sharpe:>8.2f} {pf:>8.2f} {n_trades:>8} {net:>10.0f} {wr:>7.1%}")
        results.append(dict(window=window, period=period, sharpe=sharpe, pf=pf,
                            trades=n_trades, net=net, wr=wr))

        i += test_months  # slide forward

    # Summary
    print(f"\n{'='*80}")
    print("WALK-FORWARD SUMMARY")
    print(f"{'='*80}")
    sharpes = [r['sharpe'] for r in results]
    nets = [r['net'] for r in results]
    trades = [r['trades'] for r in results]
    positive = sum(1 for s in sharpes if s > 0)
    print(f"  Windows: {len(results)}")
    print(f"  Positive Sharpe: {positive}/{len(results)} ({positive/len(results)*100:.0f}%)")
    print(f"  Avg Sharpe: {np.mean(sharpes):.2f}")
    print(f"  Min Sharpe: {min(sharpes):.2f}")
    print(f"  Max Sharpe: {max(sharpes):.2f}")
    print(f"  Total net profit: R${sum(nets):,.0f}")
    print(f"  Avg trades/window: {np.mean(trades):.0f}")
    print(f"  Total trades: {sum(trades)}")


if __name__ == "__main__":
    main()
