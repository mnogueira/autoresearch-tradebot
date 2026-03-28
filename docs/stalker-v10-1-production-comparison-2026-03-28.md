# Stalker v10.1 Production Comparison - 2026-03-28

## Side-By-Side

| Variant | Net | PF | DD | Win Rate | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, MT5-validated `sl0p84/tp0p30` | `R$14,330` | `1.36` | `3.94%` | `80.29%` | 2483 |
| Session winner | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | 1896 |
| Session winner + cooldown | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | 1568 |
| Max-hold v2, session winner + cooldown + `120` M1-bar max hold | `R$14,135` | `1.4851` | `3.29%` | `80.55%` | 1568 |

## Quality Alternative

| Variant | Net | PF | DD | Win Rate | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Maximum Quality v2 | `R$10,665` | `1.4492` | `3.78%` | `80.16%` | 1255 |

## Readout

- Safest paper-trading choice today: the MT5-validated base preset.
- Best exact research candidate: session winner + `30m` cooldown + `120` M1-bar max hold.
- Best quality-biased operator preset: Maximum Quality v2.
- Main risk across all exact variants: transaction-cost sensitivity. The max-hold leader fails under `3x` spread stress: `R$-3,300`, `PF 0.9198`, `DD 46.44%`.
- Final innovation pass:
  - M30 confirmation improved quality to `PF 1.5335` and `DD 3.25%`, but net fell to `R$12,460`.
  - TP scaling after three consecutive wins underperformed the max-hold leader.
  - Recommendation stays unchanged: keep the plain max-hold leader as the main exact target for MT5 validation.
- Position sizing stays mechanically clean:
  - `0.5` contract: `R$7,067.5`, `DD 2.14%`
  - `1.0` contract: `R$14,135`, `DD 3.29%`
  - `2.0` contracts: `R$28,270`, `DD 5.03%`
  - `3.0` contracts: `R$42,405`, `DD 6.32%`

## Files

- Validated MT5 artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
- Exact max-hold artifact: `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
- Frontier note: `docs/research-frontier-2026-03-28.md`
- MT5 playbook: `docs/mt5-paper-trading-playbook-2026-03-28.md`
