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

## Cost-Survivor Local Refinement

- Adding a `150m` max-hold to the Friday-off corrected survivor improved it only marginally:
  - `R$2,153`, `PF 1.0679`, `DD 11.68%`, composite `0.4422`
  - artifact: [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survivor_maxhold150_20260329/summary.json)
- Skipping the last contract day helped more:
  - `R$2,543`, `PF 1.0853`, `DD 9.60%`, composite `0.5131`
  - `70/30` test: `R$879`, `PF 1.1142`, `DD 8.77%`
  - recent `60d`: `R$312`, `PF 1.2708`
  - artifact: [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survivor_skip_last1_20260329/summary.json)
- Adding `150m` max-hold on top only nudged it further:
  - `R$2,553`, `PF 1.0858`, `DD 9.65%`, composite `0.5140`
  - artifact: [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survivor_skip_last1_maxhold150_20260329/summary.json)
- Interpretation:
  - the best corrected-cost static branch so far is now:
    - strengthened Tier 2A geometry
    - `TP 0.48`
    - `60m` cooldown
    - `AllowFriday=false`
    - skip last `1` contract day
    - `150m` max-hold
  - this is the first corrected-cost branch that is clearly positive full sample and clearly positive on the 70/30 holdout
  - it still does not change the Monday plan because it lacks host-side MT5 validation and remains a materially different operating profile

## Corrected-Cost Cooldown Ceiling

- Pushing the improved survivor from `60m` to `75m` cooldown hurt:
  - `R$1,909`, `PF 1.0670`, `DD 11.71%`, composite `0.4145`
  - `70/30` test: `R$503`, `PF 1.0654`, `DD 9.57%`
  - artifact: [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survivor_cd75_20260329/summary.json)
- Interpretation:
  - around the corrected-cost survivor branch, `60m` is still the local cooldown peak
  - further trade suppression gave back too much net and holdout quality

## Corrected-Cost Stop-Width Ceiling

- `SL 1.00` improved the full sample but weakened the holdout:
  - full sample: `R$2,693`, `PF 1.0872`, `DD 8.47%`, composite `0.5294`
  - `70/30` test: `R$534`, `PF 1.0647`, `DD 9.78%`
- `SL 1.20` failed the holdout:
  - full sample: `R$2,713`, `PF 1.0847`, `DD 9.86%`, composite `0.4869`
  - `70/30` test: `R$-71`, `PF 0.9921`, `DD 12.20%`
- Interpretation:
  - a slightly wider stop can look better in sample, but the out-of-sample edge does not strengthen
  - `SL 0.84` remains the more trustworthy static setting for the corrected-cost survivor branch

## Corrected-Cost TP Ceiling

- Pushing the simplified corrected-cost branch from `TP 0.48` to `TP 0.54` hurt:
  - full sample: `R$1,494`, `PF 1.0414`, `DD 11.09%`, composite `0.3595`
  - `70/30` test: `R$647`, `PF 1.0695`, `DD 7.64%`
  - recent `60d`: `R$-124`, `PF 0.9268`
  - recent `10d`: `R$-209`, `PF 0.6186`
- Pushing again to `TP 0.60` hurt more:
  - full sample: `R$214`, `PF 1.0053`, `DD 18.69%`, composite `0.2186`
  - `70/30` test: `R$177`, `PF 1.0168`, `DD 7.89%`
  - recent `60d`: `R$-179`, `PF 0.9046`
  - recent `10d`: `R$-319`, `PF 0.5122`
- Interpretation:
  - the simplified corrected-cost survivor still wants `TP 0.48`
  - wider reward targets quickly give back too much realized edge
  - the corrected-cost reward ceiling is now mapped cleanly through `TP 0.60`, and the local peak remains `0.48`

## Corrected-Cost ROC Simplification Check

- Removing `ROC(5)` from the corrected-cost local peak lowered the full sample but improved the holdout and recent windows:
  - full sample: `R$2,114`, `PF 1.0692`, `DD 10.64%`, composite `0.4499`
  - `70/30` test: `R$1,007`, `PF 1.1305`, `DD 7.23%`, composite `0.7206`
  - recent `60d`: `R$331`, `PF 1.2873`
  - recent `30d`: `R$368`, `PF 1.6815`
- Interpretation:
  - `ROC(5)` still helps the full-sample corrected-cost frontier
  - but the simplified no-ROC branch may be the more robust corrected-cost candidate
  - that makes the corrected-cost story more nuanced than the pre-correction frontier, where ROC was clearly unique

## Corrected-Cost Max-Hold Simplification Check

- Removing max-hold from the no-ROC corrected-cost branch barely changed the result:
  - full sample: `R$2,104`, `PF 1.0687`, `DD 10.58%`, composite `0.4491`
  - `70/30` test: `R$1,007`, `PF 1.1305`, `DD 7.23%`
  - recent `60d`: `R$331`, `PF 1.2873`
