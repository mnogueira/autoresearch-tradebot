# MT5 Monday Final Summary - 2026-03-28

## Bottom Line

- Monday default remains Tier 1: the validated MT5 `Every Tick` base preset.
- Best exact research refinement remains Tier 2: session winner + `30m` cooldown only.
- Tier 3, the max-hold variant, is still strong, but the operational upside versus Tier 2 is tiny.

## What We Learned

- The current deployable signal family is probably near its ceiling on this data.
- No live-ready exact variant beat the current exact leader by a meaningful margin on the Sortino-weighted composite.
- The only higher composite scores came from research-only overlays:
  - confidence-weighted sizing
  - confidence-weighted sizing + time-widened stop
  - equal-weight blend of the top two exact strategies

## Current Ranking

| Tier | Variant | Why |
| --- | --- | --- |
| Tier 1 | MT5 validated base preset | Safest Monday choice because it is already validated in MT5 `Every Tick`. |
| Tier 2 | Session winner + `30m` cooldown | Keeps almost all of the exact leader’s quality with less moving logic. |
| Tier 3 | Session winner + `30m` cooldown + `120` M1-bar max hold | Best exact single-strategy composite, but only by a hair. |

## Recent Tape

- Last `30` trading days were soft:
  - `R$40`, `PF 1.0357`, `DD 4.67%`
- Last `10` trading days recovered sharply:
  - `R$455`, `PF 4.25`, `DD 0.81%`
- Interpretation:
  - the edge did soften in the recent range-bound tape
  - but the latest `10` days do not look broken
  - Monday should still be treated as cautious paper validation, not scale-up

## Main Risks

- Transaction-cost sensitivity remains the number-one risk.
- Range-bound, low-ADX tape remains the main underperformance regime.
- The last `3` contract days before rollover are structurally weaker.
- MT5 tester stability is still imperfect, so live paper monitoring matters more than backtest polish now.

## What Not To Chase On Monday

- Do not switch to the research-only confidence overlays yet.
- Do not hard-skip Tuesday/Friday by default.
- Do not promote ATR trailing, dynamic `TP 1.0 ATR`, ML gates, or ML overlays.

## Best Next Upgrade Path

1. Run Tier 1 for the first paper week.
2. If the first `5` paper sessions are clean, move to Tier 2.
3. Only after another clean week, test Tier 3.
4. Keep the ADX gate and rollover caution as operator context, not default hard filters.
