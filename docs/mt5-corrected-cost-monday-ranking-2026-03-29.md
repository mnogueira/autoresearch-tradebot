# MT5 Corrected-Cost Monday Ranking - 2026-03-29

## Executive Call

- Monday still runs Tier 1 only.
- The corrected-cost exact research is now mapped tightly enough to rank the best honest post-Monday targets.

## Final Ranking

| Rank | Variant | Full Net | PF | DD | 70/30 Test Net | Test PF | Test DD | Rolling WF | Read |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | Stacked combo: long ATR prune + short hours `10/11/12` | `R$3,317` | `1.1334` | `8.07%` | `R$1,580` | `1.2615` | `6.02%` | `4/7` pass | strongest static corrected-cost branch |
| 2 | Long-ATR-prune-only fallback | `R$3,243` | `1.1284` | `7.79%` | `R$1,629` | `1.2696` | `6.00%` | not rolled yet | nearly tied, simpler to implement |
| 3 | Balanced baseline | `R$3,024` | `1.0966` | `7.06%` | `R$887` | `1.1091` | `7.91%` | `3/7` pass | first true corrected-cost survivor |
| 4 | Best short-only sleeve | `R$2,168` | `1.1458` | `12.10%` | `R$1,610` | `1.4601` | `2.85%` | not rolled | stronger edge by side, but too much full-sample DD |
| 5 | Best short-only timing sleeve `10/11/12` | `R$2,619` | `1.1750` | `12.33%` | n/a | n/a | n/a | `3/7` pass | cleaner shorts, still less robust than the combo |

## Why Rank 1 Wins

- It is the best full-sample corrected-cost static result.
- It stays positive on the `70/30` holdout with a clearly better PF than the balanced baseline.
- Its rolling walk-forward is better than the balanced baseline:
  - stacked combo `4/7` pass
  - balanced baseline `3/7` pass
- Recent windows stayed healthy:
  - recent `60d` `R$348`, `PF 1.4203`
  - recent `30d` `R$403`, `PF 2.1749`
  - recent `10d` `R$280`, `PF inf`

## Why Rank 2 Still Matters

- It is only a tiny step behind Rank 1.
- It is operationally simpler because it does not require side-specific short-hour routing.
- If the first host-side MT5 validation should minimize implementation complexity, this is the cleaner fallback.

## Why Short-Only Is Not The Main Answer

- Shorts clearly carry more honest edge than longs.
- But pure short-only variants still carry too much full-sample drawdown.
- The strongest short-only timing sleeve only passes `3/7` rolling folds, versus `4/7` for the stacked combo.
- The best corrected-cost portfolio still comes from keeping both directions and pruning the weaker long sleeve selectively.

## Final Monday Interpretation

1. Monday: Tier 1 only.
2. First corrected-cost host-side MT5 validation target after Monday:
   - stacked combo: long ATR prune + short hours `10/11/12`
3. Simpler fallback if implementation complexity matters more:
   - long-ATR-prune-only branch
4. Do not promote any corrected-cost Python branch directly without host-side MT5 validation.
