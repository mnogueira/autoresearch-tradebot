# Stalker v10.1 Production Comparison - 2026-03-28

## Correction Notice

The earlier Python production ladder was materially overstated.

Corrected rerun fixes:
- `ROUND_TRIP_COST_BRL = 11.0`
- lagged ROC agreement
- ATR sizing from `get_atr_open()`
- cooldown reset at each new session

Source:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## Monday Comparison

| Variant | Full Net | PF | DD | 70/30 Test Net | Test PF | Test DD | Recent 60d Net | Recent 60d PF | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| MT5 validated Tier 1 base | `R$14,330` | `1.36` | `3.94%` | n/a | n/a | n/a | n/a | n/a | Monday default |
| Tier 2A corrected `TP 0.48` + `60m` cooldown + Friday off + skip last `1` contract day | `R$2,543` | `1.0853` | `9.60%` | `R$879` | `1.1142` | `8.77%` | `R$312` | `1.2708` | best corrected-cost static survivor, research only |
| Tier 2A corrected `TP 0.48` + `60m` cooldown + Friday off + `150m` max-hold | `R$2,153` | `1.0679` | `11.68%` | `R$623` | `1.0754` | `9.53%` | `R$312` | `1.2708` | best corrected-cost local refinement, research only |
| Tier 2A corrected `TP 0.48` + `60m` cooldown | `R$2,285` | `1.0545` | `17.15%` | `R$-68` | `0.9941` | `15.16%` | `R$259` | `1.1516` | first static survivor, research only |
| Tier 1 exact analog, corrected | `R$-15,135` | `0.7546` | `149.78%` | `R$-5,174` | `0.6959` | `56.13%` | `R$-1,689` | `0.5354` | invalidated |
| Tier 2, corrected | `R$-3,910` | `0.8837` | `53.59%` | `R$-2,534` | `0.7455` | `33.06%` | `R$-1,050` | `0.5268` | invalidated |
| Tier 2A, corrected | `R$-2,951` | `0.9147` | `46.08%` | `R$-2,255` | `0.7800` | `29.02%` | `R$-753` | `0.6346` | invalidated |
| Tier 3, corrected | `R$-3,142` | `0.9110` | `47.41%` | `R$-2,372` | `0.7731` | `30.13%` | `R$-724` | `0.6487` | invalidated |

## Practical Ranking

1. Tier 1 validated MT5 base
2. Everything else is research-only until it survives corrected costs or fresh host-side MT5 validation

## What Still Matters

- Spread rule still stands:
  - do not trade above `2` ticks
- Recent corrected `10d` windows were still positive, so the setup is not obviously dead intraday
- A widened-target, lower-frequency corrected survivor does exist now:
  - Tier 2A geometry with `TP 0.48` and `60m` cooldown
  - but its holdout is too weak to promote yet
- But the corrected full-sample and holdout profiles are not strong enough to justify automatic promotion beyond Tier 1

## Historical Note

Earlier exact rankings remain useful as idea-generation history, but they are superseded for deployment decisions by the corrected-cost rerun above.
