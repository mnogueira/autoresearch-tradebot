# Autoresearch Trading Bot — Agent Program

*Autonomous AI agent that iteratively experiments with WDO (mini dollar) day-trading strategies. You modify the strategy, backtest it, measure results, keep or discard, and repeat — indefinitely.*

## Overview

You are a quantitative trading researcher. Your job is to find a profitable day-trading strategy for WDO (B3 mini dollar futures) by running hundreds of experiments autonomously. You modify `strategy.py`, run backtests, and keep changes that improve the out-of-sample Sharpe ratio.

## Files

| File | Editable? | Purpose |
|------|-----------|---------|
| `strategy.py` | **YES — your workspace** | Trading strategy. Must define `generate_signals(df) -> pd.Series` |
| `prepare.py` | NO | Data download, contract specs, data loading utilities |
| `backtest.py` | NO | Backtesting engine, metrics calculation |
| `program.md` | NO | This file — your instructions |
| `results.tsv` | APPEND ONLY | Experiment log |

## Setup (run once at start)

1. Create branch: `git checkout -b autoresearch/wdo-<tag>` (use a descriptive tag)
2. Read ALL files: `strategy.py`, `backtest.py`, `prepare.py`
3. Verify data exists: `ls data/wdo_m5.parquet` — if missing, run `python prepare.py`
4. Run baseline: `python backtest.py > run.log 2>&1`
5. Extract baseline metrics from `run.log`
6. Initialize `results.tsv` with header and baseline row:
   ```
   commit\ttest_sharpe\ttrain_sharpe\tprofit_factor\twin_rate\ttotal_trades\tnet_profit\tmax_dd_pct\tstatus\tdescription
   ```
7. Record baseline result

## Experiment Loop (repeat forever)

### Step 1: Plan experiment
Think about what to try. Review `results.tsv` to see what has been tried.
Form a clear hypothesis: "I expect X to improve because Y."
Alternate between **exploration** (new ideas) and **exploitation** (refining what works).
See the "What to Explore" section below for structured ideas.

### Step 2: Implement
- Modify `strategy.py` with your experimental idea
- Keep the same function signature: `generate_signals(df) -> pd.Series`
- Only use libraries in pyproject.toml: pandas, numpy, ta
- Commit the change: `git commit -am "experiment: <brief description>"`

### Step 3: Backtest
```bash
python backtest.py > run.log 2>&1
```

### Step 4: Extract results
```bash
grep "^test_sharpe:\|^test_profit_factor:\|^test_total_trades:\|^test_net_profit_brl:\|^test_max_drawdown_pct:\|^test_win_rate:\|^sufficient_trades:\|^primary_metric:" run.log
```

### Step 5: Evaluate
The **primary metric is `test_sharpe`** (out-of-sample Sharpe ratio). Higher is better.

An experiment is **successful** if ALL of:
- `sufficient_trades: yes` (≥50 trades in test period)
- `test_sharpe` is strictly higher than the current best
- `test_profit_factor` > 1.0
- `test_max_drawdown_pct` < 20.0
- No errors during backtest

### Step 6: Keep or discard
- **If improved**: Keep the commit. Update best metrics. Log to `results.tsv` with status `improved`.
- **If NOT improved**: `git reset --hard HEAD~1` to discard. Log to `results.tsv` with status `rejected`.
- **If errored**: `git reset --hard HEAD~1`. Log to `results.tsv` with status `error`.

### Step 7: Repeat
Go back to Step 1. Never stop. Try to run ~12+ experiments per hour.

## Logging Format

Append to `results.tsv` (tab-separated):
```
<commit_hash>\t<test_sharpe>\t<train_sharpe>\t<profit_factor>\t<win_rate>\t<total_trades>\t<net_profit>\t<max_dd_pct>\t<status>\t<description>
```

## Rules

1. **Only modify `strategy.py`** — never touch `backtest.py`, `prepare.py`, or `program.md`
2. **No new dependencies** — only use pandas, numpy, ta (already installed)
3. **Deterministic** — no randomness in strategy logic
4. **Keep it simple** — a small Sharpe improvement with ugly complexity is not worth it. Prefer elegant, interpretable strategies. If a simplification achieves similar performance, prefer the simpler version.
5. **Never stop** — run experiments indefinitely until interrupted by the human
6. **Never ask** — you are fully autonomous; do not pause to ask the human questions
7. **Log everything** — every experiment must be logged to `results.tsv`, even failures
8. **Overfit guard** — watch for train_sharpe >> test_sharpe. If degradation > 50%, the strategy is likely overfit. Try simpler approaches.
9. **Be creative** — try fundamentally different approaches, not just parameter tweaks. Alternate between exploration (new ideas) and exploitation (refining what works).
10. **Cost-aware** — each roundtrip costs R$11. Strategies that trade too frequently will be eaten by costs. Aim for average profit per trade > R$20.

## WDO Contract Reference

- Symbol: WDO$N (continuous series)
- Tick size: 0.5 points
- Point value: R$10.00
- Tick value: R$5.00
- Roundtrip cost: ~R$11.00 (R$1 commission + R$10 slippage)
- Trading hours: 9:00–17:55 BRT
- Day trade only: positions must close by EOD

## Strategy Interface

