# MT5 Workflows

MT5 automation now uses a clean split between repo assets and runtime state.

## Source vs Runtime

- `mt5/experts/custom/`
  Repo-owned `.mq5` experts that should be edited and reviewed.
- `mt5/profiles/tester/`
  Repo-owned `.set` files that the calibration/test flows depend on.
- `runtime/mt5-portable/`
  Local runtime folder containing the terminal, MetaEditor, and whatever MT5 recreates at runtime.

The Python MT5 scripts sync the needed expert or tester profile into the runtime before compiling or running.

## Common Commands

History export:

```powershell
python -m autoresearch_tradebot.mt5.run_mt5_history_export --portable
```

Stalker v10 MT5 test:

```powershell
python -m autoresearch_tradebot.mt5.run_mt5_stalker_v10_test --output-dir artifacts/outputs/mt5_stalker_v10 --report-name report.html --compile
```

Python vs MT5 calibration:

```powershell
python -m autoresearch_tradebot.mt5.calibrate_stalker_v10_mt5 --compile --portable
```

Real tick export:

```powershell
python -m autoresearch_tradebot.mt5.export_mt5_real_ticks
```

## Notes

- When a portable runtime is present at `runtime/mt5-portable/`, it is preferred automatically.
- If the portable runtime is absent, the scripts fall back to a standard MT5 installation when possible.
- Runtime caches, tester data, and logs are intentionally not treated as source code.
