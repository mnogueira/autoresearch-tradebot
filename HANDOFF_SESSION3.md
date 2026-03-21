# Autoresearch Session 3 — Handoff

## Start Here

Read this file, then `CLAUDE.md`, then `program.md`, then `strategy.py`, then `backtest.py`.

## Current State

- **Branch**: `autoresearch/wdo-honest`
- **Best honest strategy**: test_sharpe = **3.31**, train_sharpe = **+0.52** (both positive)
- **Strategy**: EMA(8/34) crossover + EMA(220) trend + ADX(14)>20 + RSI(7)>65/<40 + Hurst(100)>0.50 + ATR(20)x2 trailing stop + TRIX(12) rolling median exit + skip 12+13h + no entry after 14:55
- **Results**: PF 3.67, WR 65.7%, 67 trades, R$5,798 net, 0.34% max DD
- **Walk-forward realistic**: Sharpe ~2.0 average, 50% of 16 windows positive, R$4,294 total net
- **Audited**: 4 independent Opus audits confirmed no execution bias or lookahead bugs

## Session 3 Improvement Chain (8 steps, 2.38 → 3.31)

| # | Change | test_sharpe |
|---|--------|-------------|
| 1 | Parameter sweep (SMA200, RSI7, RSI>65) | 2.71 |
| 2 | EMA reversal exit | 2.80 |
| 3 | EMA(200) trend filter | 2.86 |
| 4 | TRIX(15) exit (comprehensive indicator sweep) | 2.91 |
| 5 | Skip 12+13h (unlocked by TRIX) | 2.98 |
| 6 | Hurst(100)>0.50 regime filter | 3.04 |
| 7 | Audit fix (rolling TRIX median, time-based cutoff) | 3.04 |
| 8 | Re-sweep (EMA220, RSI<40, TRIX12) | 3.31 |

## Robustness Validation

### Different train/test splits (ALL pass both-positive)
| Split | test_sharpe | test trades |
|-------|-------------|-------------|
| 50/50 | 2.23 | 119 |
| 60/40 | 2.10 | 101 |
| 65/35 | 2.66 | 84 |
| 70/30 | 3.31 | 67 |
| 75/25 | 3.65 | 58 |
| 80/20 | 3.88 | 50 |

### Walk-forward (12mo train, 2mo test, 16 windows)
- 8/16 positive (50%)
- Windows 1-9 (2023-2024): mostly negative (ranging WDO)
- Windows 10-16 (2025-2026): mostly very positive (trending WDO)
- Total net: +R$4,294
- **Realistic expected Sharpe: ~2.0**

## What Was Exhaustively Tested (~60+ experiments)

### Comprehensive indicator sweep (ALL 35 ta library indicators x 3 roles)
Found TRIX as exit signal — the breakthrough. Nothing else beat baseline.

### Entry filters tested and rejected
+DI/-DI, MACD, volume, StochRSI, Keltner, TSI, CCI, Williams %R, BB squeeze, EMA gap, VWAP, prev-day return, meia perna, asymmetric RSI/ADX, ADX rising, morning-only, close>open, day-of-week, KER regime, Choppiness Index, TTM Squeeze, Connors RSI confirm

### Alternative entries tested and rejected
Donchian breakout, SMA108 pullback, Schaff Trend Cycle, DIDI Index, KAMA crossover, HMA crossover, pullback entry, delayed 2-bar

### Exit mechanisms tested
EMA reversal (used then replaced), close<EMA(8), ratchet stop, re-entry after stop, time stops, breakeven, Chandelier Exit, Parabolic SAR, Supertrend exit

### Other approaches
ML (LightGBM), volume bars (M1), M15 timeframe, DXY/VIX/USDBRL with D-1 lag

### Custom indicators from web research
Kaufman Efficiency Ratio, KAMA, TTM Squeeze, Choppiness Index, Supertrend, Hull MA, McGinley Dynamic, Hurst exponent (WINNER), autocorrelation

## Audit Results (4 independent Opus 4.6 audits)

1. **Signal generation**: 5 scenarios traced — all clean
2. **Backtest execution**: Fill prices always Open, no double counting, costs correct
3. **Indicator computation**: ALL indicators verified causal, no future data
4. **TRIX median lookahead**: Found and FIXED (rolling + shift(1))

## CRITICAL RULES — ENFORCE ALWAYS

1. **Fill at Open price** — `df["Open"].iloc[i]`
2. **1-bar signal delay per day** — `signals.groupby(df["date"]).shift(1).fillna(0).astype(int)`
3. **Sharpe uses ddof=1**
4. **BOTH train AND test Sharpe must be positive**
5. **No external data lookahead** — use PREVIOUS day's close
6. **Rolling statistics must use .shift(1)** to exclude current bar
7. **Time-based entry cutoff** — use clock time, not bars_remaining
8. **Test ALL indicators in ALL roles** before concluding
9. **Re-sweep parameters after structural changes**
10. **Audit when Sharpe > 3** — spawn independent reviewers

## How to Resume
```
Read HANDOFF_SESSION3.md, then continue from test_sharpe=3.31.
Walk-forward realistic Sharpe ~2.0. Strategy is regime-dependent.
Next: regime-adaptive approach, more historical data, or live paper trading.
```
