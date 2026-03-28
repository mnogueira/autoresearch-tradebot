# Stalker v10.1 - What Worked And What Didn't - 2026-03-28

## What Worked

| Theme | Best Result | Why It Matters |
| --- | --- | --- |
| `SL/TP` optimization | `SL 0.84 / TP 0.30` improved the surgical baseline to `R$16,025`, `PF 1.4280`, `DD 4.62%` | This was the first major quality jump and became the anchor for everything that followed. |
| Session filter | `10:00, 11:00, 12:00, 14:00` produced `R$15,965`, `PF 1.4438`, `DD 4.04%` | Narrowing to the best hours improved quality without killing the edge. |
| Trade cooldown | `30m` cooldown produced `R$14,085`, `PF 1.4825`, `DD 3.30%` | This was the key cost-control breakthrough. |
| Max hold | `120` M1 bars on top of cooldown produced `R$14,135`, `PF 1.4851`, `DD 3.29%` | Small but real improvement on all major exact metrics. |
| Walk-forward validation | `70/30` holdout on the max-hold leader: train `PF 1.5332`, test `PF 1.3668` | The core strategy held up out of sample. |
| Regime awareness | Trend-day production slice: `R$7,535`, `PF 1.9183`, `DD 3.38%` | Most of the quality edge comes from trend days. |

## What Worked, But Not Enough To Promote

| Theme | Best Result | Why It Stayed Secondary |
| --- | --- | --- |
| Wider TPs | `TP 0.48` on the max-hold leader: `R$18,625`, `PF 1.4356`, `DD 4.92%` | Higher net, but weaker quality balance than the production leader. |
| Daily ADX gate | Trend-day-only preset: `PF 1.9183`, `DD 3.38%` | Extremely clean, but it over-pruned too hard for default deployment. |
| Adaptive cooldown | `30m` on trend days, `15m` on range days: `R$14,770`, `PF 1.4670`, `DD 3.75%` | Better gross net, but worse balanced quality than the fixed `30m` cooldown. |
| Regime switch | Session-only on range days, full production stack on trend days: `R$15,020`, `PF 1.4482`, `DD 4.13%` | Similar story: more net, less quality. |
| M30 confirmation | `R$12,460`, `PF 1.5335`, `DD 3.25%` | Nice quality niche, but too much net-profit giveback. |
| Month-adaptive hours | `R$14,355`, `PF 1.5991`, `DD 3.50%` | Strong in-sample result, but too obviously overfit for Monday promotion. |

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
| Breakeven stop | Best trigger still weaker than baseline | The edge did not want early stop tightening. |

## The Real Risks

- Transaction-cost sensitivity is the main structural risk.
  - `2x` spread stress stayed positive at `R$4,790`, `PF 1.11`, `DD 12.48%`
  - `3x` spread stress failed at `R$-3,300`, `PF 0.9198`, `DD 46.44%`
- Recent softness is real.
  - Last `30` trading days: `R$40`, `PF 1.0357`, `DD 4.67%`
- The regime explanation is coherent:
  - prior-day daily `ADX > 25` share fell from `31.57%` full sample to `16.67%` in the recent weak window
  - first half of `2025`: `R$1,555`, `PF 1.5604`
  - second half of `2025`: `R$655`, `PF 1.2652`

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
