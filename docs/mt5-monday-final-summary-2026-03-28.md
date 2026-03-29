# MT5 Monday Final Summary - 2026-03-28

## Bottom Line

- Monday default remains Tier 1: the validated MT5 `Every Tick` base preset.
- Best new exact cooldown-sweep refinement is Tier 2: session winner + `25m` cooldown only.
- Best stronger post-Tier-2 research validation target is now Tier 2A: session winner + `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`.
- The older `30m` cooldown line remains the safer fallback because it already has the exact `70/30` walk-forward pass.
- Tier 3 is now the stronger aggressive branch: session winner + `25m` cooldown + `150m` max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`.
- That Tier 3 line is the strongest exact research score overall, but it still comes after Tier 2A operationally because Tier 2A is the cleaner first upgrade.

## What We Learned

- The current deployable signal family is probably near its ceiling on this data.
- No live-ready exact variant beat the current exact leader by a meaningful margin on the Sortino-weighted composite.
- The only higher composite scores came from research-only overlays:
  - ATR-regime sizing on strengthened Tier 2A
  - confidence-weighted sizing
  - confidence-weighted sizing + time-widened stop
  - weighted advanced research-only sleeve blends

## Current Ranking

| Tier | Variant | Why |
| --- | --- | --- |
| Tier 1 | MT5 validated base preset | Safest Monday choice because it is already validated in MT5 `Every Tick`. |
| Tier 2 | Session winner + `25m` cooldown | Best deployable exact composite in the cooldown sweep. |
| Tier 2A | Session winner + `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2` | Strongest simpler exact post-Monday upgrade and best out-of-sample post-Monday line. |
| Tier 3 | Session winner + `25m` cooldown + `150m` max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2` | Strongest aggressive exact research line, but still a later rollout step than Tier 2A. |
| Tier 4 | Research-only advanced sleeves and sizing overlays | Highest raw ceiling comes from ATR-regime sizing and advanced directional sleeves, but neither is Monday-deployable as a static preset. |

## Recent Tape

- Last `30` trading days were soft:
  - `R$40`, `PF 1.0357`, `DD 4.67%`
- Last `10` trading days recovered sharply:
  - `R$455`, `PF 4.25`, `DD 0.81%`
- Last `5` trading days were also solid:
  - `R$110`, `PF 1.7857`, `DD 0.84%`
- Interpretation:
  - the edge did soften in the recent range-bound tape
  - but the latest `10` days and latest `5` days do not look broken
  - Monday should still be treated as cautious paper validation, not scale-up

## Main Risks

- Transaction-cost sensitivity remains the number-one risk.
- Exact spread break-even for the main deployable tiers is `2` ticks. Do not trade when spread is above `2` ticks.
- Range-bound, low-ADX tape remains the main underperformance regime.
- The last `3` contract days before rollover are structurally weaker.
- A true fixed `5`-tick spread tape is fatal to the edge.
- MT5 tester stability is still imperfect, so live paper monitoring matters more than backtest polish now.

## What Not To Chase On Monday

- Do not switch to the research-only confidence overlays yet.
- Do not hard-skip Tuesday/Friday by default.
- Do not promote ATR trailing, dynamic `TP 1.0 ATR`, ML gates, or ML overlays.

## Best Next Upgrade Path

1. Run Tier 1 for the first paper week.
2. If the first `5` paper sessions are clean, move to Tier 2.
3. If Tier 2 behaves cleanly, validate Tier 2A next.
4. Only after that, test Tier 3.
5. Keep Tier 4 as a research-only blend, not a live preset.
6. Keep the ADX gate and rollover caution as operator context, not default hard filters.
