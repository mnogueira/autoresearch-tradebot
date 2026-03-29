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
- Research-only sizing overlays:
  - still the strongest remaining upside
  - especially ATR-based de-risking on hot-volatility days
- Wider TP plus fewer trades:
  - the first corrected-cost robust survivor is:
    - strengthened Tier 2A geometry
    - `TP 0.48`
    - `60m` cooldown
    - `AllowFriday=false`
    - `R$2,143`, `PF 1.0674`, `DD 11.61%`
  - it also stayed positive on the holdout:
    - `70/30` test `R$623`, `PF 1.0754`, `DD 9.53%`
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
  - `TP 0.48` + `60m` cooldown on Tier 2A geometry
  - promising, but not robust enough yet to promote
