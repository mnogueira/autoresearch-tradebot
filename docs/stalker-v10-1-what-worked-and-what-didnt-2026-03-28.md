# Stalker v10.1 - What Worked And What Didn't - 2026-03-28

## What Worked

| Theme | Best Result | Why It Matters |
| --- | --- | --- |
| `SL/TP` optimization | `SL 0.84 / TP 0.30` improved the surgical baseline to `R$16,025`, `PF 1.4280`, `DD 4.62%` | This was the first major quality jump and became the anchor for everything that followed. |
| Session filter | `10:00, 11:00, 12:00, 14:00` produced `R$15,965`, `PF 1.4438`, `DD 4.04%` | Narrowing to the best hours improved quality without killing the edge. |
| Trade cooldown | `25m` cooldown produced `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158` | This was the key cost-control breakthrough, and the final sweep nudged the best exact cooldown setting from `30m` to `25m`. |
| Max hold | `150` M1 bars on top of the new `25m` cooldown produced `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340` | Small but real improvement on the new cooldown winner and the best deployable exact composite in the sprint, though the recent `60`-day tape did not reward it over Tier 2. |
| Simplification test | Cooldown-only variant kept `99.65%` of net and `99.82%` of PF versus the max-hold leader | This tells us the strategy is not over-dependent on the max-hold timer. |
| Walk-forward validation | `70/30` holdout on the max-hold leader: train `PF 1.5332`, test `PF 1.3668` | The core strategy held up out of sample. |
| Regime awareness | Trend-day production slice: `R$7,535`, `PF 1.9183`, `DD 3.38%` | Most of the quality edge comes from trend days. |
| Component discipline | Ablation showed session filter, cooldown, and `SkipShortWednesday` are the true load-bearing pieces | This separates real edge from convenient but mostly cosmetic parameters. |

## What Worked, But Not Enough To Promote

