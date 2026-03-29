# MT5 Monday Executive Summary - 2026-03-28

## Executive Call

- Monday default stays Tier 1:
  - the validated MT5 `Every Tick` base preset
- Do **not** promote the Python Tier 2 / Tier 2A / Tier 3 upgrades on the old frontier numbers.
- Reason:
  - after fixing flat costs, ROC lookahead, ATR timing, and session-cooldown resets, the Python production ladder no longer survives realistic costs.

## Critical Correction

The exact production rerun now uses:

- `ROUND_TRIP_COST_BRL = 11.0`
- lagged ROC agreement, using only prior-bar information
- `get_atr_open()` for SL/TP sizing instead of current-bar ATR
- cooldown reset at session boundaries

Corrected production rerun artifact:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## Corrected Results

| Variant | Full Net | PF | DD | 70/30 Test Net | Test PF | Test DD | Recent 60d Net | Recent 60d PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tier 1 exact analog, corrected | `R$-15,135` | `0.7546` | `149.78%` | `R$-5,174` | `0.6959` | `56.13%` | `R$-1,689` | `0.5354` |
| Tier 2, corrected | `R$-3,910` | `0.8837` | `53.59%` | `R$-2,534` | `0.7455` | `33.06%` | `R$-1,050` | `0.5268` |
| Tier 2A, corrected | `R$-2,951` | `0.9147` | `46.08%` | `R$-2,255` | `0.7800` | `29.02%` | `R$-753` | `0.6346` |
| Tier 3, corrected | `R$-3,142` | `0.9110` | `47.41%` | `R$-2,372` | `0.7731` | `30.13%` | `R$-724` | `0.6487` |

## What Still Holds

- The validated MT5 base report is still the only production-ready Monday anchor:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`
- The recent tape is softer than the old full-sample Python frontier, but not dead:
  - corrected last `10` trading days were still positive across corrected exact variants
  - corrected Tier 2A last `10` days: `R$269`, `PF 2.4462`, `DD 1.33%`

## What Changed

- The prior Python upgrade ladder was materially inflated by missing flat costs.
- The ROC agreement family still looks like the only uniquely helpful lightweight confirmation family.
- But none of the static Python upgrade tiers currently justify promotion for Monday after the corrected rerun.
- The first corrected-cost survivor branch now exists, but it is still not a Monday promotion:
  - strengthened Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
  - `AllowFriday=false`
  - local best refinement also skips the last `1` contract day
  - full sample `R$2,543`, `PF 1.0853`, `DD 9.60%`
  - `70/30` test `R$879`, `PF 1.1142`, `DD 8.77%`

## Corrected-Cost Survivor Frontier

- The first corrected-cost static survivor was:
  - Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
- The local refinement that is currently best is:
  - Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
  - `AllowFriday=false`
  - skip last `1` contract day
- Full sample:
  - `R$2,543`, `PF 1.0853`, `DD 9.60%`
- `70/30` test:
  - `R$879`, `PF 1.1142`, `DD 8.77%`
- Recent windows:
  - recent `60d`: `R$312`, `PF 1.2708`
  - recent `30d`: `R$363`, `PF 1.6722`
  - recent `10d`: `R$231`, `PF 2.2419`
- Read:
  - the edge can survive the corrected flat-cost model, but only after much wider targets and much lower trade frequency
  - skipping the final contract day helps more than adding max-hold
  - it is still research-only until host-side MT5 validation exists

## Monday Recommendation

1. Run Tier 1 only.
2. Enforce the spread rule:
   - do not trade when spread is above `2` ticks
3. Treat Monday as validation-first paper trading, not a scale-up day.
4. Keep Tier 2 / Tier 2A / Tier 3 in research status until one of these happens:
   - a corrected-cost Python variant turns positive and robust
   - or host-side MT5 validation proves a specific upgrade survives real trading frictions

## Main Risks

- Real transaction costs are now the dominant threat to the strategy edge.
- Recent soft regimes still matter:
  - corrected recent `60d` exact reads are negative for the Python upgrades
- MT5 tester instability still means host-side verification matters.

## Next Research Goal

- Stop polishing tiny filters.
- Focus only on variants that can survive realistic costs:
  - fewer trades
  - wider targets
  - materially different signal families
  - better execution assumptions only if they are realistically deployable
