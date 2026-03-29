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

Metrics:

- full sample: `R$3,024`
- `PF 1.0966`
- `DD 7.06%`
- composite `0.6049`
- `70/30` test: `R$887`, `PF 1.1091`, `DD 7.91%`
- recent `60d`: `R$241`, `PF 1.1911`

## Honest Interpretation

- This is the first corrected-cost branch that is both positive and reasonably stable.
- It is the best static corrected-cost candidate to validate next.
- It is still **not** a Monday promotion, because it has no host-side MT5 confirmation yet.

## What Did Not Beat It

- keeping ROC on the corrected-cost branch
- keeping max-hold on the simplified branch
- shortening cooldown to `45m`
- widening TP to `0.54` or `0.60`
- widening SL to `1.2`
- re-enabling Friday
- cutting `Thu/Fri` entirely
- hard ATR exclusion
- partial ATR trim to `0.75x` on top ATR days
- directional asymmetry did matter, but not enough to replace the balanced branch:
  - long-only failed on holdout
  - short-only was much healthier and is the stronger corrected-cost sleeve

## Monday Plan

1. Trade Tier 1 only.
2. Enforce the spread rule:
   - prefer `0-1` tick
   - `2` ticks max
   - above `2` ticks: stand down
3. Use the balanced corrected-cost branch as the next host-side MT5 validation target after Monday, not as Monday default.

## Next Research Direction

- Stop looking for another small filter.
- The remaining upside is in:
  - host-side MT5 validation of the balanced branch
  - better execution
  - variable sizing overlays
  - side-specific routing, where the short sleeve currently looks stronger than the long sleeve
