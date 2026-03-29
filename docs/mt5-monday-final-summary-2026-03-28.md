# MT5 Monday Final Summary - 2026-03-28

## Final Answer

- Monday stays on Tier 1:
  - the validated MT5 base preset
- The old Python upgrade ladder is superseded.
- After the corrected rerun, Tier 2 / Tier 2A / Tier 3 are no longer trustworthy promotion candidates on their old numbers.

## Why

The corrected rerun fixed four material issues:

1. flat round-trip cost was missing
2. ROC agreement had lookahead
3. ATR sizing used current-bar ATR instead of open-bar ATR
4. cooldown state did not reset cleanly at session boundaries

Corrected rerun artifact:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

Best corrected Python line:
- Tier 2A
- `R$-2,951`, `PF 0.9147`, `DD 46.08%`

That is still negative.

## Operational Message

- Tier 1 validated MT5 base is the only Monday-ready paper-trading configuration.
- Tier 2 / Tier 2A / Tier 3 move back to research-only status until revalidated.
- Spread guardrail remains critical:
  - do not trade above `2` ticks

## Honest Conclusion

- The strategy may not have enough static edge in Python exact form to cover conservative retail WDO costs.
- But the corrected-cost frontier is no longer empty:
  - the best honest static branch is now the balanced simplified survivor
  - strengthened Tier 2A geometry
  - no ROC
  - no max-hold
  - `SL 1.0`
  - `TP 0.48`
  - `60m` cooldown
  - Friday off
  - skip last contract day
- Real metrics for that branch:
  - full sample `R$3,024`, `PF 1.0966`, `DD 7.06%`
  - `70/30` test `R$887`, `PF 1.1091`, `DD 7.91%`
- That makes it the best honest post-Monday validation target, not a Monday promotion.
- Any remaining viable upside is now more likely to come from:
  - host-side MT5 validation of that balanced branch
  - or sizing / execution improvements rather than another small filter