| Theme | Best Result | Why It Stayed Secondary |
| --- | --- | --- |
| Wider TPs | `TP 0.48` on the max-hold leader: `R$18,625`, `PF 1.4356`, `DD 4.92%` | Higher net, but weaker quality balance than the production leader. |
| Daily ADX gate | Trend-day-only preset: `PF 1.9183`, `DD 3.38%` | Extremely clean, but it over-pruned too hard for default deployment. |
| Stricter daily ADX gate | Cooldown-only with prior-day `ADX > 30`: `R$3,515`, `PF 1.6356`, `DD 4.35%` | Still positive, but it threw away too much net and was actually worse than the simpler `ADX > 25` quality niche. |
| Adaptive cooldown | `30m` on trend days, `15m` on range days: `R$14,770`, `PF 1.4670`, `DD 3.75%` | Better gross net, but worse balanced quality than the fixed `30m` cooldown. |
| Regime switch | Session-only on range days, full production stack on trend days: `R$15,020`, `PF 1.4482`, `DD 4.13%` | Similar story: more net, less quality. |
| M30 confirmation | `R$12,460`, `PF 1.5335`, `DD 3.25%` | Nice quality niche, but too much net-profit giveback. |
| Month-adaptive hours | `R$14,355`, `PF 1.5991`, `DD 3.50%` | Strong in-sample result, but too obviously overfit for Monday promotion. |
| Skip last 3 contract days | `R$12,905`, `PF 1.5281`, `DD 3.49%` | Useful as a caution rule, but not strong enough to replace the production default. |
| Time-widened stop | `0.84 -> 1.20` ATR after `30` bars: `R$14,270`, `PF 1.4887`, `DD 3.28%` | Tiny headline-metric improvement, but still slightly worse than max-hold on the Sortino-weighted composite and more complex operationally. |
| Weekly profit cap | `R$300` cap: `R$14,095`, `PF 1.4937`, `DD 3.32%` | Slightly smoother trade-to-trade and a touch higher PF, but not enough total-package improvement to replace the leader. |
| Market-open avoidance analog | practical `10:15` start: `R$12,670`, `PF 1.5198`, `DD 4.34%` | The true `09:00-09:15` skip is already a no-op here because the production setup does not enter before `10:00`; delaying further improved PF but gave up too much net and drawdown. |
| Confidence-weighted sizing | Research-only fractional sizing by trend-efficiency: `R$18,030.27`, `PF 1.4897`, `DD 3.71%`, composite `3.1301` | This is the clearest sign that stronger signals deserve more size, but it is not deployable until the MQ5 side supports realistic discrete sizing. |
| Confidence-weighted sizing + time-widened stop | Research-only overlay on the `0.84 -> 1.20` ATR after `30` bars variant: `R$18,359.32`, `PF 1.4993`, `DD 3.72%`, composite `3.1377` | This became the strongest raw composite of the entire sprint, which reinforces the case for future graded sizing research rather than binary filters. |
| Confidence-weighted sizing on the final Tier 3 line | Research-only overlay on `25m + 150m`: `R$18,231.63`, `PF 1.4765`, `DD 3.93%`, composite `3.0623` | The idea still looks directionally valid on the newest line, but it did not beat the simpler exact Tier 3 on a deployable basis and still depends on fractional sizing. |
| ROC(5) agreement on the final Tier 3 line | Keep trend-efficiency and add `ROC(5)` directional agreement: `R$14,630`, `PF 1.4935`, `DD 3.28%`, composite `3.1676` | This was the first exact improvement over the final Tier 3 base, which suggests the best remaining frontier is light signal agreement rather than replacing the core signal family. It is now wired into the MQ5 EA/preset flow, so the remaining gap is host-side MT5 validation, not implementation. |
| ROC(5) agreement on the simpler Tier 2 line | Cooldown-only `25m` plus `ROC(5)` directional agreement: `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493` | This is the cleaner ROC-based follow-up because it stays closer to the simpler Tier 2 production path while still improving the composite and holding the same recent `60`-day readout. |
| Adaptive recent-win-rate sizing | Last `20` closed trades control full-size vs half-size: `R$9,260`, `PF 1.4332`, `DD 2.74%`, composite `2.6942` | Cleaner drawdown profile, but too much net and composite giveback to promote beyond research. |
| Trend-efficiency + session VWAP confirmation | Exact tie with the `30m` cooldown baseline: `R$14,085`, `PF 1.4825`, `DD 3.30%` | Interesting because it is an independent confirmation layer, but in practice it added no incremental edge. |
| Equal-weight blend of the top two exact strategies | `R$14,202.50`, `PF 1.4885`, `DD 3.27%`, composite `3.0724` | This is the cleanest sign that the single-strategy frontier is near its ceiling and that any further improvement will likely come from portfolio smoothing, not another small rule tweak. This is now documented as Tier 4, Research Blend. |
| Weekday selectivity | Skip Tuesday and Friday: `R$9,200`, `PF 1.6261`, `DD 2.97%` | Cleaner on PF/DD, but it throws away too much net to become the default. |
| Weekday selectivity + time-widened stop | Mon/Wed/Thu only plus time-widened stop: `R$9,500`, `PF 1.6525`, `DD 3.19%`, composite `2.3232` | Quality improved, but the net giveback was still too large for promotion. |
| Alternate ratio on the plain session winner | `SL 0.60 / TP 0.42`: `R$13,025`, `PF 1.2851`, `DD 4.45%`, `Sortino 2.1894` | Better downside-adjusted return than many variants, but too weak on PF and win rate to replace the production line. |
| Micro-pullback smart entry | `1` tick in `3` bars: `R$2,220`, `PF 1.5139`, `DD 3.92%` | Cleaner PF on a much smaller trade set, but it over-pruned too hard and gave up far too much net and composite. |

## What Did Not Work

