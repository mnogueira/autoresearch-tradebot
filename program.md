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
Think about what to try. Ideas to explore (not exhaustive):
- Different indicator combinations (MACD, Bollinger, ATR, VWAP, OBV, Stochastic, etc.)
- Different timeframe analysis (use M1, M15, H1 data alongside M5)
- Trend-following vs mean-reversion approaches
- Volatility-based filters (only trade when ATR is in a certain range)
- Time-of-day filters (which hours are most profitable?)
- Pattern recognition (inside bars, engulfing, pin bars)
- Momentum and volume confirmation
- Adaptive parameters (adjust based on recent volatility)
- Risk management: stop-loss, take-profit, trailing stops
- Multiple entry/exit conditions
- Session-specific strategies (opening range, lunch, afternoon trend)

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

## Available Indicators (ta library)

The `ta` library provides 40+ indicators organized by category:
- **Trend**: SMA, EMA, MACD, ADX, Ichimoku, Aroon, TRIX, DPO, KST, etc.
- **Momentum**: RSI, Stochastic, Williams %R, ROC, TSI, Ultimate Oscillator, etc.
- **Volatility**: Bollinger Bands, ATR, Keltner Channel, Donchian Channel, etc.
- **Volume**: OBV, VWAP, MFI, ADI, CMF, Force Index, EMV, etc.

Import with: `import ta` then use e.g. `ta.trend.macd_diff(df["Close"])`.
See: https://technical-analysis-library-in-python.readthedocs.io/
