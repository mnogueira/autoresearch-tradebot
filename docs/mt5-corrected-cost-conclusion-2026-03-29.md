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
- restrict **short** entries to `10/11/12`

Metrics:

- full sample: `R$3,317`
- `PF 1.1334`
- `DD 8.07%`
- composite `0.6219`
- `70/30` test: `R$1,580`, `PF 1.2615`, `DD 6.02%`
- recent `60d`: `R$348`, `PF 1.4203`
- recent `30d`: `R$403`, `PF 2.1749`
- recent `10d`: `R$280`, `PF inf`
- rolling walk-forward: `4/7` test folds positive with `PF > 1.0`

## Simpler Fallback

- The simpler fallback remains extremely close:
  - same branch, but without the short-hours restriction
  - full sample `R$3,243`, `PF 1.1284`, `DD 7.79%`, composite `0.6201`
  - `70/30` test `R$1,629`, `PF 1.2696`, `DD 6.00%`
- If we want the least operational complexity for the first host-side MT5 validation, the long-ATR-pruned-only version is still a defensible first target.

## Honest Interpretation

- This is now the strongest static corrected-cost branch I have.
- The improvement over the simpler long-ATR-pruned branch is real but small.
- It is still **not** a Monday promotion, because it has no host-side MT5 confirmation yet.
- The strategy is not dead under honest costs, but the viable branch is much narrower and more conservative than the old frontier.

## What The Corrected-Cost Work Showed

- The balanced corrected-cost branch was the first real survivor:
  - no ROC
  - no max-hold
  - `SL 1.0`
  - `TP 0.48`
  - `60m` cooldown
  - Friday off
  - skip last contract day
  - `R$3,024`, `PF 1.0966`, `DD 7.06%`
- Side-specific routing then improved it:
  - prune only long entries on top-ATR tercile days
  - `R$3,243`, `PF 1.1284`, `DD 7.79%`
  - `70/30` test `R$1,629`, `PF 1.2696`, `DD 6.00%`
- The latest incremental improvement is stacking short-hours `10/11/12` on top:
  - `R$3,317`, `PF 1.1334`, `DD 8.07%`
  - `70/30` test `R$1,580`, `PF 1.2615`, `DD 6.02%`
- Rolling walk-forward on the new leader was constructive but still regime-sensitive:
  - `7` folds of `252d` train / `126d` test
  - `4/7` test folds positive with `PF > 1.0`

## What Did Not Beat It

- keeping ROC on the corrected-cost branch
- keeping max-hold on the simplified branch
- shortening cooldown to `45m`
- slowing only longs to `120m` while keeping shorts at `60m` on top of the new combo:
  - `R$2,907`, `PF 1.1176`, `DD 12.06%`
  - `70/30` test `R$1,270`, `PF 1.2071`, `DD 7.12%`
- widening TP to `0.54` or `0.60`
- widening SL to `1.2`
- re-enabling Friday
- cutting `Thu/Fri` entirely
- hard ATR exclusion
- partial ATR trim to `0.75x` on top ATR days
- slowing only longs to `120m` cooldown
- short-only branch, even though shorts are the stronger honest sleeve
- wider short-only SL (`1.2`, `1.5`)
- wider short-only TP (`0.54`, `0.60`)
- research-only long/short TP routing (`long TP 0.42 / short TP 0.48`)

## Directional Sleeve Readout

- Pure short-only is still the stronger honest sleeve:
  - full sample `R$2,168`, `PF 1.1458`, `DD 12.10%`
  - `70/30` test `R$1,610`, `PF 1.4601`, `DD 2.85%`
  - recent `60d` `R$185`, `PF 1.2955`
  - recent `30d` `R$280`, `PF 2.1814`
- Best short-only timing sleeve is `10/11/12`:
  - full sample `R$2,619`, `PF 1.1750`, `DD 12.33%`
  - rolling walk-forward `3/7` test folds positive with `PF > 1.0`
- Pure long-only is not viable under corrected costs:
  - full sample `R$521`, `PF 1.0292`, `DD 11.54%`
  - `70/30` test `R$-838`, `PF 0.8373`
- Honest read:
  - the short sleeve carries more of the real-cost edge
  - but the best corrected-cost portfolio still comes from keeping both directions and pruning the weaker long sleeve selectively
  - even the best short-only timing sleeve is less robust than the stacked combo

## Monday Plan

1. Trade Tier 1 only.
2. Enforce the spread rule:
   - prefer `0-1` tick
   - `2` ticks max
   - above `2` ticks: stand down
3. Use the stacked side-specific corrected-cost branch as the next host-side MT5 validation target after Monday, not as Monday default.
4. Primary post-Monday target:
   - balanced branch core
   - prune long entries on top-ATR tercile days
   - restrict short entries to `10/11/12`
5. Simpler fallback target:
   - balanced branch core
   - prune long entries on top-ATR tercile days

## Next Research Direction

- Stop looking for another small filter.
- The remaining upside is in:
  - host-side MT5 validation of the corrected-cost static survivor branch
  - better execution
  - variable sizing overlays
  - side-specific routing, because the short sleeve is still stronger than the long sleeve under corrected costs
