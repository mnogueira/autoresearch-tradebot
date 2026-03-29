# Stalker v10.1 What Worked And What Didn't - 2026-03-28

## Critical Correction

After fixing costs and lookahead, the old Python production ladder no longer holds for deployment.

Corrected rerun:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## What Still Worked

- Tier 1 validated MT5 base:
  - still the only Monday-ready configuration
- Spread guardrail:
  - still essential
  - `>2` ticks remains a no-trade condition
- `ROC(5)` as a research signal:
  - still the uniquely useful lightweight agreement family in the old frontier
  - but after the cost correction, the best holdout survivor no longer clearly requires it
- Research-only sizing overlays:
  - still the strongest remaining upside
  - especially ATR-based de-risking on hot-volatility days
- Wider TP plus fewer trades:
  - the corrected-cost survivor branch is:
    - strengthened Tier 2A geometry
    - `TP 0.48`
    - `60m` cooldown
    - `AllowFriday=false`
  - the best local refinement is:
    - skip last `1` contract day
    - `150m` max-hold
    - `R$2,553`, `PF 1.0858`, `DD 9.65%`
  - the best holdout refinement is now the simpler no-ROC branch:
    - `R$2,104`, `PF 1.0687`, `DD 10.58%`
    - `70/30` test `R$1,007`, `PF 1.1305`, `DD 7.23%`
    - removing max-hold did not change the out-of-sample readout
  - the best balanced refinement so far is:
    - no ROC
    - no max-hold
    - `SL 1.0`
    - `R$3,024`, `PF 1.0966`, `DD 7.06%`
    - `70/30` test `R$887`, `PF 1.1091`, `DD 7.91%`
  - it also stayed positive on the holdout:
    - `70/30` test `R$879`, `PF 1.1142`, `DD 8.77%`
  - and on the recent windows:
    - recent `60d` `R$312`, `PF 1.2708`
    - recent `30d` `R$363`, `PF 1.6722`
  - so it is now the first real corrected-cost research survivor, though still not a Monday promotion
- Corrected-cost static survival:
  - Tier 2A geometry with `TP 0.48` and `60m` cooldown is the first positive full-sample survivor
  - that means fewer trades plus wider targets are the first credible path through realistic costs

## What Did Not Hold Up

- Tier 2 under corrected costs:
  - negative
- Tier 2A under corrected costs:
  - negative
- Tier 3 under corrected costs:
  - negative
- automatic promotion path beyond Tier 1:
  - no longer justified for Monday
- over-throttling the corrected-cost survivor:
  - pushing the improved branch to `75m` cooldown hurt both full-sample net and holdout quality
- overly wide stops on the corrected-cost survivor:
  - `SL 1.0` looked better in sample but had a weaker holdout
  - `SL 1.2` failed the holdout outright
- but on the simplified corrected-cost branch:
  - `SL 1.0` is actually the best balanced result so far
  - `SL 1.2` gives back too much holdout quality
  - so stop-width interacts with branch complexity
- shortening the simplified corrected-cost cooldown to `45m`:
  - raised full-sample and holdout net
  - but gave back too much drawdown, so `60m` stays the balanced setting
- cutting the balanced branch to `Mon/Tue/Wed` only:
  - looked great in the recent tape
  - but failed the holdout badly, so it is not robust
- excluding the top ATR tercile on the balanced branch:
  - improved PF and drawdown
  - but over-pruned enough to lose the total score and even produced `0` trades in the recent `10d`
- trimming top-ATR days to `0.75x` on the balanced branch:
  - came much closer than hard exclusion
  - but still stayed just below the plain balanced branch, so it remains research-only sizing upside
- splitting the balanced branch by direction:
  - long-only failed badly on holdout
  - short-only held up much better and is clearly the stronger corrected-cost sleeve
  - but the combined balanced branch still wins as the cleaner static default
  - even on the stronger short sleeve, shortening cooldown to `45m` made the branch worse again
  - and tightening that short sleeve back to `SL 0.84` still did not beat the `SL 1.0` short branch
  - widening the short-only stop to `1.2` or `1.5` also failed to beat the `SL 1.0` short branch
  - widening the short-only target to `0.54` or `0.60` also failed; the short sleeve still wants `TP 0.48`
  - a research-only long/short TP split did help slightly (`long TP 0.42`, `short TP 0.48`), but still did not beat the balanced branch
  - the first side-specific static branch that really did beat the balanced branch was:
    - prune only long entries on top-ATR tercile days
    - `R$3,243`, `PF 1.1284`, `DD 7.79%`
    - `70/30` test `R$1,629`, `PF 1.2696`, `DD 6.00%`
  - best short-only timing was `10/11/12`, but that still did not beat the long-ATR-pruned balanced branch
  - slowing only longs to `120m` while leaving shorts at `60m` also failed to beat it
- overly wide profit targets on the corrected-cost survivor:
  - `TP 0.54` weakened the full sample and flipped the recent `60d` and `10d` windows negative
  - `TP 0.60` was worse again and nearly flatlined the full-sample edge

## What Clearly Did Not Work

- RSI mean reversion
- VWAP mean reversion
- opening-range breakout
- session breakout
- next-bar-open entry timing
- patience filters
- confirmation candle delays
- hard signal-strength gates
- most oscillator confirmations besides ROC
- H1 translation of the same signal family

## Ceiling Read

- The confirmation family is now exhaustively mapped.
- `ROC(5)` is genuinely unique inside that family.
- But even that is not enough, by itself, to survive corrected retail cost assumptions in static exact form.

## Honest Takeaway

- The current signal family may not have enough static edge to clear realistic costs once modeled honestly.
- That means future work should focus on:
  - fewer trades
  - wider reward structures
  - or truly different signal families
- Current best cost-aware lead:
  - strongest static corrected-cost branch:
    - balanced simplified branch with `SL 1.0`, `TP 0.48`, `60m`, Friday off, skip last `1`
    - prune only long entries on top-ATR tercile days
  - strongest corrected-cost directional sleeve:
    - short-only, `SL 1.0`, `TP 0.48`, `60m`, Friday off, skip last `1`
  - promising, but not robust enough yet to promote
