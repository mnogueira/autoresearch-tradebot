# MT5 Monday Morning Checklist - 2026-03-30

## Primary Decision

- Run Tier 1 only.
- Do not promote the corrected Python upgrade tiers on Monday.

## Exact Paths

1. MT5 terminal:
   - `C:\Program Files\MetaTrader 5 Terminal\terminal64.exe`
2. EA source:
   - `C:\Dev\autoresearch-tradebot\mt5\experts\custom\WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
3. Monday preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`

## Before The Open

1. Open MT5 and let history sync.
2. Compile the EA in MetaEditor.
3. Open Strategy Tester and set:
   - Expert: `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
   - Symbol: terminal continuous WDO symbol
   - Timeframe: `M1`
   - Model: `Every Tick`
4. Load the Tier 1 preset.
5. Run one clean sanity backtest.

## Sanity Checks

1. Confirm spread behavior before enabling paper trading:
   - `0-1` tick normal
   - `2` ticks maximum tolerable
   - `>2` ticks means no trade
2. Confirm the tester result is directionally consistent with:
   - [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json)
3. Confirm the paper account is observation-first:
   - `1` contract max

## Do Not Promote Yet

- Tier 2 cooldown-only
- Tier 2A ROC-enhanced cooldown
- Tier 3 max-hold + ROC

These were invalidated by the corrected-cost exact rerun:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## Monitoring

1. Export the trade log after the session.
2. Build the monitoring snapshot.
3. Run the paper-session health assessor.

CLI tools:
- `tradebot-mt5-monitoring-snapshot`
- `tradebot-mt5-paper-health`
- `tradebot-mt5-verify-handoff`

## Monday Mindset

- Tier 1 only
- spreads under control
- no scale-up
- treat any upgrade as blocked until revalidated under corrected costs
