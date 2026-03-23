# Repository Guide

This repo now separates the long-lived project assets from one-off research output.

## Primary Zones

- `src/autoresearch_tradebot/legacy/`
  Legacy backtesting loop, baseline strategy, and older research utilities.
- `src/autoresearch_tradebot/legacy/experiments/`
  Archived research scripts that were previously misnamed as `test_*.py`.
- `src/autoresearch_tradebot/strategies/`
  Strategy-specific runners with their own optimization and reporting flows.
- `src/autoresearch_tradebot/mt5/`
  MT5 automation that syncs repo assets into the runtime before compiling or testing.
- `tests/`
  Unit tests for the maintained strategy modules.

## Data, Research, and Runtime

- `data/`
  Local parquet inputs used by the Python strategy modules.
- `research/source_material/`
  Raw transcripts, playlists, and supporting strategy notes.
- `research/legacy/results.tsv`
  Historical experiment ledger for the original autoresearch loop.
- `mt5/experts/custom/`
  The repo-owned MQ5 source files worth keeping.
- `mt5/profiles/tester/`
  The tester presets still referenced by the automation.
- `runtime/mt5-portable/`
  Optional local MT5 runtime and binaries.

## Generated Output Policy

- Put rerun output under `artifacts/outputs/`.
- Put generated markdown/CSV reports under `artifacts/reports/`.
- Put legacy progress charts under `artifacts/legacy/`.
- Do not recreate root-level `outputs/`, `reports/`, or loose log files.
