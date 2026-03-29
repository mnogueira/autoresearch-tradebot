# MT5 Next Steps After Monday - 2026-03-28

## Week 1 Goal

- Treat Monday through Friday as a validation week, not a scaling week.
- Run Tier 1 only.
- Keep size at `1` contract per `R$100k`.

## Metrics To Track Daily

- Net `PnL`
- Rolling `30`-day profit factor
- Current drawdown versus the saved historical `p90/p95` drawdown bands
- Trades per day versus expected baseline
- Live spread during `10:00`, `11:00`, `12:00`, and `14:00`
- Any MT5 order/modify/close errors

## End-Of-Week Review

- Stay on Tier 1 if:
  - live spread is often `2+` ticks
  - rolling `30`-day `PF` is under `1.0`
  - live fills look materially worse than the baseline MT5 report
- Promote to Tier 2 if:
  - you have `5` clean paper sessions
  - spreads stayed mostly `0-1` tick
  - no repeated execution errors
  - daily PnL profile is directionally consistent with the saved artifacts

## Week 2 Goal

- Validate Tier 2, the cooldown-only refinement, on paper.
- Keep size unchanged.
- Compare Tier 2 behavior against Tier 1 on:
  - average daily PnL
  - rolling `30`-day `PF`
  - drawdown
  - average trades per day

## Later Upgrade Path

- Tier 3 only after another clean week on Tier 2.
- Tier 4 remains research-only until there is live support for the required execution/sizing workflow.

## Hard Stop Conditions

- Spread above `2` ticks during the entry windows
- `5` consecutive losing days
- Rolling `30`-day `PF < 1.0`
- Repeated MT5 execution errors
- Low-ADX tape plus last `3` contract days plus heavy spread

## Research Backlog After Monday

- Add an explicit broker/B3 fee model to the exact engine so commission sensitivity is no longer a proxy.
- Validate the confidence-weighted sizing research in a live-compatible sizing model.
- Keep tracking whether the recent weak `Q1 2026` tape is reversing or not.
