# Stalker v10.1 Strategy Ceiling Assessment

## Executive Answer

The current signal family looks close to its local ceiling on the available WDO tape.

- Best exact deployable full-sample line so far:
  - Tier 3 + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,885`, `PF 1.4993`, `DD 3.21%`
  - Sortino-weighted composite `3.3186`
- Best simpler exact upgrade path:
  - Tier 2A, `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,970`, `PF 1.5145`, `DD 3.23%`
  - composite `3.3124`
- Best MT5-validated line remains lower because it is the only host-side-validated production anchor:
  - Tier 1 MT5 base preset

That means the signal family still has room to reshuffle a few basis points of quality, but not enough to call it an open-ended optimization frontier anymore.

## What Ceiling Means Here

For this repo, "ceiling" means:

1. New exact deployable filters stop improving the full risk-adjusted package in a material way.
2. Alternate signal families fail to beat the incumbent trend/retracement stack.
3. Remaining upside mostly comes from research-only sizing overlays or execution quality, not from a new hard rule that obviously belongs in Monday deployment.

That is where the strategy now appears to be.

## Evidence

### 1. Exact deployable improvements are now small

- Tier 2: `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
- Tier 2A: `R$15,970`, `PF 1.5145`, `DD 3.23%`, composite `3.3124`
- Tier 3: `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340`
- Tier 3 + `ROC(5)`: `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`

These are real improvements, but they are incremental, not transformational.

### 2. Walk-forward results stay positive but not explosive

All main tiers passed the chronological `70/30` split.

- Tier 1 exact analog: test composite `2.6668`
- Tier 2: test composite `2.5061`
- Tier 2A: test composite `3.9009`
- Tier 3: test composite `2.5061`
- Tier 3 + `ROC(5)` also held up through its own follow-up validation

So the stack is robust enough to keep, but the out-of-sample results do not suggest a hidden, much better signal waiting nearby.

### 3. New signal families keep losing

Rejected or clearly inferior:

- EMA crossover family
- RSI mean reversion
- Inside-bar breakout
- Session high/low breakout
- Session VWAP extreme mean reversion
- Opening-bias and prior-day-bias confirmation
- Bollinger squeeze gating
- Delayed next-open execution variants

This is strong evidence that the current family is dominating the obvious alternatives on this dataset.

### 4. Research-only sizing still helps gross PnL, but not enough

Trend-strength sizing overlay on top of the current tiers raised net profit:

- Tier 2A overlay: `R$18,258.17`, `PF 1.4827`, `DD 3.94%`, composite `3.0554`
- Tier 3 overlay: `R$18,231.63`, `PF 1.4765`, `DD 3.93%`, composite `3.0623`

So sizing can lift gross net, but it does not beat the best exact deployable composite once the extra drawdown is counted.

### 5. Execution quality is now the biggest remaining upside

The one dramatic remaining lever was the fill-quality proxy:

- one-tick better fill proxy: `R$21,925`, `PF 1.7925`, `DD 2.64%`, composite `5.0181`

But that is not a real deployable signal change. It says the next big frontier is execution, not another indicator.

## Honest Conclusion

The strategy is probably near its ceiling for this signal family under the current data and exact-engine assumptions.

- Deployable exact ceiling:
  - around composite `3.15` to `3.17`
- Research-only gross-net ceiling:
  - materially higher, but it comes from sizing overlays and execution assumptions rather than a clearly better hard rule
- Operational implication:
  - stop expecting a radically better signal from small extra filters
  - focus on MT5 validation, execution quality, and disciplined rollout

## Monday Implication

- Monday default stays Tier 1 because it is the validated MT5 anchor.
- First upgrade path remains Tier 2, then Tier 2A.
- Tier 3 + `ROC(5)` is the highest exact research line, but it should only be promoted after the simpler variants behave well in paper trading.
- The biggest practical remaining upside is:
  - better fills
  - strict spread discipline
  - avoiding poor execution conditions
