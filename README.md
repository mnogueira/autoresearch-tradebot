# Autoresearch Tradebot

WDO strategy research, validation, and MT5 automation toolkit.

The repository is organized around durable source code instead of ad hoc run artifacts:

- `src/autoresearch_tradebot/legacy/`: the original autoresearch loop and older research scripts.
- `src/autoresearch_tradebot/strategies/`: standalone strategy runners and paper-trading logic.
- `src/autoresearch_tradebot/mt5/`: MT5 export, tester, and calibration automation.
- `tests/`: real unit tests only.
- `data/`: local parquet inputs used by the repo.
- `research/`: preserved source material and the legacy experiment log.
- `mt5/`: MT5 source-of-truth experts and tester profiles.
- `runtime/mt5-portable/`: optional local MT5 portable runtime.
- `artifacts/`: generated outputs, reports, and rerun products.

## Quick Start

Install the package in editable mode:

```powershell
pip install -e .[analysis,ml,dev]
```

Add `.[mt5]` when working with MetaTrader 5 integration.

Run the unit test suite:

```powershell
python -m unittest discover -s tests -v
```

Run the archived legacy backtest loop:

```powershell
python -m autoresearch_tradebot.legacy.backtest
```

Inspect the strategy runners:

```powershell
python -m autoresearch_tradebot.strategies.ema_wdo --help
python -m autoresearch_tradebot.strategies.stalker_wdo --help
python -m autoresearch_tradebot.strategies.stalker_v10_python --help
```

MT5-specific workflows are documented in `docs/mt5-workflows.md`.

## Conventions

- Durable code belongs under `src/`, `tests/`, `docs/`, `research/`, or `mt5/`.
- Generated outputs belong under `artifacts/`.
- MT5 runtime churn stays under `runtime/mt5-portable/` and is ignored where appropriate.
- Root-level scratch files, reports, and logs are intentionally avoided.
