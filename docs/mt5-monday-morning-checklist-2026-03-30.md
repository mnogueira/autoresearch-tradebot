# MT5 Monday Morning Checklist - 2026-03-30

## Before The Open

1. Log into the paper-trading terminal/account you will actually use on Monday.
2. Open the main MetaTrader 5 terminal and let it sync for at least `2` minutes.
3. Open MetaEditor and compile:
   - `mt5/experts/custom/WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
4. Confirm the compile finished without errors or warnings that affect trading logic.
5. Open Strategy Tester and set:
   - Expert: `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
   - Symbol: the terminal’s continuous WDO symbol
   - Timeframe: `M1`
   - Model: `Every Tick`

## Exact Paths

1. MT5 main terminal:
   - `C:\Program Files\MetaTrader 5 Terminal\terminal64.exe`
2. EA source to compile:
   - `C:\Dev\autoresearch-tradebot\mt5\experts\custom\WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
3. Safest validated preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`
4. Moderate exact refinement preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m GPT 5.4.set`
5. Walk-forward-validated cooldown fallback preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
6. Aggressive exact refinement preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m GPT 5.4.set`
7. Regime-aware ROC research preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m ROC5 TrendSwitch ADX25 GPT 5.4.set`
8. Advanced regime-aware ROC + max-hold research preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m ROC5 TrendSwitch ADX25 GPT 5.4.set`
9. Quality-biased preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
10. Optional trend-day quality preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`
11. Optional live spread-guard preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m SpreadGuard1t GPT 5.4.set`

## Preset Order

1. Run the safest validated preset first:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`
2. If that report looks sane, validate the new cooldown-sweep winner next:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m GPT 5.4.set`
3. If the desk wants the more validated cooldown setting first, use this instead:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
4. If that also looks sane, validate the aggressive max-hold refinement next:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m GPT 5.4.set`
5. If the desk wants the strongest regime-aware research follow-up before max-hold logic, validate:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m ROC5 TrendSwitch ADX25 GPT 5.4.set`
6. If the desk wants the strongest advanced regime-aware stack after that, validate:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m ROC5 TrendSwitch ADX25 GPT 5.4.set`
7. If the desk prefers the cleaner operator profile, validate the quality preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
8. If the desk wants the EA itself to stand down in weaker daily regimes, validate the optional ADX-gated preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`

## Sanity Checks

1. Verify the loaded preset values in the tester:
   - `EntryStart 10:00`
   - `LastEntry 14:30`
   - `MinMinutesBetweenEntries 25` for the new cooldown-sweep winner and the new max-hold refinement, or `30` for the older validated cooldown fallback
   - `MaxMinutesInTrade 150` for the aggressive refinement preset
   - `SL 0.84`
   - `TP 0.30`
   - if using the regime-aware ROC preset, confirm:
     - `UseROCAgreementFilter=true`
     - `UseROCAgreementOnlyOnTrendDays=true`
     - `ROCAgreementBars=5`
     - `UsePriorDayADXFilter=false`
     - `MinPriorDayADX=25`
   - if using the advanced regime-aware max-hold preset, confirm the same ROC-on-trend values plus:
     - `MaxMinutesInTrade=150`
   - if using the trend-day preset, confirm `UsePriorDayADXFilter=true`, `PriorDayADXPeriod=14`, `MinPriorDayADX=25`
2. Confirm the spread is realistic for the current session.
   - The historical exact tape was effectively a `0-1` tick spread world, so repeated live spreads above `1` tick are a real warning sign, not noise.
   - Hard rule for Monday: do **not** trade when spread is above `2` ticks.
   - Operational interpretation:
     - `0-1` tick is the safe zone
     - `2` ticks is already degraded but still historically survivable
     - `3+` ticks turned the main exact tiers negative
3. Run one clean backtest before turning on any paper automation.
4. Save the HTML report and compare the headline numbers against the artifact summary.
5. If the tester output looks sane, move to the paper chart:
   - open the live paper symbol chart
   - attach the EA
   - load the same preset
   - verify `Algo Trading` is enabled
   - confirm the smile icon / active EA state on the chart

## Paper Trading Go / No-Go

- Go only if:
  - the MT5 report is directionally consistent with the saved artifact
  - spreads are not dramatically worse than the baseline assumption
  - entry hours match the intended session windows
  - the desk is treating Monday as a paper-validation session, not a scale-up day

- Stop and investigate if:
  - MT5 fails to produce a report
  - `Every tick based on real ticks` is selected by mistake
  - spread behavior looks closer to the exact `3x` stress case
  - live spread is repeatedly above `2` ticks during the core hours
  - the EA opens positions outside the intended `10,11,12,14` session structure

