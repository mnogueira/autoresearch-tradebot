# Strategy Modules

The actively maintained strategy modules now live under `src/autoresearch_tradebot/strategies/`.

## Modules

- `ema_wdo.py`
  5-minute EMA/ADX/RSI/TRIX/Hurst strategy with overlap checks against 1-minute execution data.
- `stalker_wdo.py`
  15-minute retracement strategy with optional 1-hour filter and 1-minute execution support.
- `stalker_wdo_revalidate.py`
  Lower-timeframe validation pass for the `stalker_wdo` holdout and walk-forward outputs.
- `stalker_v10_python.py`
  Python port of the MT5 Stalker v10 logic using M1 input data.
- `opening_double_bar.py`
  Deterministic opening-bar setup with fixed stop/target logic.
- `no_wick_bar_momentum_wdo.py`
  No-wick momentum strategy with M15 signals and M1 execution simulation.
- `paper_trade_mt5.py`
  Paper/live execution harness wrapped around the EMA strategy parameters.

## Artifact Defaults

By default these scripts now write to `artifacts/outputs/` or `artifacts/reports/` instead of cluttering the repo root.

Examples:

- `artifacts/outputs/ema_wdo/`
- `artifacts/outputs/stalker_wdo/`
- `artifacts/outputs/stalker_v10_python/`
- `artifacts/reports/opening_double_bar/`
