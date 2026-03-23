# CLAUDE.md

Repository notes for AI collaborators and future cleanup passes.

## Source Layout

- `src/autoresearch_tradebot/legacy/`
  The original Karpathy-style autoresearch loop plus older exploratory scripts.
- `src/autoresearch_tradebot/strategies/`
  Standalone WDO strategy implementations, validation flows, and paper trading.
- `src/autoresearch_tradebot/mt5/`
  MT5 runtime helpers, exporter runners, tester automation, and calibration scripts.
- `src/autoresearch_tradebot/common/`
  Shared repo-path and WDO data discovery helpers.
- `tests/`
  Real unit tests only. Research scripts no longer masquerade as tests.

## Non-Code Areas

- `data/`
  Local parquet inputs used by the repo during research and validation runs.
- `research/source_material/`
  Transcript dumps, playlist metadata, and supporting strategy notes.
- `research/legacy/results.tsv`
  Preserved experiment log from the original autoresearch loop.
- `mt5/`
  Source-of-truth `.mq5` experts and tester `.set` files.
- `runtime/mt5-portable/`
  Optional portable MT5 runtime. Runtime churn is ignored.
- `artifacts/`
  Generated outputs, reports, progress charts, and rerun products.

## Working Rules

- Prefer `python -m ...` entrypoints from the package.
- Keep new durable code under `src/` and new tests under `tests/`.
- Send generated files to `artifacts/`, not to the repo root.
- Treat `mt5/` as source and `runtime/mt5-portable/` as disposable runtime state.
- Keep docs aligned with the actual folder structure whenever commands or paths change.
