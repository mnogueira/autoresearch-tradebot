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
- Final cost follow-up on the max-hold leader:
  - `TP 0.42`: `R$15,660`, `PF 1.3951`, `DD 5.16%`
  - `TP 0.48`: `R$18,625`, `PF 1.4356`, `DD 4.92%`
  - interpretation: wider targets improve gross net, but the plain `TP 0.30` leader still has the best overall `PF/DD/OnTester` balance.
- Monte Carlo on the max-hold leader is supportive, not magical:
  - shuffled trade-order `95th` percentile drawdown: `8.79%`
  - bootstrap ending PnL `5th/95th`: `R$10,483.25` / `R$17,686.75`
- The strict spread-aware entry idea was a dead end on this tape:
  - historical cached spread only took values `0` or `1` tick
  - strict `current spread < prior session average spread` produced `0` trades
- Recent degradation check on the exact max-hold leader:
  - last `30` trading days (`2026-02-05` to `2026-03-20`): `R$40`, `PF 1.0357`, `DD 4.67%`, `48` trades
  - interpretation: still positive, but clearly softer than the full-sample profile, so Monday should be treated as validation-first.
- Final wrap-up exploration:
  - quarter-adaptive hours were effectively just `10,11,12` all year and came back as a near-tie: `R$14,030`, `PF 1.4889`, `DD 3.41%`
  - month-adaptive hours reached `R$14,355`, `PF 1.5991`, `DD 3.50%`, but that mapping is explicitly in-sample and not safe to promote for Monday
  - a max-daily-profit stop at `2x` active-day mean hurt too much: `R$10,190`, `PF 1.4506`, `DD 3.66%`
- Final patience-entry probe:
  - `30%` pullback within `3` bars: `R$-10,050`, `PF 0.4857`, `DD 100.94%`
  - `40%` pullback within `3` bars: `R$-12,430`, `PF 0.5443`, `DD 125.06%`
  - `50%` pullback within `3` bars: `R$-11,885`, `PF 0.6497`, `DD 119.47%`
  - interpretation: the strategy wants fast continuation entries, not patient pullback entries
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
- Final cost follow-up artifact: `artifacts/outputs/stalker_v10_1_session_cost_followups_20260328/summary.json`
- Final wrap-up artifact: `artifacts/outputs/stalker_v10_1_session_wrapup_followups_20260328/summary.json`
- Final patience artifact: `artifacts/outputs/stalker_v10_1_session_patience_followups_20260328/summary.json`
- Recent 30-day check: `artifacts/outputs/stalker_v10_1_recent_30d_check_20260328/summary.json`
- Frontier note: `docs/research-frontier-2026-03-28.md`
- MT5 playbook: `docs/mt5-paper-trading-playbook-2026-03-28.md`
