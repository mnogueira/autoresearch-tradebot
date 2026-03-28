# Stalker v10.1 Strategy Health Dashboard - 2026-03-28

## Goal

Provide one lightweight JSON snapshot that can be checked remotely during paper trading without opening MT5 or the raw HTML report.

## Data Source

- Primary script:
  - `src/autoresearch_tradebot/mt5/build_monitoring_snapshot.py`
- Inputs:
  - MT5 tester HTML report, or
  - previously exported `trade_log.csv`

## Recommended Panels

| Panel | Metric | Why It Matters |
| --- | --- | --- |
| Daily PnL chart | last `10` daily rows, cumulative equity | Fast visual check for drift, clustering, and paper-execution issues |
| Rolling PF | `5d`, `20d`, `30d`, `60d` profit factor | Short window catches sudden degradation; longer window smooths noise |
| Current DD | current `BRL` and `%` drawdown | Tells the operator where the strategy is right now versus its own peak |
| Historical DD distribution | `p50`, `p90`, `p95`, `max` drawdown `%` | Lets the desk compare current pain to historically normal pain |
| Trade activity | total trades, trading days, expected trades/day | Sets realistic expectations for Monday monitoring |

## Minimal Operator Interpretation

- Healthy:
  - rolling `30d` PF stays above `1.0`
  - current drawdown stays below the historical `p95` drawdown band
  - realized trades/day stays roughly in the expected band for the selected tier
- Caution:
  - rolling `30d` PF trends toward `1.0`
  - current drawdown is near or above the historical `p95`
  - spread/fill quality is visibly worse than the backtest assumptions
- Pause:
  - rolling `30d` PF below `1.0`
  - repeated execution issues
  - drawdown moves materially beyond the historical worst case

## JSON Shape

The monitoring snapshot currently emits:

- `last_trade_time`
- `total_trades`
- `trading_days`
- `expected_trades_per_day`
- `latest_daily_pnl_brl`
- `rolling_pnl_brl`
- `rolling_profit_factor`
- `drawdown`
- `historical_drawdown_distribution_pct`
- `last_10_daily_rows`

## Example Output

- Tier 1 tested snapshot:
  - `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json`

## Monday Use

- Run Tier 1 first.
- Export the trade log after the tester run or after the session.
- Build the monitoring snapshot JSON.
- Compare:
  - current drawdown vs historical `p95`
  - rolling `30d` PF vs `1.0`
  - realized trades/day vs expected trades/day