Recent context:
- The exact max-hold leader was still positive over the last `30` trading days, but only marginally: `R$40`, `PF 1.0357`, `DD 4.67%`.
- That is a yellow light, not a red light: keep the first live-paper sessions observational and disciplined.
- The simpler cooldown-only refinement behaved identically in that same weak tape:
  - `R$40`, `PF 1.0357`, `DD 4.67%`
  - practical takeaway: keep the cooldown-only preset as the first exact refinement to validate before adding the max-hold timer
- The latest cooldown sweep found a slightly better full-sample setting at `25` minutes:
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
  - use that as the first new exact candidate after Tier 1, while keeping the older `30m` line as the safer fallback because it already passed the exact `70/30` walk-forward
- The latest max-hold sweep found a tiny but real improvement at `150` M1 bars:
  - `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340`
  - fixed-parameter `70/30` walk-forward still passed:
    - train `R$11,245`, `PF 1.5236`, `DD 3.28%`
    - test `R$3,175`, `PF 1.3662`, `DD 4.29%`
- The regime readout says trend days are the quality engine:
  - trend-day production slice: `PF 1.9183`, `DD 3.38%`
  - range-day production slice: `PF 1.3153`, `DD 4.95%`
- The second half of 2025 was also weaker than the first half, and it coincided with a much lower share of prior-day `ADX > 25` days.
- Rollover context matters too:
  - first `3` contract days were historically strong at `PF 1.7455`, `DD 3.83%`
  - last `3` contract days were historically weaker at `PF 1.2614`, `DD 6.50%`
  - a full-sample stand-down rule for those last `3` days improved PF to `1.5281`, but still gave up too much net and did not improve drawdown enough to become the default preset
  - because Monday is `2026-03-30`, treat it as a month-end / rollover-tail validation session and stay conservative on interpretation
  - practical rule: keep size small and be willing to skip the session if spread or trend quality looks poor

## Live Monitoring

1. Keep size at `1` contract.
   - stress-budgeted rule of thumb: do not exceed `1` contract per `R$100k` of paper capital on Monday
2. Watch the first two sessions closely around `10:00`, `11:00`, `12:00`, and `14:00`.
3. Record actual spread and fill behavior for each trade.
   - baseline expectation for Tier 1 is about `1.96` trades per day from the validated MT5 report
   - if you later promote to Tier 2, the exact-engine expectation is about `1.30` trades per day
   - if you later promote to Tier 2A with `ROC(5)` agreement, the exact-engine expectation is about `1.28` trades per day
   - if you later promote to Tier 3, the exact-engine expectation is about `1.30` trades per day
4. Keep the `Experts` and `Journal` tabs open and watch for:
   - unexpected entries outside the intended windows
   - repeated close-order rejections
   - spread spikes around the allowed sessions
   - if you want the EA itself to refuse wide-spread entries, load the optional SpreadGuard `1t` preset after the baseline sanity run
5. If live-paper performance diverges sharply from the exact baseline, fall back to the fully validated MT5 base preset.
6. After the tester run or the paper session, export the trade log and daily PnL CSV:
   - script: `src/autoresearch_tradebot/mt5/export_tester_trade_log.py`
   - tested Tier 1 example:
     - `python -m autoresearch_tradebot.mt5.export_tester_trade_log --report artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/mt5_model_0_report.html --trades-out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/trade_log.csv --daily-out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/daily_pnl.csv`
7. Build the compact monitoring JSON after the export:
   - script: `src/autoresearch_tradebot/mt5/build_monitoring_snapshot.py`
   - installed CLI entry point after `pip install -e .`:
     - `tradebot-mt5-monitoring-snapshot --trade-log artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/trade_log.csv --session-date 2026-03-19 --out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json`
   - tested Tier 1 example:
     - `python -m autoresearch_tradebot.mt5.build_monitoring_snapshot --report artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/mt5_model_0_report.html --out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json`
   - reusable trade-log workflow:
     - `python -m autoresearch_tradebot.mt5.build_monitoring_snapshot --trade-log artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/trade_log.csv --session-date 2026-03-19 --out artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/monitoring_snapshot.json`
   - the current tested snapshot fields are:
     - daily PnL
     - rolling `5d/20d/60d` profit factor
     - rolling `30d` profit factor
     - current and max drawdown
     - historical drawdown distribution (`p50/p90/p95/max`)
     - expected trades per day
   - dashboard concept reference:
     - `docs/stalker-v10-1-strategy-health-dashboard-2026-03-28.md`
8. Start the paper-week worksheet before the first live session:
   - `docs/mt5-week-1-monitoring-template-2026-03-28.md`
9. After each session, assess the paper-session health from the monitoring snapshot:
   - `python -m autoresearch_tradebot.mt5.assess_paper_session --snapshot <monitoring_snapshot.json> --max-spread-ticks <observed_max> --completed-sessions <count> --current-tier "Tier 1"`
   - installed CLI: `tradebot-mt5-paper-health`
10. Do not try to improve fills by intentionally waiting one extra minute after the signal.
   - the next-open patience and one-tick-better next-open entry overlays were both strongly negative in research
