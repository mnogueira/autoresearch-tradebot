# Legacy Autoresearch Loop

This is the archived Karpathy-style experiment loop that originally drove the project.

The code now lives under `src/autoresearch_tradebot/legacy/`, but the flow is still runnable.

## Key Files

- `src/autoresearch_tradebot/legacy/prepare.py`
- `src/autoresearch_tradebot/legacy/backtest.py`
- `src/autoresearch_tradebot/legacy/strategy.py`
- `src/autoresearch_tradebot/legacy/plot_progress.py`
- `research/legacy/results.tsv`

## Commands

Prepare data:

```powershell
python -m autoresearch_tradebot.legacy.prepare
```

Run the baseline backtest:

```powershell
python -m autoresearch_tradebot.legacy.backtest
```

Generate the legacy progress chart:

```powershell
python -m autoresearch_tradebot.legacy.plot_progress --input research/legacy/results.tsv --output artifacts/legacy/progress.png
```

## Notes

- The legacy experiment history is preserved at `research/legacy/results.tsv`.
- Older research utilities are now grouped under `src/autoresearch_tradebot/legacy/experiments/`.
- New work should prefer the maintained strategy modules under `src/autoresearch_tradebot/strategies/`.