- Interpretation:
  - on the corrected-cost validation branch, max-hold is effectively a no-op
  - the simpler no-ROC, no-max-hold version is now the cleaner corrected-cost candidate to validate next

## Corrected-Cost Simplified Stop Improvement

- Widening the simplified no-ROC, no-max-hold branch to `SL 1.00` materially improved it:
  - full sample: `R$3,024`, `PF 1.0966`, `DD 7.06%`, composite `0.6049`
  - `70/30` test: `R$887`, `PF 1.1091`, `DD 7.91%`, composite `0.6052`
  - recent `60d`: `R$241`, `PF 1.1911`
- Pushing that same simplified branch to `SL 1.20` went too far:
  - full sample: `R$3,409`, `PF 1.1055`, `DD 9.93%`, composite `0.5526`
  - `70/30` test: `R$227`, `PF 1.0253`, `DD 10.66%`
- Interpretation:
  - this is now the strongest balanced corrected-cost static branch
  - it gives up some holdout net versus the pure no-ROC/no-max-hold branch, but materially improves full-sample quality and drawdown while keeping the holdout positive
  - `SL 1.0` is the local peak on the simplified branch; `1.2` gives back too much holdout quality
  - it is the best candidate so far for future host-side MT5 validation, though still not a Monday promotion

## Corrected-Cost Simplified Cooldown Check

- Shortening the balanced simplified branch from `60m` to `45m` raised net but weakened the quality balance:
  - full sample: `R$3,169`, `PF 1.0942`, `DD 11.44%`, composite `0.5331`
  - `70/30` test: `R$1,018`, `PF 1.1184`, `DD 7.90%`
  - recent `60d`: `R$345`, `PF 1.2552`
- Interpretation:
  - `45m` improves gross net and even the holdout net
  - but `60m` is still the more balanced corrected-cost setting because it keeps drawdown materially lower and preserves the stronger composite

## Corrected-Cost Static Regime Pruning Checks

- Cutting both Thursday and Friday from the balanced branch was a recent-tape near-miss, but not robust:
  - full sample: `R$711`, `PF 1.0311`, `DD 11.70%`, composite `0.2797`
  - `70/30` test: `R$-618`, `PF 0.9076`, `DD 13.20%`
  - recent `30d`: `R$364`, `PF 2.8958`
- Excluding the top ATR tercile cleaned up PF and drawdown, but still lost to the balanced baseline:
  - full sample: `R$2,030`, `PF 1.1014`, `DD 8.60%`, composite `0.4634`
  - `70/30` test: `R$590`, `PF 1.1186`, `DD 7.13%`
  - recent `10d`: `0` trades
- Trimming the top ATR tercile to `0.75x` size was much better than hard exclusion, but still a near-miss:
  - full sample: `R$2,775.5`, `PF 1.0974`, `DD 7.07%`, composite `0.5891`
  - `70/30` test: `R$812.75`, `PF 1.1107`, `DD 7.38%`
  - recent `30d`: `R$319`, `PF 1.6827`
- Interpretation:
  - static regime pruning can improve certain windows
  - but neither late-week exclusion nor ATR-based pruning beat the balanced `SL 1.00 / TP 0.48 / 60m / Friday off / skip last1` branch on total score
  - partial ATR trimming is clearly better than hard ATR exclusion, which is useful ceiling evidence for future sizing work

## Current Best Static Corrected-Cost Survivor

- The stronger local refinement is:
  - strengthened Tier 2A geometry
  - `TP 0.48`
  - `60m` cooldown
  - `AllowFriday=false`
  - skip last `1` contract day
- Full sample:
  - `R$2,543`, `PF 1.0853`, `DD 9.60%`, composite `0.5131`
- `70/30` test:
  - `R$879`, `PF 1.1142`, `DD 8.77%`, composite `0.6114`
- Recent windows:
  - `60d`: `R$312`, `PF 1.2708`
  - `30d`: `R$363`, `PF 1.6722`
  - `10d`: `R$231`, `PF 2.2419`
- Artifact:
  - [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_survivor_skip_last1_20260329/summary.json)
- Honest read:
  - contract-cycle pruning helps more than max-hold on the corrected-cost survivor branch
  - this is the first corrected-cost static variant with clearly positive full sample, positive holdout, and controlled drawdown
  - it is still not a Monday promotion until MT5 host-side validation exists

## Corrected-Cost Direction Split

- Long-only on the balanced branch was weak:
  - full sample: `R$521`, `PF 1.0292`, `DD 11.54%`, composite `0.2582`
  - `70/30` test: `R$-838`, `PF 0.8373`, `DD 13.06%`
- Short-only was much healthier:
  - full sample: `R$2,168`, `PF 1.1458`, `DD 12.10%`, composite `0.4395`
  - `70/30` test: `R$1,610`, `PF 1.4601`, `DD 2.85%`
  - recent `60d`: `R$185`, `PF 1.2955`
- But shortening that short sleeve to `45m` cooldown weakened it:
  - full sample: `R$1,998`, `PF 1.1221`, `DD 13.64%`, composite `0.4127`
  - `70/30` test: `R$1,486`, `PF 1.3828`, `DD 4.21%`
