# Stalker v10.1 Production Comparison - 2026-03-28

## Side-By-Side

| Variant | Status | Key Filters / Management | Trades | Net PnL | PF | Max DD | Win Rate | OnTester |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MT5 validated base `sl0p84/tp0p30` | MT5 `Every Tick` validated | core v10.1 timing/strength logic | 2483 | `R$14,330` | `1.36` | `3.94%` | `80.29%` | n/a |
| Session winner | exact Python | hours `10,11,12,14`, `SkipShortWednesday`, `SkipShortHour13`, `SL 0.84 / TP 0.30` | 1896 | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | `3950.819156` |
| Session winner + cooldown | exact Python | session winner + `30m` between filled entries | 1568 | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | `4263.59877` |
| Session winner + cooldown + max-hold | exact Python | session winner + `30m` cooldown + hard exit after `120` M1 bars | 1568 | `R$14,135` | `1.4851` | `3.29%` | `80.55%` | `4290.320082` |
| Maximum Quality v2 | exact Python | session winner + `30m` cooldown + `120` M1-bar max hold + full Wednesday skip + full `13:00` skip | 1255 | `R$10,665` | `1.4492` | `3.78%` | `80.16%` | `2824.558594` |

## Readout

- Safest paper-trading choice today: the MT5-validated base preset.
- Best exact research candidate: session winner + `30m` cooldown + `120` M1-bar max hold.
- Best quality-biased operator preset: Maximum Quality v2.
- Main risk across all exact variants: transaction-cost sensitivity. The session family survives a `2x` spread stress, but not a `3x` stress.
- Final innovation pass:
  - M30 confirmation improved quality to `PF 1.5335` and `DD 3.25%`, but net fell to `R$12,460`.
  - TP scaling after three consecutive wins underperformed the max-hold leader.
  - Recommendation stays unchanged: keep the plain max-hold leader as the main exact target for MT5 validation.

## Files

- Validated MT5 artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
- Exact max-hold artifact: `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
- Frontier note: `docs/research-frontier-2026-03-28.md`
- MT5 playbook: `docs/mt5-paper-trading-playbook-2026-03-28.md`
