# Autoresearch Session 3 — Handoff

## Start Here

Read this file, then `CLAUDE.md`, then `program.md`, then `strategy.py`, then `backtest.py`.

## Current State

- **Branch**: `autoresearch/wdo-honest`
- **Best honest strategy**: test_sharpe = **2.86**, train_sharpe = **+0.12** (both positive)
- **Strategy**: EMA(8/34) crossover + EMA(200) trend + ADX(14)>20 + RSI(7)>65/<45 + ATR(20)x2 trailing stop + EMA(8/34) reversal exit + skip 13h PTAX + 36 bars remaining
- **Results**: PF 2.35, WR 53.8%, 106 trades, R$6,044 net, 0.66% max DD
- **Data**: M5 bars in `data/wdo_m5.parquet` (95,935 bars, Aug 2022 → Mar 2026)

## Session 3 Improvements (2.38 → 2.86)

1. **Parameter sweep** (2.38→2.71): Coordinate descent across 12 parameter dimensions
   - SMA trend filter: 162 → 200 (longer = more reliable)
   - RSI window: 9 → 7 (faster momentum detection)
   - RSI long threshold: 55 → 65 (stricter entry quality)

2. **EMA reversal exit** (2.71→2.80): Exit when EMA(8) crosses back against EMA(34)
   - Catches trend reversals faster than trailing stop alone
   - Reduced average loss from -101 to -91

3. **EMA(200) trend filter** (2.80→2.86): Replaced SMA(200) with EMA(200)
   - EMA reacts faster to trend changes
   - 9 more trades (106 vs 97) while maintaining quality

## Walk-Forward Validation

- 16 windows (12mo train, 2mo test sliding): **8/16 positive** (50%)
- Recent windows (2025-2026) are strongly positive (Sharpe 2-5)
- Earlier windows (2023-2024) are mostly negative (Sharpe -1 to -7)
- Total net across ALL windows: +R$1,729
- **Conclusion**: Strategy is regime-dependent. Works in trending markets, loses when ranging.

## Ablation Study (every component matters)

| Component removed | test_sharpe delta | Conclusion |
|---|---|---|
| ATR trailing stop | -1.10 | Most critical |
| RSI filter | -0.75 | Very important |
| ADX filter | -0.56 | Important |
| Bars remaining cutoff | -0.47 | Important |
| RSI strictness (65→55) | -0.20 | Moderate |
| PTAX skip | -0.12 | Least critical but still helps |

## What Was Exhaustively Tested and Rejected (~30 experiments)

### Entry Filters (all reduce trades below optimal ~100)
- +DI/-DI, MACD histogram, volume>SMA(20), StochRSI, Keltner, TSI, CCI, Williams %R
- BB squeeze, EMA gap threshold, VWAP confirm, prev-day return, meia perna
- Donchian breakout, asymmetric RSI/ADX, ADX rising, morning-only, close>open
- Day-of-week filters (Mon, Fri, etc.)

### Exit Modifications (none beat ATR+EMA reversal combo)
- Close below EMA(8) — exits too early
- Ratchet stop — marginally worse
- Re-entry after stop — adds bad trades
- Time stops (20, 30 bars) — fail train>0
- Breakeven stop — never triggers (ATR stop fires first)

### Other
- M15 timeframe — completely unprofitable (0 trades or negative)
- EMA(220) trend — test=2.91 but train barely negative (-0.02)
- Skip 12+13h — test=2.94 but train=-0.06
- Prev-day momentum — test=2.93 but train=-0.11

## Near-Misses (ideas that almost worked)

These were tantalizingly close to beating the baseline:
1. **Skip 12+13h**: test=2.94, train=-0.06 — if train could be made positive, this would be best
2. **Prev-day ret momentum**: test=2.93, train=-0.11 — same issue
3. **EMA(220) trend**: test=2.91, train=-0.02 — barely fails

## What to Try Next

1. **Regime detection**: Use rolling ADX or Hurst exponent to switch between trend and no-trade
2. **Machine learning**: Use sklearn/lightgbm with feature engineering from discovered indicators
3. **Ensemble**: Combine trend-following with a separate mean-reversion strategy
4. **Different entry signals**: Schaff Trend Cycle, DIDI Index (from expert guide, not yet tested)
5. **Higher timeframe trend**: Use H1 or Daily trend direction as regime filter (but careful of lookahead)
6. **Expand to new asset**: Apply framework to DI1, IBOV, or other Brazilian futures
7. **Walk-forward optimization**: Optimize parameters on rolling window, not single split

## CRITICAL RULES — ENFORCE ALWAYS

### Execution Model
1. **Fill at Open price** — `df["Open"].iloc[i]` for all fills
2. **1-bar signal delay per day** — `signals.groupby(df["date"]).shift(1).fillna(0).astype(int)`
3. **Sharpe uses ddof=1** — sample standard deviation
4. **BOTH train AND test Sharpe must be positive**
5. **No external data lookahead** — use PREVIOUS day's close

### Strategy Development Lessons
6. **Adding entry filters to ~100-trade strategy almost always hurts** — not enough signals
7. **Exit improvements are more impactful than entry filters**
8. **EMA better than SMA for trend filter** — faster reaction
9. **Crossover + trailing stop + reversal exit is the optimal exit combo**
10. **Walk-forward validation is essential** — single split can be misleading

## Additional Tests (post-initial handoff)

### Correlated Assets (DXY, VIX, USDBRL with D-1 lag)
- VIX under 25: test=2.84, train=0.24 (close but lower test)
- DXY trend/momentum: all make train negative
- USDBRL: same pattern
- **Conclusion**: External data with honest D-1 constraint adds NO edge

### Volume Bars (López de Prado)
- Only 8 months of M1 data (Jul 2025 - Mar 2026)
- Insufficient for proper train/test split with 200-bar indicators
- Need 2+ years of M1 data from MT5

### Machine Learning (LightGBM)
- Bar-by-bar prediction: catastrophic failure (Sharpe -3 to -14)
- Crossover quality filter: also fails (Sharpe -8 to -11)
- **Conclusion**: Not enough crossover samples (~260 in train) for ML to generalize

### Schaff Trend Cycle / DIDI Index
- STC entry: 321 noisy signals, train=-1.87
- STC as filter: over-restricts, train negative
- DIDI entry: 420 noisy signals, train=-1.71
- DIDI confirm: test=2.74 but train=-0.27

### SMA 108 Pullback (Expert Strategy)
- 248 trades, train=-1.79: too many false pullbacks with honest execution

## How to Resume
```
Read HANDOFF_SESSION3.md, then continue the autoresearch loop from test_sharpe=2.86.
Strategy is near its ceiling for indicator-based approaches.
Possible breakthroughs require: more data (10+ years M5, tick data from MT5/IB),
or fundamentally different market microstructure approach.
Enforce ALL critical rules. Both train+test must be positive.
```
