# MT5 Corrected-Cost Conclusion - 2026-03-29

## Executive Call

- Monday should still run Tier 1 only.
- The old Python Tier 2 / Tier 2A / Tier 3 ladder was not trustworthy after realistic retail WDO costs were restored.
- The corrected-cost frontier now has a real survivor, but it is still research-only until host-side MT5 validation exists.

## Best Honest Corrected-Cost Branch

Configuration:

- strengthened Tier 2A geometry
- no ROC
- no max-hold
- `SL 1.0`
- `TP 0.48`
- `60m` cooldown
- Friday off
- skip the last contract day
- prune only **long** entries on top-ATR tercile days

Metrics:

- full sample: `R$3,243`
- `PF 1.1284`
- `DD 7.79%`
- composite `0.6201`
- `70/30` test: `R$1,629`, `PF 1.2696`, `DD 6.00%`
- recent `60d`: `R$348`, `PF 1.4203`

## Honest Interpretation

- This is now the strongest static corrected-cost branch I have.
- It is the best static corrected-cost candidate to validate next.
- It is still **not** a Monday promotion, because it has no host-side MT5 confirmation yet.

## Latest Frontier Checks

- Direction-aware TP routing helped only as a research sleeve, not as a new static leader:
  - best hybrid was `long TP 0.42 / short TP 0.48`
  - full sample `R$2,744`, `PF 1.0900`, `DD 10.14%`
  - `70/30` test `R$692`, `PF 1.0849`, `DD 5.36%`
  - useful ceiling evidence, but still below the plain balanced corrected-cost branch
- The short sleeve is still the healthier honest sub-strategy:
  - full sample `R$2,168`, `PF 1.1458`, `DD 12.10%`
  - `70/30` test `R$1,610`, `PF 1.4601`, `DD 2.85%`
  - recent `60d` `R$185`, `PF 1.2955`
- But the short sleeve still wants the same core geometry:
  - `TP 0.48` beat `0.42`, `0.54`, and `0.60`
  - `SL 1.0` beat `1.2` and `1.5`
- Rolling walk-forward on the best static corrected-cost branch was mixed:
  - `7` folds of `252d` train / `126d` test
  - `3/7` test folds positive with `PF > 1.0`
  - honest read: viable, but regime-sensitive and not yet stable enough for automatic promotion

## What Did Not Beat It

- keeping ROC on the corrected-cost branch
- keeping max-hold on the simplified branch
- shortening cooldown to `45m`
- widening TP to `0.54` or `0.60`
- widening SL to `1.2`
- widening short-only SL to `1.2` or `1.5`
- re-enabling Friday
- cutting `Thu/Fri` entirely
- hard ATR exclusion
- partial ATR trim to `0.75x` on top ATR days
- directional asymmetry did matter, but not enough to replace the balanced branch:
  - long-only failed on holdout
  - short-only was much healthier and is the stronger corrected-cost sleeve
  - tighter long TP plus wider short TP improved the research sleeve, but still not enough to replace the balanced branch
- slowing only longs to `120m` cooldown did not beat the new long-ATR-pruned branch
- short-only hours `10/11/12` were the best short sleeve timing, but still not enough to replace the new long-ATR-pruned branch

## Monday Plan

1. Trade Tier 1 only.
2. Enforce the spread rule:
   - prefer `0-1` tick
   - `2` ticks max
   - above `2` ticks: stand down
3. Use the long-ATR-pruned corrected-cost branch as the next host-side MT5 validation target after Monday, not as Monday default.
4. That target is:
   - balanced branch core
   - prune long entries on top-ATR tercile days

## Next Research Direction

- Stop looking for another small filter.
- The remaining upside is in:
  - host-side MT5 validation of the balanced branch
  - better execution
  - variable sizing overlays
  - side-specific routing, where the short sleeve currently looks stronger than the long sleeve
