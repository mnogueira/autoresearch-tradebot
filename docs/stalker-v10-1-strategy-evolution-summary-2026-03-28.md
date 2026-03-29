# Stalker v10.1 Strategy Evolution Summary - 2026-03-28

## Core Journey

| Stage | Variant | Net | PF | DD | Win Rate | Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Original surgical timing baseline | `R$14,510` | `1.3224` | `5.18%` | `74.03%` | 1960 |
| 2 | SL/TP-optimized core (`SL 0.84 / TP 0.30`) | `R$16,025` | `1.4280` | `4.62%` | `80.00%` | 1960 |
| 3 | Session filter (`10,11,12,14`) | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | 1896 |
| 4 | Session filter + `30m` cooldown | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | 1568 |
| 5 | Session filter + `25m` cooldown | `R$14,350` | `1.4749` | `3.30%` | `80.50%` | 1615 |
| 6 | Session filter + `25m` cooldown + `150` M1 max hold | `R$14,420` | `1.4784` | `3.28%` | `80.50%` | 1615 |

## What Each Step Added

- Stage `1` gave us the first clean timing-aware intraday template worth refining.
- Stage `2` was the biggest single jump in quality: the `0.84 / 0.30` exit pair materially improved net, PF, and drawdown together.
- Stage `3` showed that narrowing the strategy to the strongest hours improved PF and drawdown without killing the edge.
- Stage `4` was the key cost-control breakthrough. The `30`-minute cooldown reduced trade count and lifted PF while cutting drawdown hard.
- Stage `5` was the fine cooldown refinement. Tightening the lockout to `25` minutes slightly improved the deployable composite without changing the strategy's character.
- Stage `6` was the final exact refinement. The `150` M1-bar max hold improved net, PF, DD, and composite score together, even if only by a narrow margin over `120`.

## Validation Anchor

The safest live-paper anchor is still the MT5 `Every Tick` validation, not the exact Python leader:

| Variant | Net | PF | DD | Win Rate | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| MT5 validated `SL 0.84 / TP 0.30` | `R$14,330` | `1.36` | `3.94%` | `80.29%` | 2483 |

That is why the Monday recommendation stays conservative:
- Safest deployment preset: the MT5-validated base preset.
- Best next MT5 validation target: the exact `25m + 150m` max-hold leader.

## Final Frontier Readout

- Best exact research candidate: session filter + `25m` cooldown + `150` M1 max hold.
- Biggest remaining risk: transaction-cost sensitivity. Under `3x` spread stress the max-hold leader breaks.
- Best exploratory but unpromoted niche: month-adaptive session hours.
  - `R$14,355`, `PF 1.5991`, `DD 3.50%`
  - I am not promoting it because the month mapping was derived from the same historical tape, so the overfit risk is too obvious for Monday deployment.

## Current Caveat

- The most recent `30` trading days were much softer than the full-sample average:
  - `R$40`, `PF 1.0357`, `DD 4.67%`
- The softness does not look like a lack of signals. It looks more like weaker signal quality in a less-trending tape:
  - trades per day rose from `1.26` to `1.60`
  - prior-day daily `ADX(14) > 25` fell from `31.57%` full-sample to `16.67%` recently
- Operational implication:
  - Monday should be treated as a cautious paper-validation start, not a scale-up day.

## Source Artifacts

- Surgical baseline and SL/TP grid: `artifacts/outputs/stalker_v10_1_surgical_sltp_grid_20260328/summary.json`
- Session filter refinement: `artifacts/outputs/stalker_v10_1_session_refinement_20260328/summary.json`
- Cooldown refinement: `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`
- Max-hold refinement: `artifacts/outputs/stalker_v10_1_maxhold_sweep_followups_20260328/summary.json`
- Final wrap-up experiments: `artifacts/outputs/stalker_v10_1_session_wrapup_followups_20260328/summary.json`
