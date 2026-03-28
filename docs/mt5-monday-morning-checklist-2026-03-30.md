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
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
5. Aggressive exact refinement preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
6. Quality-biased preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
7. Optional trend-day quality preset:
   - `C:\Dev\autoresearch-tradebot\mt5\profiles\tester\WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`

## Preset Order

1. Run the safest validated preset first:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`
2. If that report looks sane, validate the simpler exact refinement next:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
3. If that also looks sane, validate the aggressive max-hold refinement next:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
4. If the desk prefers the cleaner operator profile, validate the quality preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
5. If the desk wants the EA itself to stand down in weaker daily regimes, validate the optional ADX-gated preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`

## Sanity Checks

1. Verify the loaded preset values in the tester:
   - `EntryStart 10:00`
   - `LastEntry 14:30`
   - `MinMinutesBetweenEntries 30`
   - `MaxMinutesInTrade 120` for the new refinement presets
   - `SL 0.84`
   - `TP 0.30`
   - if using the trend-day preset, confirm `UsePriorDayADXFilter=true`, `PriorDayADXPeriod=14`, `MinPriorDayADX=25`
2. Confirm the spread is realistic for the current session.
   - The historical exact tape was effectively a `0-1` tick spread world, so repeated live spreads above `1` tick are a real warning sign, not noise.
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
  - the EA opens positions outside the intended `10,11,12,14` session structure

Recent context:
- The exact max-hold leader was still positive over the last `30` trading days, but only marginally: `R$40`, `PF 1.0357`, `DD 4.67%`.
- That is a yellow light, not a red light: keep the first live-paper sessions observational and disciplined.
- The simpler cooldown-only refinement behaved identically in that same weak tape:
  - `R$40`, `PF 1.0357`, `DD 4.67%`
  - practical takeaway: use the simpler cooldown-only preset as the first exact refinement to validate before adding the max-hold timer
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
4. Keep the `Experts` and `Journal` tabs open and watch for:
   - unexpected entries outside the intended windows
   - repeated close-order rejections
   - spread spikes around the allowed sessions
5. If live-paper performance diverges sharply from the exact baseline, fall back to the fully validated MT5 base preset.
