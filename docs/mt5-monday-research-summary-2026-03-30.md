# MT5 Monday Research Summary - 2026-03-30

## Executive Call

- Monday live paper trading still starts with the validated MT5 Tier 1 base preset.
- The best corrected-cost static deployment candidate remains the M1 stacked combo:
  - prune only long entries on top-ATR tercile days
  - restrict shorts to `10/11/12`
  - `SL 1.0`
  - `TP 0.48`
  - `60m` cooldown
  - Friday off
  - skip last contract day
- Exact corrected-cost numbers:
  - full sample: `R$3,317`, `PF 1.1334`, `DD 8.07%`
  - `70/30` test: `R$1,580`, `PF 1.2615`, `DD 6.02%`
  - rolling walk-forward: `4/7` folds passed

## Strongest Challengers

| Variant | Full Sample | 70/30 Test | Recent Jan-Mar 2026 | Call |
| --- | --- | --- | --- | --- |
| M1 stacked combo | `R$3,317`, `PF 1.1334`, `DD 8.07%` | `R$1,580`, `PF 1.2615`, `DD 6.02%` | `R$410`, `PF 1.5640`, `DD 1.75%` | deployment winner |
| M1 combo + M5 EMA20 confirmation | `R$3,812`, `PF 1.1576`, `DD 7.37%` | `R$1,534`, `PF 1.2578`, `DD 5.88%` | `R$410`, `PF 1.5640`, `DD 1.75%` | strongest static research overlay, but no current-regime gain |
| M5 proxy of combo logic | `R$6,945`, `PF 1.3841`, `DD 5.18%` | `R$1,605`, `PF 1.3232`, `DD 7.43%` | `R$-9`, `PF 0.9900`, `DD 3.54%` | promising structural research branch, not promoted |
| Daily ATR above 20-day average gate | `R$2,903`, `PF 1.3106`, `DD 6.11%` | `R$1,287`, `PF 1.5936`, `DD 2.72%` | `R$267`, `PF 2.1266`, `DD 1.49%` on recent `30d` | cleaner but too selective |
| Long-ATR-prune-only fallback | `R$3,243`, `PF 1.1284`, `DD 7.79%` | `R$1,629`, `PF 1.2696`, `DD 6.00%` | positive | simpler fallback |

## Jan-Mar 2026 Trade Anatomy

- The M1 stacked combo stayed positive in the current regime:
  - `54` trading days
  - `40` trades
  - `33` winners / `7` losers
  - `R$410`, `PF 1.5640`, `DD 1.75%`
- Winners vs losers:
  - winners: `R$1,137` total, `R$34.45` average, `9.76` average minutes
  - losers: `R$-727` total, `R$-103.86` average, `8.29` average minutes
- Direction split:
  - longs: `12` trades, `R$163`, `WR 83.33%`, `8.0` average minutes
  - shorts: `28` trades, `R$247`, `WR 82.14%`, `10.14` average minutes
- Hour map in Jan-Mar:
  - `10h`: `15` trades, `R$280`, `WR 93.33%`
  - `11h`: `13` trades, `R$-43`, `WR 69.23%`
  - `12h`: `11` trades, `R$129`, `WR 81.82%`
  - `13h`: `1` trade, `R$44`
- Loss clustering:
  - `11h` produced `4` of the `7` losers for `R$-374`
  - `12h` produced `2` losers but larger average loss, `R$-128.5`
  - the strongest recent sleeve was still short-side flow at `10h`

Detailed trade export:
- [recent_3m_combo_trades.csv](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_recent_analysis_20260329/recent_3m_combo_trades.csv)

## What Failed

- Session VWAP crossover:
  - `R$-14,102`, `PF 0.7173`, `DD 139.29%`
- Opening-range breakout:
  - first `15m`: `R$-41,375`, `PF 0.6569`, `DD 372.23%`
  - first `30m`: `R$-38,533`, `PF 0.6509`, `DD 346.16%`
- Donchian breakout:
  - best case `N=30`: `R$-11,965`, `PF 0.6690`, `DD 109.58%`
- Momentum ignition:
  - `R$-9,831`, `PF 0.7073`, `DD 96.54%`
- Volume gate on combo:
  - `R$-262`, `PF 0.9746`, `DD 12.36%`
- Full `14h` prune:
  - `R$2,472`, `PF 1.0938`, `DD 9.29%`
  - near-miss, but still worse than the combo

## Recommendation

1. Monday: deploy Tier 1 validated MT5 base only.
2. First corrected-cost MT5 validation target: M1 stacked combo.
3. Next research validation target: M1 combo + M5 EMA20 confirmation.
4. Separate structural research branch: true M5 implementation of the combo logic.

## Honest Bottom Line

- The corrected-cost frontier is now well-mapped.
- The M1 stacked combo is still the best Monday deployment candidate.
- The M5 proxy and the M5 EMA20 confirmation layer are both real research leads, but neither gives a strong enough current-regime advantage to replace the M1 combo for Monday.