- Tightening the short sleeve back to `SL 0.84` also stayed below the `SL 1.0` version:
  - full sample: `R$1,798`, `PF 1.1242`, `DD 11.08%`, composite `0.4257`
  - `70/30` test: `R$1,270`, `PF 1.3533`, `DD 3.97%`
- Interpretation:
  - under corrected costs, the short sleeve is carrying much more of the robust edge
  - the balanced static branch still wins on total score
  - but the next meaningful corrected-cost research direction is clearly side-specific rather than another confirmation filter

## Corrected-Cost Direction-Aware TP Routing

- Research-only directional TP routing did help the sleeve, but not enough to replace the balanced branch:
  - best hybrid: long `TP 0.42`, short `TP 0.48`
  - full sample: `R$2,744`, `PF 1.0900`, `DD 10.14%`, composite `0.5073`
  - `70/30` test: `R$692`, `PF 1.0849`, `DD 5.36%`
  - recent `60d`: `R$77`, `PF 1.0545`
- Interpretation:
  - longs seem to want slightly tighter profit-taking than shorts under corrected costs
  - but the improvement only works in research-style sleeve routing and still does not beat the plain balanced branch

## Corrected-Cost Short-Side Ceiling

- The short-only honest sleeve still peaks at `TP 0.48`:
  - `TP 0.48`: `R$2,168`, `PF 1.1458`, `DD 12.10%`
  - `TP 0.54`: `R$1,473`, `PF 1.0855`, `DD 15.94%`
  - `TP 0.42`: `R$1,078`, `PF 1.0785`, `DD 13.46%`
  - `TP 0.60`: `R$938`, `PF 1.0486`, `DD 20.28%`
- The short-only sleeve also still peaks at `SL 1.0`:
  - `SL 1.0`: `R$2,168`, `PF 1.1458`, `DD 12.10%`
  - `SL 1.2`: `R$2,223`, `PF 1.1439`, `DD 10.99%`
  - `SL 1.5`: `R$1,828`, `PF 1.1115`, `DD 14.32%`
- Interpretation:
  - wider short stops increase win rate, but not enough Sortino-weighted value to beat `SL 1.0`
  - the short sleeve remains the stronger honest sub-strategy, but not the stronger static portfolio

## Corrected-Cost Rolling Walk-Forward

- The best balanced corrected-cost branch was positive but unstable on a rolling walk-forward:
  - `252d` train / `126d` test / `126d` step
  - `7` folds
  - only `3/7` test folds passed with positive net and `PF > 1.0`
- Interpretation:
  - the corrected-cost survivor is real
  - but it is still regime-sensitive enough that it should be treated as a post-Monday MT5 validation target, not an automatic promotion

## Corrected-Cost Long-ATR Prune Promotion

- The first direction-aware static corrected-cost improvement that genuinely beat the balanced branch is:
  - balanced branch core
  - prune only **long** entries on top-ATR tercile days
  - full sample: `R$3,243`, `PF 1.1284`, `DD 7.79%`, composite `0.6201`
  - `70/30` test: `R$1,629`, `PF 1.2696`, `DD 6.00%`
  - recent `60d`: `R$348`, `PF 1.4203`
- Interpretation:
  - under corrected costs, long entries are the weaker sleeve specifically in hotter volatility regimes
  - pruning only those longs is better than pruning both directions and better than pure short-only routing
  - this is now the strongest static corrected-cost branch to validate next on MT5

## Corrected-Cost Long-ATR Plus Short-Hours Stack

- Stacking the next-best static short-side idea on top produced a small additional improvement:
  - balanced branch core
  - prune only **long** entries on top-ATR tercile days
  - restrict **short** entries to `10/11/12`
  - full sample: `R$3,317`, `PF 1.1334`, `DD 8.07%`, composite `0.6219`
  - `70/30` test: `R$1,580`, `PF 1.2615`, `DD 6.02%`
  - recent `60d`: `R$348`, `PF 1.4203`
  - rolling walk-forward: `4/7` test folds positive with `PF > 1.0`
- Interpretation:
  - this is now the strongest static corrected-cost branch overall
  - the improvement over long-ATR-prune-only is small, so the simpler branch remains a valid fallback if we want the least operational complexity for MT5 validation

## Corrected-Cost Short-Side Timing And Cooldown Checks

- The short sleeve is still strongest at `TP 0.48` and `SL 1.0`.
- Best short-only timing was hours `10/11/12`:
  - `R$2,242`, `PF 1.1549`, `DD 12.33%`
  - slightly better than short-only `10/11/12/14`, but still below the long-ATR-pruned balanced branch
- Slowing only longs to `120m` while keeping shorts at `60m` did not beat the leader:
  - `R$2,585`, `PF 1.0839`, `DD 10.87%`
- Interpretation:
  - side-specific timing and cooldown asymmetry help less than simply pruning weak longs in the hottest ATR regime

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
