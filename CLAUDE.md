# Autoresearch Tradebot

Autonomous AI research loop for WDO (B3 mini dollar futures) day-trading strategy optimization.
Adapted from Karpathy's autoresearch methodology.

## Architecture

- `prepare.py` — READ-ONLY. Data download from MT5, contract specs, utilities.
- `backtest.py` — READ-ONLY. Backtesting engine with realistic cost modeling.
- `strategy.py` — AGENT-EDITABLE. The trading strategy. Only file the agent modifies.
- `program.md` — Agent instructions for the autonomous experiment loop.

## How to run

1. Ensure MT5 is running and connected to XP demo account
2. Download data: `python prepare.py`
3. Run single backtest: `python backtest.py`
4. Start autonomous loop: point Claude at `program.md` and let it run

## Key constraints

- Only `strategy.py` is modified by the agent
- No new dependencies (pandas, numpy, ta only)
- Primary metric: out-of-sample Sharpe ratio (test_sharpe)
- Day trading only, positions close by 17:55
- WDO contract: tick=0.5pts, point=R$10, roundtrip cost=R$11

## Data

- Source: MetaTrader 5 (XP demo account)
- Symbol: WDO$N (continuous series)
- Default timeframe: 5-minute bars
- Split: 70% train / 30% test (chronological)
