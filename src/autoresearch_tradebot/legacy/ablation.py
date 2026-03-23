"""
ablation.py — Remove components one by one to test if simpler strategy maintains performance.
"""
import numpy as np
import pandas as pd
import ta

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT
from .sweep_params import generate_signals_param, fast_backtest


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    BASE = dict(ema_fast=8, ema_slow=34, sma_trend=200, adx_thresh=20,
                adx_window=14, rsi_window=7, rsi_long=65, rsi_short=45,
                atr_window=20, atr_mult=2.0, skip_hour=13, bars_remaining_min=36)

    print("=" * 80)
    print("ABLATION STUDY — removing components one by one")
    print("=" * 80)

    # Baseline
    sig_tr = generate_signals_param(train_df, **BASE)
    sig_te = generate_signals_param(test_df, **BASE)
    tr = fast_backtest(train_df, sig_tr)
    te = fast_backtest(test_df, sig_te)
    print(f"\nBASELINE:  test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  net={te[4]:>8.0f}")

    # Test removing each component
    ablations = {
        "No SMA trend filter": dict(sma_trend=1),  # SMA(1) = close, effectively no filter
        "No ADX filter": dict(adx_thresh=0),
        "No RSI filter": dict(rsi_long=0, rsi_short=100),
        "No PTAX skip": dict(skip_hour=None),
        "No bars remaining cutoff": dict(bars_remaining_min=0),
        "Looser RSI (55/45)": dict(rsi_long=55, rsi_short=45),
        "No trailing stop (mult=100)": dict(atr_mult=100),
        "RSI only (no ADX)": dict(adx_thresh=0),
        "ADX only (no RSI)": dict(rsi_long=0, rsi_short=100),
    }

    for name, overrides in ablations.items():
        params = BASE.copy()
        params.update(overrides)
        try:
            sig_tr = generate_signals_param(train_df, **params)
            sig_te = generate_signals_param(test_df, **params)
            tr = fast_backtest(train_df, sig_tr)
            te = fast_backtest(test_df, sig_te)
            both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
            delta = te[0] - 2.7106
            print(f"  {name:<35} test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  [{both}]  delta={delta:>+.4f}")
        except Exception as e:
            print(f"  {name:<35} ERROR: {e}")

    # Also test adding new components
    print(f"\n{'='*80}")
    print("ADDITIONS — trying new components on top of best")
    print("=" * 80)

    # Test adding volume filter
    # Test adding time-of-day restrictions
    # Test adding momentum divergence
    additions = {
        "Morning only (9-13h)": "morning",
        "No afternoon (skip 14-16h too)": "no_afternoon",
        "Wider EMA gap (8/50)": dict(ema_slow=50),
        "Tighter trailing (1.5x ATR)": dict(atr_mult=1.5),
        "Wider trailing (3x ATR)": dict(atr_mult=3.0),
    }

    for name, cfg in additions.items():
        if isinstance(cfg, dict):
            params = BASE.copy()
            params.update(cfg)
            try:
                sig_tr = generate_signals_param(train_df, **params)
                sig_te = generate_signals_param(test_df, **params)
                tr = fast_backtest(train_df, sig_tr)
                te = fast_backtest(test_df, sig_te)
                both = "OK" if tr[0] > 0 and te[0] > 0 else "FAIL"
                delta = te[0] - 2.7106
                print(f"  {name:<35} test={te[0]:>7.4f}  train={tr[0]:>7.4f}  PF={te[1]:>6.2f}  trades={te[3]:>4}  [{both}]  delta={delta:>+.4f}")
            except Exception as e:
                print(f"  {name:<35} ERROR: {e}")


if __name__ == "__main__":
    main()
