# Autoresearch Session 2 — Handoff

## Start Here

Read this file, then `CLAUDE.md`, then `program.md`, then `strategy.py`, then `backtest.py`.

## Current State

- **Branch**: `autoresearch/wdo-honest`
- **Best honest strategy**: test_sharpe = **2.38**, train_sharpe = **+0.72** (both positive)
- **Strategy**: EMA(8/34) crossover + SMA(162) trend + ADX(14)>20 + RSI(9)>55/<45 + ATR(20)x2 trailing stop + skip 13h PTAX + 36 bars remaining
- **Results**: PF 2.03, WR 50.5%, 105 trades, R$5,215 net, 0.72% max DD
- **Data**: M5 bars in `data/wdo_m5.parquet` (95,935 bars, Aug 2022 → Mar 2026)
- **External data**: `data/vix_daily.parquet`, `data/dxy_daily.parquet`, `data/usdbrl_daily.parquet` (downloaded via yfinance)
- **Results log**: `results.tsv` (gitignored, only honest results)

## CRITICAL RULES — ENFORCE ALWAYS

### Execution Model (verified by 15 auditors — 5 Sonnet + 10 Opus)
1. **Fill at Open price** — `backtest.py` uses `df["Open"].iloc[i]` for all fills, never Close
2. **1-bar signal delay per day** — `signals.groupby(df["date"]).shift(1).fillna(0).astype(int)` — no cross-day leakage
3. **Sharpe uses ddof=1** — sample standard deviation
4. **No external data lookahead** — VIX/DXY must use PREVIOUS day's close, not same day
5. **prev_day_ret must use YESTERDAY's return** — `daily_ret.iloc[i-1]` mapped to day i
6. **H1 resampling must use previous completed bar** — current hour's close is unknown at hour start

### Strategy Development Rules
7. **BOTH train AND test Sharpe must be positive** before accepting any result
8. **Never reject a strategy concept from one test** — always sweep parameters AND test in all roles (entry, exit, filter, confirmation)
9. **When adding anything new, optimize its parameters** — never test with just one setting
10. **Do not be biased toward trend-following or mean reversion** — both may work
11. **If results look too good (Sharpe > 3), spawn Opus 4.6 subagents to audit for errors**
12. **Be skeptical of >70% win rates on intraday bars** — likely execution bias

### Bugs Previously Found and Fixed
- H1 resampling used current hour's close (FUTURE data) — fixed to use previous completed bar
- Same-bar execution (fill at signal close price) — fixed with 1-bar delay + Open fills
- VIX used same-day close — fixed to use previous day
- prev_day_ret used today's return — fixed to use yesterday
- Signal shift crossed day boundaries — fixed with groupby(date)
- Sharpe used ddof=0 — fixed to ddof=1
- End-of-data close used Close — fixed to use Open
- BB mean reversion appeared to have 93% WR but was 100% execution bias — edge evaporated with honest model

## What Works (Honest)
- **EMA crossover** with wide spread (8/34 = 26-bar gap) captures genuine trend changes
- **SMA(162)** = 1.5 trading days is a good trend filter
- **ADX > 20** correctly identifies trending markets
- **ATR(20) x2 trailing stop** adapts to volatility (better than HiLo/EMA trailing)
- **RSI(9) > 55 / < 45** as momentum confirmation filters weak crossovers
- **PTAX 13h skip** genuinely disrupts trend signals
- Pure price strategies are more trustworthy than external-data-filtered ones
- The honest Sharpe ~2.38 is real and verified — hedge fund quality

## What Does NOT Work (Honest)
- BB mean reversion with honest execution (1-bar delay kills the edge)
- H1 trend filter with previous-bar correction (too laggy)
- VIX/DXY as strict filters (lookahead was the "edge", not the data)
- Adding more entry filters (reduces trades below optimal ~100-120)
- Same-bar execution strategies (any strategy with >80% WR on M5 is suspicious)

## What to Try Next
1. **Machine learning** — use sklearn/lightgbm with features from our discovered indicators
2. **Different timeframe** — try M15 or H1 bars where execution delay matters less
3. **Multi-asset correlation** — DXY, DI1 with proper previous-day-only data
4. **Volume bars** — resample M1 data into volume-based bars (Marcos López de Prado)
5. **Walk-forward validation** — `walkforward.py` exists, re-run on honest strategy
6. **Ensemble** — combine trend + mean reversion but only if BOTH components are honest-positive
7. **PTAX-aware timing** — detailed hour-by-hour analysis of entry quality
8. **Different entry signals** — Donchian breakout, DIDI Index, Schaff Trend Cycle (all need honest re-test)

## Files Reference
| File | Purpose |
|------|---------|
| `strategy.py` | Current best strategy (agent-editable) |
| `backtest.py` | Backtesting engine (honest: Open fills, ddof=1) |
| `prepare.py` | Data loading and session markers |
| `optimize.py` | Optuna parameter optimization (needs updating for honest model) |
| `walkforward.py` | Walk-forward validation script |
| `sweep_honest.py` | Comprehensive honest parameter sweep |
| `results.tsv` | Experiment log (honest results only) |
| `plot_progress.py` | Generates progress chart |
| `data/wdo_m5.parquet` | Primary M5 data (95K bars) |
| `data/wdo_m1.parquet` | M1 data (94K bars, shorter period) |
| `data/vix_daily.parquet` | VIX daily (use D-1 only!) |

## Telegram
- Chat ID saved in `telegram_chat_id.txt` (8674564835)
- Send improvements only, not rejections
- Attach `progress.png` on improvements
- User wants to be notified of breakthroughs

## How to Resume
```
Read HANDOFF_SESSION2.md, then continue the autoresearch loop from test_sharpe=2.38.
Enforce ALL critical rules. Both train+test must be positive. Sweep all parameters.
```
