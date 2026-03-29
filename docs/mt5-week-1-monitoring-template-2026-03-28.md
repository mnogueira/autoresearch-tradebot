# MT5 Week 1 Monitoring Template - 2026-03-28

## Goal

Track the first paper-trading week in one place so the desk can decide whether to stay on Tier 1, promote to Tier 2, or stand down.

## Daily Fields

Use one row per paper-trading session.

| Date | Tier | Trades | Net PnL (R$) | Win Rate | Avg Entry Spread (ticks) | Max Spread (ticks) | Rolling 5d PF | Rolling 20d PF | Rolling 30d PF | Current DD % | Max DD % | MT5 Errors? | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2026-03-30 | Tier 1 |  |  |  |  |  |  |  |  |  |  |  |  |

## Minimum Daily Checklist

1. Confirm the tier in use:
   - Tier 1 on Monday
   - Tier 2 only after `5` clean paper sessions
   - Tier 3 only after another clean week
2. Export the MT5 trade log and daily PnL CSV after the session.
3. Build the monitoring snapshot JSON from the exported trade log.
4. Build the session-health JSON from the monitoring snapshot.
5. Fill the worksheet row before the next session starts.

## Snapshot Commands

1. Export MT5 trade log and daily PnL:
   - `python -m autoresearch_tradebot.mt5.export_tester_trade_log --report artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/mt5_model_0_report.html --trades-out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/trade_log.csv --daily-out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/daily_pnl.csv`
2. Build the monitoring snapshot JSON:
   - `python -m autoresearch_tradebot.mt5.build_monitoring_snapshot --trade-log artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/trade_log.csv --session-date 2026-03-19 --out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json`
   - installed CLI: `tradebot-mt5-monitoring-snapshot`
3. Build the session-health JSON:
   - `python -m autoresearch_tradebot.mt5.assess_paper_session --snapshot artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json --max-spread-ticks 1 --completed-sessions 5 --current-tier "Tier 1" --out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/session_health.json`
   - installed CLI: `tradebot-mt5-paper-health`

## Green / Yellow / Red Thresholds

- Green:
  - spread mostly `0-1` tick
  - rolling `30d` PF `> 1.2`
  - current DD below historical `p90`
  - no repeated MT5 execution errors
- Yellow:
  - spread often touches `2` ticks
  - rolling `30d` PF between `1.0` and `1.2`
  - current DD between historical `p90` and `p95`
  - one-off MT5 execution issues
- Red:
  - live spread repeatedly `> 2` ticks
  - rolling `30d` PF `< 1.0`
  - current DD above historical `p95`
  - repeated MT5 execution errors or out-of-window entries

## Promotion Rules

1. Stay on Tier 1 for the first full paper-trading week.
2. Promote to Tier 2 only if all are true:
   - `5` consecutive paper sessions completed
   - no red days
   - fills stayed near the `0-1` tick expectation
   - realized behavior stayed directionally consistent with the saved artifact
3. Promote to Tier 3 only after another clean week on Tier 2.

## Stand-Down Rules

- Stop the session immediately if spread is above `2` ticks during the entry windows.
- Pause the strategy after `5` consecutive losing days.
- Pause if trailing `30`-day PF drops below `1.0`.
- Treat the last `3` contract days before rollover as caution days.

## Notes

- The biggest remaining upside is still execution quality, not more signal complexity.
- Research-only result: a hypothetical one-tick better fill on every trade was very strong.
- But delaying one extra minute after the signal was strongly negative, so do not convert the live workflow into a "wait and see" entry process.
