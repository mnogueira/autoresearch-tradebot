# Autoresearch Tradebot — Handoff for New Session

## What is this?

An autonomous AI research loop that iteratively finds profitable day-trading strategies for
**WDO (B3 mini dollar futures)** — adapted from Karpathy's autoresearch methodology.

You are being handed a fully set up project. Your job: **run the experiment loop indefinitely**.

---

## Quick Start

```bash
# 1. Read the full instructions
cat program.md

# 2. Read the strategy research (expert knowledge + 50 tested indicators)
cat strategies_guide.md

# 3. Verify data exists
ls data/

# 4. Run the loop as described in program.md
```

Follow `program.md` exactly — it contains the full experiment loop instructions.

---

## Project State

### What's already done
- **Infrastructure**: prepare.py (data pipeline), backtest.py (backtesting engine), strategy.py (agent-editable), plot_progress.py (Karpathy-style chart)
- **Data downloaded** (all in `data/` directory):
  - `wdo_m1.parquet` — 94,015 bars, 176 days (Jul 2025 → Mar 2026)
  - `wdo_m5.parquet` — 95,935 bars, 891 days (Aug 2022 → Mar 2026) ← primary
  - `wdo_m15.parquet` — 44,844 bars, 1,248 days (Mar 2021 → Mar 2026)
  - `wdo_h1.parquet` — 11,212 bars, 1,248 days (Mar 2021 → Mar 2026)
- **Strategy research** in `strategies_guide.md`:
  - 4 expert WDO strategies from professional trader (Stalker, VWAP Tunnel, SMA 108, Extreme)
  - 50+ indicators tested with win rates (from YouTube research)
  - Implementation priority roadmap (Phase 1-5)
- **YouTube transcripts** in `all_transcripts.txt` (606KB) and `all_transcripts.json`
- **Baseline result**: EMA(9)/EMA(21) crossover → test_sharpe = -1.37 (unprofitable, expected)
- **GitHub repo**: https://github.com/mnogueira/autoresearch-tradebot
- **Git**: initialized on `master` branch, 2 commits

### What's NOT done yet
- No `results.tsv` created yet (you create it in setup phase)
- No experiments run yet — you start from scratch
- Baseline strategy in strategy.py is intentionally bad (the starting point to improve from)

---

## Key Files to Read

| Priority | File | Why |
|----------|------|-----|
| 1 | `program.md` | **Your full instructions** — the experiment loop, rules, what to explore |
| 2 | `strategies_guide.md` | Expert WDO strategies + ranked indicators — what to implement |
| 3 | `strategy.py` | Current strategy code — what you modify each experiment |
| 4 | `backtest.py` | How backtesting works — understand before modifying |
| 5 | `prepare.py` | Data pipeline — understand before adding data sources |

---

## You Have NO LIMITS

Unlike Karpathy's original (where only train.py is editable), you can:
- **Modify ANY file** — backtest engine, data pipeline, everything
- **Install packages** — `pip install sklearn lightgbm xgboost yfinance` etc.
- **Download new data** — correlated assets, economic indicators, Google Trends
- **Search the internet** — for new strategies, academic papers, indicator ideas
- **Create new files** — helper scripts, notebooks, whatever you need
- **Try ANY approach** — ML, statistics, patterns, multi-timeframe, ensembles

---

## Telegram Notifications (Optional)

The user wants to receive Telegram messages when you find a better strategy.

### How to check if Telegram is available
Before attempting to send, check if the `mcp__plugin_telegram_telegram__reply` tool is
available in your tool list. If it is NOT available, skip Telegram entirely — just log
improvements to stdout and `results.tsv`.

### If Telegram IS available
1. Check if `telegram_chat_id.txt` exists in the project root — if so, read the chat_id from it
2. If the file doesn't exist, wait for an incoming Telegram message (it will arrive as a
   `<channel source="telegram" chat_id="..." ...>` tag) and save that chat_id to
   `telegram_chat_id.txt` for future use
3. On each **improvement only** (not rejections/errors):
   a. Run `python plot_progress.py` to generate `progress.png`
   b. Send via `mcp__plugin_telegram_telegram__reply`:
      - `chat_id`: from file or incoming message
      - `text`: experiment summary (strategy description, test_sharpe, profit_factor,
        win_rate, total_trades, net_profit, max_drawdown, comparison to previous best)
      - `files`: `["C:\\Dev\\autoresearch-tradebot\\progress.png"]`
4. If sending fails for any reason, log the error and **continue the loop** — never stop for Telegram issues

### If Telegram is NOT available
Just continue the loop normally. Print improvements to stdout. The user can check
`results.tsv` and run `python plot_progress.py` manually to see progress.

---

## WDO Contract Quick Reference

- **Symbol**: WDO$N (MT5 continuous series) / WDO1! (TradingView)
- **Tick size**: 0.5 points | **Point value**: R$10.00 | **Tick value**: R$5.00
- **Roundtrip cost**: ~R$11.00 (R$1 XP commission + R$10 slippage)
- **Trading hours**: 9:00–17:55 BRT (day trade, must close by EOD)
- **SMA 108 on M5** = exactly 1 full trading day of bars (108 × 5min = 9hrs)
- **Data**: the user has MT5 connected to XP demo account if you need fresh data

---

## Expert Strategy Concepts (Key Ideas)

These come from a professional WDO trader — implement and test them:

1. **"Meia perna"** (half-leg filter): don't trade until the market has moved at least half
   its average daily range. This ensures a trend has been established before entering.

2. **Dynamic Fibonacci retracement**: after meia perna activates, enter on pullbacks
   (20-30% retracement of the day's range) expecting trend continuation.

3. **VWAP tunnel with asymmetric bands**: upper +0.6%/+1.2%, lower -0.65%/+1.3%.
   The asymmetry comes from research showing downside moves are sharper.

4. **Contract-aware calculations**: WDO contracts expire monthly. Calculate average
   daily range per contract, not rolling 30 days. First 5 days of new contract
   use previous contract's average.

---

## Metrics That Matter

- **Primary**: `test_sharpe` (out-of-sample Sharpe ratio) — higher is better
- **Must have**: `test_profit_factor` > 1.0, `test_max_drawdown_pct` < 20%
- **Minimum**: ≥50 trades in test period
- **Watch for**: train/test degradation > 50% = overfitting

---

## How to Launch This Session

### Without Telegram (simplest)
```bash
cd C:\Dev\autoresearch-tradebot
claude
# Then paste: "Read HANDOFF.md and program.md, then start the autoresearch loop"
```

### With Telegram notifications
```bash
cd C:\Dev\autoresearch-tradebot
claude --channels plugin:telegram@claude-plugins-official
# Then paste: "Read HANDOFF.md and program.md, then start the autoresearch loop"
# Send a message to the Telegram bot so the session captures your chat_id
```

---

## Important Notes

- The user's expert partner (Joabe/Clarian Solutions) developed the strategies but the
  MQL5 implementations were learning exercises and never achieved profitability. Trust the
  **strategy concepts**, not the specific parameter values from the MT5 code.
- There's another tradebot project at `C:\Dev\tradebot` (29k LOC, ML-based) — you can
  read it for reference but do NOT modify it.
- The user has an NVIDIA GPU available if you want to try ML approaches.
- The user has TradingView Pro — you can reference TV indicator ideas.
- **IB Gateway is running** (paper trading account) — you can use `ib_async` or `ib_insync`
  to fetch data from Interactive Brokers if needed (US markets, global indices, etc.).
  IB paper trading port is 4002.
