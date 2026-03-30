# MT5 Corrected-Cost Final Handoff - 2026-03-29

## Bottom Line

- Monday still runs the validated MT5 Tier 1 base only.
- The best corrected-cost exact research branch is now clear enough to rank honestly, but it is still a post-Monday MT5 validation target, not a same-day promotion.

## Best Corrected-Cost Leader

- Current leader:
  - stacked combo
  - prune only long entries on top-ATR tercile days
  - restrict shorts to `10/11/12`
  - `SL 1.0`
  - `TP 0.48`
  - `60m` cooldown
  - Friday off
  - skip last contract day
- Exact numbers:
  - full sample: `R$3,317`, `PF 1.1334`, `DD 8.07%`
  - `70/30` test: `R$1,580`, `PF 1.2615`, `DD 6.02%`
  - rolling walk-forward: `4/7` test folds passed

## Main Challengers And Why They Failed

- Long-ATR-prune-only fallback:
  - `R$3,243`, `PF 1.1284`, `DD 7.79%`
  - almost tied, but still slightly below the stacked combo
- Balanced baseline:
  - `R$3,024`, `PF 1.0966`, `DD 7.06%`
  - positive and honest, but weaker PF and weaker rolling robustness than the combo
- Best short-only sleeve:
  - `R$2,619`, `PF 1.1750`, `DD 12.33%`
  - cleaner edge by direction, but too much full-sample drawdown and only `3/7` rolling folds passed
- `14h` prune near-miss:
  - `R$2,472`, `PF 1.0938`, `DD 9.29%`
  - the hour is weak, but removing it entirely gives back too much edge
- EMA20 filter on top of the combo:
  - `R$3,206`, `PF 1.1486`, `DD 9.14%`
  - near-miss, but still worse once drawdown is counted
- M5 EMA20 confirmation on top of the combo:
  - full sample `R$3,812`, `PF 1.1576`, `DD 7.37%`
  - `70/30` test `R$1,534`, `PF 1.2578`, `DD 5.88%`
  - recent Jan-Mar `2026` stayed exactly tied with the combo at `R$410`, `PF 1.5640`, `DD 1.75%`
  - strongest lightweight overlay, but not enough recent-regime separation to change Monday
- Volume gate `1.5x` on top of the combo:
  - `R$-262`, `PF 0.9746`, `DD 12.36%`
  - over-pruned and failed holdout
- VWAP crossover:
  - `R$-14,102`, `PF 0.7173`, `DD 139.29%`
  - not viable as a replacement signal family
- M5 proxy of the same combo logic:
  - full sample `R$6,945`, `PF 1.3841`, `DD 5.18%`
  - `70/30` test `R$1,605`, `PF 1.3232`, `DD 7.43%`
  - but recent Jan-Mar `2026` slipped to `R$-9`, `PF 0.9900`
  - strong structural lead, but not stable enough in the current regime to replace the M1 combo for Monday
- Daily ATR above 20-day average regime gate:
  - `R$2,903`, `PF 1.3106`, `DD 6.11%`
  - `70/30` test `R$1,287`, `PF 1.5936`, `DD 2.72%`
  - much cleaner, but too selective and still below the stacked combo on total score
- Dual-timeframe M15 EMA20 confirmation:
  - `R$3,206`, `PF 1.1486`, `DD 9.14%`
  - `70/30` test `R$773`, `PF 1.1331`, `DD 9.97%`
  - recent windows improved, but the total profile stayed below the combo
- Opening-range breakout:
  - first `15m`: `R$-41,375`, `PF 0.6569`, `DD 372.23%`
  - first `30m`: `R$-38,533`, `PF 0.6509`, `DD 346.16%`
  - decisively non-viable
- Donchian breakout:
  - best case `N=30`: `R$-11,965`, `PF 0.6690`, `DD 109.58%`
  - another clear dead end under corrected costs

## Hour Map Summary

- Corrected-cost stacked combo by entry hour:
  - `10h`: `R$365`, `PF 1.0304`
  - `11h`: `R$309`, `PF 1.0440`
  - `12h`: `R$2,300`, `PF 1.7749`
  - `13h`: `R$466`, `PF 1.2316`
  - `14h`: `R$-123`, `PF 0.8565`
- Interpretation:
  - `12h` is the real profit engine
  - `14h` is the only clearly losing hour
  - but fully cutting `14h` did not improve the total strategy score

## Monday Recommendation

1. Deploy the validated MT5 Tier 1 base for Monday paper trading.
2. Keep the corrected-cost stacked combo as the first post-Monday MT5 validation target.
3. Keep the long-ATR-prune-only branch as the simpler fallback if implementation complexity matters more than the last small edge gain.
4. Do not promote VWAP, opening-range breakout, Donchian breakout, or the volume gate branches.

## Honest Interpretation

- The strategy does survive corrected costs, but only in a narrower and more conservative form than the pre-correction frontier suggested.
- The best remaining upside is still in careful trade selection and sizing, not in another replacement signal family.
- The one structural branch that did stand out was the M5 proxy, but it weakened enough in Jan-Mar `2026` that it should stay a separate research track, not a Monday swap.
- Monday should therefore be treated as validation-first, with the corrected-cost combo queued as the next serious MT5 candidate rather than an immediate switch.