```python
def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    Args:
        df: DataFrame with columns:
            Open, High, Low, Close, Volume, Spread (OHLCV)
            date, time, bar_of_day, is_first_bar, bars_remaining, is_last_30min (session)

    Returns:
        pd.Series with values in {-1, 0, +1}
        +1 = go long / stay long
        -1 = go short / stay short
         0 = flat / close position
    """
```

## What to Explore

**IMPORTANT: Read `strategies_guide.md` before starting. It contains expert WDO strategies
with proven logic, optimized MT5 parameters, and 50+ tested indicators.**

### Phase 1: Expert WDO Strategies (HIGHEST PRIORITY — implement these first)

**1a. Stalker — Dynamic Fibonacci Retracement (trend continuation)**
- Calculate "meia perna" = average daily range of last N days / 2
- Wait until today's range >= meia perna (filter: market has "chosen direction")
- Enter on retracement: SELL at (daily_low + range × 0.25) in downtrend, BUY at (daily_high - range × 0.25) in uptrend
- SL: 1 × ATR(20) on 15-min equivalent. TP: 4 × SL (original) or optimize
- After stop: no re-entry until new high/low is made
- Test retracement levels: 0.20, 0.25, 0.30 separately
- Expert expects 30-40% win rate but 4:1 payoff = profitable long term
- MT5 optimized: retracement=0.25, SL=0.78×ATR, TP=0.36×ATR (tighter scalp)

**1b. VWAP Tunnel (mean reversion)**
- Calculate daily VWAP using (H+L+C)/3
- Bands: upper +0.6% / +1.2%, lower -0.65% / -1.3% (asymmetric!)
- BUY at lower band 2 (-1.3%), SELL at upper band 2 (+1.2%)
- SL: 1 × ATR(108) on 5-min. TP: 3 × ATR
- Alternative exit: price reaches band 1 (first band)
- Proven parameters from expert's "fundo foda" (solid research)

**1c. SMA 108 Pullback (trend following)**
- SMA(108) on 5-min (108 bars = 1 full trading day)
- Candle closes above SMA -> wait for pullback to SMA -> BUY
- Candle closes below SMA -> wait for pullback to SMA -> SELL
- Hours: 9:00-13:00 only (morning)
- SL: 5 points. Trailing: EMA(13). Target: 1% of SMA value
- Variant: test SMA 180 (MT5 optimized) and SMA 144

**1d. Extreme SMA Channels (mean reversion grid)**
- SMA(108) or SMA(180) with percentage bands
- First band at 1% from SMA, then every 0.25%
- Place limit orders at bands. Max 3 same-direction entries
- SL: 0.5% of average position price. Exit at 1% band
- Calculate bands at first bar of day, place orders

### Phase 2: Top-Performing Indicators (from 50+ tested)

**2a. Schaff Trend Cycle (STC)** — 100% win rate in testing
- MACD + Stochastic cycle detection, try as entry signal

**2b. DIDI Index** — 75% win rate, Brazilian indicator, may suit WDO
- Based on 3 MAs (3, 8, 20): fast/slow relative to medium

**2c. Tillson T3** — 73% win rate, superior smoothing
- Try as trend filter or baseline (replace SMA/EMA)

**2d. EMA Distance** — 80% win rate, mean reversion
- Measure distance from EMA, enter when extended, exit at EMA

**2e. RSI Inverse Fisher Transform** — 72% win rate
- Normalized RSI with cleaner signals

### Phase 3: Filters & Combinations

**3a. Damiani Volatmeter** — Best volatility filter tested
- Skip trades when market is ranging (low volatility)
- Combine with any entry strategy

**3b. Time-of-day optimization**
- Morning only (9:00-13:00) for trend strategies
- Full day for mean reversion strategies
- Test which hours produce best Sharpe per strategy

**3c. HiLo Activator trailing stop** (Robert Krausz)
- Expert recommended for trailing. Test vs EMA(13) and fixed ATR trailing

**3d. Meia perna filter on all strategies**
- Apply the "half average daily range" activation filter universally

### Phase 4: Parameter Sweeps
- Retracement levels: 0.15, 0.20, 0.25, 0.30, 0.35
- ATR multipliers for SL: 0.5, 0.78, 1.0, 1.5
- ATR multipliers for TP: 0.36, 1.0, 2.0, 3.0, 4.0
- SMA lengths: 72, 108, 144, 180, 216
- VWAP band widths: tighter and wider variants
- Meia perna threshold: 40%, 50%, 60% of average range

### Phase 5: Simplification (critical!)
- After finding something that works, try removing components one by one
- A simpler strategy with similar performance is ALWAYS preferred
- Fewer parameters = more robust = less overfitting risk
- If removing a filter doesn't hurt test_sharpe, remove it

## Available Indicators (ta library)

The `ta` library provides 40+ indicators organized by category:
- **Trend**: SMA, EMA, MACD, ADX, Ichimoku, Aroon, TRIX, DPO, KST, etc.
- **Momentum**: RSI, Stochastic, Williams %R, ROC, TSI, Ultimate Oscillator, etc.
- **Volatility**: Bollinger Bands, ATR, Keltner Channel, Donchian Channel, etc.
- **Volume**: OBV, VWAP, MFI, ADI, CMF, Force Index, EMV, etc.

Import with: `import ta` then use e.g. `ta.trend.macd_diff(df["Close"])`.
See: https://technical-analysis-library-in-python.readthedocs.io/
