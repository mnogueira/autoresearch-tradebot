# Stalker v10.1 - What Worked And What Didn't - 2026-03-28

## What Worked

| Theme | Best Result | Why It Matters |
| --- | --- | --- |
| `SL/TP` optimization | `SL 0.84 / TP 0.30` improved the surgical baseline to `R$16,025`, `PF 1.4280`, `DD 4.62%` | This was the first major quality jump and became the anchor for everything that followed. |
| Session filter | `10:00, 11:00, 12:00, 14:00` produced `R$15,965`, `PF 1.4438`, `DD 4.04%` | Narrowing to the best hours improved quality without killing the edge. |
| Trade cooldown | `30m` cooldown produced `R$14,085`, `PF 1.4825`, `DD 3.30%` | This was the key cost-control breakthrough. |
| Max hold | `120` M1 bars on top of cooldown produced `R$14,135`, `PF 1.4851`, `DD 3.29%` | Small but real improvement on all major exact metrics. |
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
| Equal-weight blend of the top two exact strategies | `R$14,202.50`, `PF 1.4885`, `DD 3.27%`, composite `3.0724` | This is the cleanest sign that the single-strategy frontier is near its ceiling and that any further improvement will likely come from portfolio smoothing, not another small rule tweak. This is now documented as Tier 4, Research Blend. |
| Weekday selectivity | Skip Tuesday and Friday: `R$9,200`, `PF 1.6261`, `DD 2.97%` | Cleaner on PF/DD, but it throws away too much net to become the default. |
| Weekday selectivity + time-widened stop | Mon/Wed/Thu only plus time-widened stop: `R$9,500`, `PF 1.6525`, `DD 3.19%`, composite `2.3232` | Quality improved, but the net giveback was still too large for promotion. |
| Alternate ratio on the plain session winner | `SL 0.60 / TP 0.42`: `R$13,025`, `PF 1.2851`, `DD 4.45%`, `Sortino 2.1894` | Better downside-adjusted return than many variants, but too weak on PF and win rate to replace the production line. |

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
| ML signal overlays | Logistic `AUC 0.5987`, random forest `AUC 0.5607`, but all trade overlays underperformed badly | There is a bit of predictive information in the features, but not enough to survive translation into a tradable overlay on the existing strategy. |

## The Real Risks

- Transaction-cost sensitivity is the main structural risk.
  - `2x` spread stress stayed positive at `R$4,790`, `PF 1.11`, `DD 12.48%`
  - `3x` spread stress failed at `R$-3,300`, `PF 0.9198`, `DD 46.44%`
  - fixed `5`-tick spread stress was catastrophic at `R$-16,975`, `PF 0.6614`, `DD 168.02%`
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
  - session filter + `30m` cooldown + `120` M1-bar max hold
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