| Theme | Result | Takeaway |
| --- | --- | --- |
| EMA crossover exact family | `EMA 5/21`, `SL 0.84 / TP 0.42`: `R$-1,805`, `PF 0.9554`, `DD 39.89%` | The bar-based prototype edge was not real under exact every-tick execution. |
| Bollinger mean reversion | `R$-13,586`, `PF 0.8837`, `DD 138.39%` | Bad family for this implementation. |
| Inside-bar breakout | `R$-4,775`, `PF 0.86`, `DD 58.41%` | Debunked. |
| Patience pullback entries | `30%` pullback in `3` bars: `R$-10,050`, `PF 0.4857`, `DD 100.94%` | This strategy wants fast continuation, not delayed pullback entries. |
| DXY correlation filter | `R$-120`, `PF 0.7670` | Too sparse and not useful. |
| Strict spread-aware entry | `0` trades | Historical spread tape was too coarse for this to add value. |
| Volume confirmation `>1.5x` average | `R$11,750`, `PF 1.4646`, `DD 6.19%` | Cleaner story, worse actual balance. |
| Market-close avoidance | `30` minutes before session end: identical to the reference exact leader | With the current session windows and `120`-bar max hold, this idea is effectively already baked in. |
| Breakeven stop | Best trigger still weaker than baseline | The edge did not want early stop tightening. |
| Confirmation-candle entry | `R$-3,515`, `PF 0.8739`, `DD 38.49%` | Waiting one bar for confirmation destroyed the fast-continuation edge this setup depends on. |
| Static profit-lock `75%/25%` | `R$5,480`, `PF 1.2426`, `DD 9.66%` | Locking profit too early cut the winner distribution and badly weakened the strategy. |
| Confirmation + profit-lock combined | `R$-5,920`, `PF 0.7372`, `DD 61.28%` | The two ideas compounded each other's damage rather than fixing false breakouts. |
| Hot-hand filter | trailing `10` closed trades PnL must be positive: `R$630`, `PF 1.9921`, `DD 1.85%` | Looked clean on the tiny surviving sample, but over-throttled the system so badly that it is not viable. |
| Hard strong-signal gate | top-quartile executed trend-efficiency only: `R$5,570`, `PF 1.4829`, `DD 4.61%` | The edge appears to want graded sizing, not a binary strong/weak cutoff. |
| Softer strong-signal gate | top-half executed trend-efficiency only: `R$8,555`, `PF 1.4047`, `DD 4.72%` | Less bad than the top quartile, but still clearly inferior to the baseline production line. |
| Equal-risk/reward ratio | `SL 0.50 / TP 0.50`: `R$8,480`, `PF 1.1711`, `DD 6.46%` | A neat idea, but it weakened both quality and robustness. |
| ATR trailing stop | `1.0x` ATR: `R$13,910`, `PF 1.4755`, `DD 3.28%`; `1.5x` and `2.0x` ATR were exact ties with the current leader | There is no real deployable upside here, so more ATR-trailing optimization is not worth the cycle budget. |
| Dynamic ATR target | `TP 1.00x ATR`: `R$17,915`, `PF 1.2569`, `DD 6.13%` | Higher gross net, but materially worse risk-adjusted quality than the fixed `0.30 ATR` target. |
| Dynamic session-hour pruning | Skip any hour whose prior `10`-trading-day Tier 2 PnL is negative: `R$10,795`, `PF 1.4950`, `DD 5.79%`, composite `1.8765` | The idea sounded adaptive, but it overreacted and stripped out too much opportunity while worsening drawdown. |
| First trade of day only | `R$8,600`, `PF 1.4531`, `DD 3.82%` | Cleaner than some rejected ideas, but much too much net and composite giveback to promote. |
| ML signal overlays | Logistic `AUC 0.5987`, random forest `AUC 0.5607`, but all trade overlays underperformed badly | There is a bit of predictive information in the features, but not enough to survive translation into a tradable overlay on the existing strategy. |
| Volatility breakout ATR-expansion entry | `0` trades | Too restrictive in this implementation; no evidence of a usable replacement signal family. |
| EMA50 direction filter | Identical to the cooldown baseline | The existing signal family is already directionally aligned enough that this filter adds no value. |
| Bigger micro-pullback smart entry | `2` ticks in `3` bars: `R$1,550`, `PF 1.3944`, `DD 3.73%` | Pushing the better-entry idea harder just starved the strategy of too many fills. |
| Two-bar trend confirmation | `R$-1,485`, `PF 0.7564`, `DD 18.63%` | Waiting for two consecutive M15 closes in the signal direction destroyed the fast-continuation edge. |
| Volume-weighted entry sizing by relative volume | `R$10,340`, `PF 1.4388`, `DD 3.70%`, composite `2.3424` | Lowering size on lower-relative-volume signals reduced risk, but it also gave up too much net and composite to justify promotion. |
| Exact ATR-adaptive target scaling | `TP = 0.30 * (current daily ATR / prior 20-session average ATR)`, clipped `0.75x-1.50x`: `R$13,650`, `PF 1.4369`, `DD 3.62%`, composite `2.7777` | Making the target breathe with recent volatility sounded sensible, but the fixed `0.30 ATR` target still produced a better risk-adjusted package. |
| Tighter exact ATR-adaptive target scaling | Best case `0.90x-1.20x` clip: `R$13,985`, `PF 1.4488`, `DD 3.45%`, composite `2.9315` | Tightening the ATR clip improved on the looser adaptive TP attempt, but it still stayed below the plain Tier 3 baseline and well below the ROC(5)-agreement line. |
| Signal-bar volume gate | Current bar volume must exceed the rolling `20`-bar average: `R$13,405`, `PF 1.4456`, `DD 3.41%` | Extra microstructure confirmation sounded sensible, but it removed too many acceptable trades and still underperformed the plain Tier 2 line. |
| Next-open patience entry | `R$-99,785`, `PF 0.0060`, `DD 997.85%` | The strategy already extracts its edge from fast retracement fills; delaying to the next minute was catastrophic. |
| Plain next-open entry proxy | `R$-130,870`, `PF 0.0052`, `DD 1308.7%` | Converting the execution model into a wait-for-next-minute entry completely destroyed the edge. |
| Next-open one-tick-better limit proxy | `R$-29,100`, `PF 0.0058`, `DD 291.0%` | A passive next-open fill requirement starved the system of the good fast entries and did not work as a live improvement path. |
| ATR trailing stop after 50% target | exact tie with Tier 2 at `R$14,085`, `PF 1.4825`, `DD 3.30%` | This added no value over the simpler cooldown-only line. |
| Bollinger squeeze gate | Bottom-quartile squeeze: `R$2,595`, `PF 1.4428`, `DD 5.24%`; bottom-third squeeze: `R$2,670`, `PF 1.3160`, `DD 8.27%` | Volatility compression did not improve this signal family; it mostly just removed too many trades. |
| RSI mean-reversion family | `RSI(14) < 30 / > 70` session prototype: `R$-11,755`, `PF 0.8236`, `DD 119.38%` | A fundamentally different edge was worth testing, but this implementation was clearly wrong for WDO versus the existing trend-continuation logic. |
| ROC-only replacement signal family | Best case `Tier 3 ROC(5)`: `R$14,930`, `PF 1.4441`, `DD 3.80%`, composite `2.9572` | ROC was the closest simpler alternative to trend-efficiency, but it still gave up too much PF and drawdown control to replace the incumbent signal family. |
| Signal-momentum gate | Require trend-efficiency to be strictly increasing across the last `2` bars: `R$12,200`, `PF 1.4324`, `DD 3.36%`; across the last `3` bars: `R$8,885`, `PF 1.4104`, `DD 5.45%` | The signal already encodes enough trend state; forcing an acceleration pattern over-pruned the good trades and never beat the plain cooldown lines. |
| Early exit on reversal | Exit immediately if trend-efficiency flips sign within `5` bars of entry: `R$2,445`, `PF 1.1498`, `DD 4.82%`, composite `0.8932` | Cutting the trade at the first sign flip sounded defensive, but it chopped winners too aggressively and destroyed the edge. |

