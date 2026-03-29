# Research Frontier - 2026-03-28

## Critical Frontier Reset

The frontier changed materially after fixing:

- missing flat round-trip cost
- ROC lookahead
- ATR timing leakage
- session-boundary cooldown behavior

Corrected rerun:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## New Honest State

- Tier 1 validated MT5 base remains the only Monday-ready production anchor.
- The Python exact upgrade ladder does **not** survive conservative retail WDO costs as currently implemented.
- Best corrected exact line was Tier 2A, and it was still negative:
  - `R$-2,951`, `PF 0.9147`, `DD 46.08%`

## First Cost Survivor

- The first corrected-cost robust survivor has now appeared:
  - strengthened Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
  - `AllowFriday=false`
  - full sample: `R$2,143`, `PF 1.0674`, `DD 11.61%`, composite `0.4414`
  - `70/30` test: `R$623`, `PF 1.0754`, `DD 9.53%`, composite `0.4718`
  - recent `60d`: `R$312`, `PF 1.2708`, `DD 2.55%`
  - recent `30d`: `R$363`, `PF 1.6722`, `DD 1.18%`
- Artifact:
  - [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survival_followups_20260329/summary.json)
- Honest read:
  - wider targets and fewer trades can rescue the edge under corrected costs
  - but this is still not a Monday promotion because it has not had host-side MT5 validation and materially changes the operating profile

## What Survived Conceptually

- `ROC(5)` still appears to be the only lightweight agreement family with repeatable incremental value inside the old pre-correction research space.
- Execution quality and sizing still look like the main remaining upside.
- Spread discipline is still operationally critical:
  - `2` ticks is the last tolerable integer spread
  - `3+` ticks breaks the main deployable logic

## What The Frontier Is Now

The next frontier is not another tiny filter.

It is:

1. find a static variant that survives corrected costs
2. or prove a host-side MT5 upgrade survives real costs
3. or accept that Tier 1 is the ceiling for now

## First Cost-Surviving Static Variant

- The first static variant to survive the corrected cost model is:
  - Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
- Full sample:
  - `R$2,285`, `PF 1.0545`, `DD 17.15%`, composite `0.4154`
- `70/30` test:
  - `R$-68`, `PF 0.9941`, `DD 15.16%`
- Recent windows:
  - `60d`: `R$259`, `PF 1.1516`
  - `30d`: `R$413`, `PF 1.4870`
  - `10d`: `R$398`, `PF 3.1398`
- Interpretation:
  - wider targets plus materially fewer trades can survive the flat-fee correction
  - but this first survivor is still too weak out of sample to change the Monday plan

## Promising Directions To Test

- fewer trades:
  - longer cooldown
  - harsher session pruning
  - first-quality-signal-only ideas
- wider reward geometry:
  - higher TP variants
  - cost-aware target structures
- genuinely different signal families:
  - not another oscillator confirmation
  - not another near-tie trend proxy

## What Is Now Explicitly Superseded For Monday

- Tier 2 as an automatic next promotion
- Tier 2A as an automatic next promotion
- Tier 3 as an automatic next promotion

Those remain research branches only until they pass corrected-cost validation or host-side MT5 validation.
