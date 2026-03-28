# WDO Stalker Strategy Report

## Setup
- 15m source: `C:\Dev\tradebot\storage\bars\B3\WDO\15m.parquet`
- 1h source: `C:\Dev\tradebot\storage\bars\B3\WDO\1h.parquet`
- 1m source: `C:\Dev\tradebot\storage\bars\B3\WDO\1m.parquet`
- 15m sample: `2021-03-22` -> `2026-03-20` (1248 trading days)
- Holdout split: `873` train days / `375` test days
- Walk-forward windows: `14` windows, `252` total days each, `70/30` train/test inside each window
- Signal bars are 15m, optional confirmation filter is previous completed 1h EMA trend, and execution is modeled with causal resting limit orders.
- Entry orders are activated from the next 15m bar only; same-bar stop/target conflicts are resolved pessimistically with stop first.

## Optimized Holdout Parameters
- `range_reference_mode`: `contract_expanding`
- `range_lookback_days`: `21`
- `prev_contract_days`: `4`
- `activation_basis`: `directional_leg`
- `activation_threshold_frac`: `0.4`
- `fib_basis`: `session_range`
- `retracement_frac`: `0.3`
- `min_range_points`: `0.0`
- `atr_timeframe`: `1h`
- `atr_period`: `11`
- `stop_atr_mult`: `1.35`
- `target_atr_mult`: `0.25`
- `use_1h_filter`: `False`
- `h1_fast_ema`: `14`
- `h1_slow_ema`: `12`
- `max_trades_per_day`: `2`
- `last_entry_time`: `16:45`
- `session_exit_time`: `17:30`

## Holdout Metrics

| Metric | Train | Test |
|---|---:|---:|
| Sharpe | 7.3913 | 4.2269 |
| Win rate | 94.71% | 93.32% |
| Net profit (BRL) | 32296.00 | 7791.00 |
| Max drawdown | 0.67% | 0.75% |
| Profit factor | 3.5259 | 2.2072 |
| Trades | 1059 | 434 |

## Walk-Forward Aggregate Metrics

- Sharpe: `3.1902`
- Win rate: `83.09%`
- Net profit (BRL): `16043.00`
- Max drawdown: `1.28%`
- Profit factor: `1.6961`
- Trades: `1017`

## Walk-Forward Windows

| Window | Train | Test | Test Sharpe | Test PF | Test Trades | Test Net |
|---|---|---|---:|---:|---:|---:|
| 1 | 2021-03-22 -> 2021-12-02 | 2021-12-03 -> 2022-03-24 | 3.3823 | 1.5449 | 103 | 1627.0 |
| 2 | 2021-07-12 -> 2022-03-24 | 2022-03-25 -> 2022-07-13 | 5.3339 | 2.2584 | 93 | 2747.0 |
| 3 | 2021-10-28 -> 2022-07-13 | 2022-07-14 -> 2022-10-31 | 5.5904 | 3.1352 | 48 | 1642.0 |
| 4 | 2022-02-17 -> 2022-10-31 | 2022-11-01 -> 2023-02-17 | 4.3827 | 2.4522 | 61 | 1429.0 |
| 5 | 2022-06-09 -> 2023-02-17 | 2023-02-22 -> 2023-06-13 | 3.7897 | 1.6579 | 106 | 1294.0 |
| 6 | 2022-09-27 -> 2023-06-13 | 2023-06-14 -> 2023-09-28 | 9.3003 | 2.8956 | 95 | 1960.0 |
| 7 | 2023-01-17 -> 2023-09-28 | 2023-09-29 -> 2024-01-22 | 4.086 | 2.7816 | 42 | 718.0 |
| 8 | 2023-05-10 -> 2024-01-22 | 2024-01-23 -> 2024-05-13 | 3.7419 | 2.4409 | 39 | 451.0 |
| 9 | 2023-08-25 -> 2024-05-13 | 2024-05-14 -> 2024-08-28 | 2.3374 | 1.617 | 53 | 857.0 |
| 10 | 2023-12-15 -> 2024-08-28 | 2024-08-29 -> 2024-12-16 | 6.7596 | 2.6566 | 75 | 2470.0 |
| 11 | 2024-04-09 -> 2024-12-16 | 2024-12-17 -> 2025-04-09 | 0.8231 | 1.1095 | 96 | 489.0 |
| 12 | 2024-07-26 -> 2025-04-09 | 2025-04-10 -> 2025-07-30 | 0.4585 | 1.0716 | 50 | 125.0 |
| 13 | 2024-11-11 -> 2025-07-30 | 2025-07-31 -> 2025-11-13 | -0.7243 | 0.8947 | 101 | -231.0 |
| 14 | 2025-03-07 -> 2025-11-13 | 2025-11-14 -> 2026-03-10 | 1.5053 | 1.4141 | 55 | 465.0 |