## The Real Risks

- Transaction-cost sensitivity is the main structural risk.
  - `2x` spread stress stayed positive at `R$4,790`, `PF 1.11`, `DD 12.48%`
  - `3x` spread stress failed at `R$-3,300`, `PF 0.9198`, `DD 46.44%`
  - fixed `5`-tick spread stress was catastrophic at `R$-16,975`, `PF 0.6614`, `DD 168.02%`
- Flat commission is not the main modeled cost in the exact harness.
  - the exact engine still carries `ROUND_TRIP_COST_BRL = 0.0`, so doubling the flat-cost proxy had no effect
  - operationally, the trustworthy live cost control is still the spread guardrail, not the flat-fee proxy
- Recent softness is real.
  - Last `30` trading days: `R$40`, `PF 1.0357`, `DD 4.67%`
- The regime explanation is coherent:
  - prior-day daily `ADX > 25` share fell from `31.57%` full sample to `16.67%` in the recent weak window
  - first half of `2025`: `R$1,555`, `PF 1.5604`
  - second half of `2025`: `R$655`, `PF 1.2652`
- Late contract-cycle days are weaker:
  - first `3` contract days: `PF 1.7455`, `DD 3.83%`
  - last `3` contract days: `PF 1.2614`, `DD 6.50%`
  - Monday `2026-03-30` should be treated as a cautious month-end validation session, not as a clean fresh-contract tape

## Production Answer Today

- Safest live-paper anchor:
  - MT5 `Every Tick` validated `SL 0.84 / TP 0.30`
- Best exact refinement waiting on MT5 validation:
  - session filter + `25m` cooldown + `150` M1-bar max hold
- Cleaner first upgrade before that:
  - session filter + `25m` cooldown only
- Optional quality-focused niche:
  - prior-day daily `ADX(14) > 25` gate on top of the production stack

## Files

- Evolution summary:
  - `docs/stalker-v10-1-strategy-evolution-summary-2026-03-28.md`
- Production comparison:
  - `docs/stalker-v10-1-production-comparison-2026-03-28.md`
- Frontier note:
  - `docs/research-frontier-2026-03-28.md`
- Monday checklist:
  - `docs/mt5-monday-morning-checklist-2026-03-30.md`
- Paper-trading playbook:
  - `docs/mt5-paper-trading-playbook-2026-03-28.md`
