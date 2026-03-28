# Stalker v10.1 Production Comparison - 2026-03-28

## Side-By-Side

| Variant | Net | PF | DD | Win Rate | Trades | Sortino | Calmar | Omega | Composite | Rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline, MT5-validated `sl0p84/tp0p30` | `R$14,330` | `1.36` | `3.94%` | `80.29%` | 2070 | `1.8158` | `5.3480` | `1.5278` | `2.8179` | 4 |
| Session winner | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | 1896 | `2.1977` | `5.2628` | `1.6392` | `3.0055` | 3 |
| Minimal moderate, session winner + cooldown | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | 1568 | `1.9306` | `5.8842` | `1.6115` | `3.0529` | 2 |
| Max-hold v2, session winner + cooldown + `120` M1-bar max hold | `R$14,135` | `1.4851` | `3.29%` | `80.55%` | 1568 | `1.9392` | `5.9153` | `1.6150` | `3.0672` | 1 |
| Cooldown-only + skip last 3 contract days | `R$12,855` | `1.5250` | `3.50%` | `81.12%` | 1345 | `1.7673` | `5.1990` | `1.6791` | `2.7792` | 5 |

## Quality Alternative

| Variant | Net | PF | DD | Win Rate | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Maximum Quality v2 | `R$10,665` | `1.4492` | `3.78%` | `80.16%` | 1255 |

## Readout

- Safest paper-trading choice today: the MT5-validated base preset.
- Best exact research candidate: session winner + `30m` cooldown + `120` M1-bar max hold.
- Simplest high-fidelity fallback: session winner + `30m` cooldown only.
  - `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - that retains `99.65%` of the max-hold leader's net profit and `99.82%` of its PF
  - for Monday, this is the better exact refinement than Tier 3:
    - the composite gap vs max-hold is only `0.0143`
    - it matched the max-hold stack exactly in the recent weak 30-day tape
    - it is operationally simpler
- Recommended configuration tiers:
  - Tier 1, safest: MT5-validated `sl0p84 / tp0p30`
  - Tier 2, moderate: session winner + `30m` cooldown only
  - Tier 3, aggressive: session winner + `30m` cooldown + `120` M1 max hold
- Risk-adjusted ranking by the Sortino-weighted composite:
  - 1: max-hold v2 at `3.0672`
  - 2: cooldown-only at `3.0529`
  - 3: session winner at `3.0055`
  - 4: MT5-validated base at `2.8179`
  - 5: cooldown-only + skip last 3 contract days at `2.7792`
- Requested top-3 professional-metric evaluation:
  - max-hold v2 beat the session winner and MT5 base on composite score
  - the session winner still had the best raw Sortino at `2.1977`
  - the max-hold and cooldown overlays won on composite because their Calmar and Omega stayed stronger while drawdown stayed lower
- Best quality-biased operator preset: Maximum Quality v2.
- Rollover filter follow-up:
  - cooldown-only + skip last 3 contract days improved PF to `1.5250` and win rate to `81.12%`
  - but net fell to `R$12,855` and the composite score dropped to `2.7792`
  - interpretation: rollover caution belongs in the playbook, but the hard skip is not strong enough to become the main production configuration
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
- Recent-softness diagnosis:
  - trades per day increased from `1.26` to `1.60`, so this was not caused by a lack of signals
  - the recent issue was weaker signal quality: win rate dropped from `80.55%` to `75.00%`, and average profit per trade dropped from `R$9.01` to `R$0.83`
  - prior-day daily `ADX(14) > 25` only `16.67%` of the time recently versus `31.57%` over the full sample
  - session-only recent run: `R$145`, `PF 1.1111`, `DD 3.37%`
  - session + cooldown only recent run: `R$40`, `PF 1.0357`, `DD 4.67%`
  - session + cooldown + max-hold recent run: `R$40`, `PF 1.0357`, `DD 4.67%`
  - interpretation: the recent month looked more range-bound, and the max-hold layer added nothing on top of the cooldown in that weak tape
- Regime breakdown for the production candidate:
  - trend days (`prior-day ADX > 25`): session + cooldown + max-hold = `R$7,535`, `PF 1.9183`, `DD 3.38%`
  - range days (`prior-day ADX <= 25`): session + cooldown + max-hold = `R$6,600`, `PF 1.3153`, `DD 4.95%`
  - interpretation: the strategy stays positive in both tapes, but trend days clearly drive the cleaner edge
- 2025 half-split stability:
  - first half of `2025`: `R$1,555`, `PF 1.5604`, `DD 2.96%`
  - second half of `2025`: `R$655`, `PF 1.2652`, `DD 3.02%`
  - prior-day `ADX > 25` share fell from `13.93%` to `3.91%`
  - interpretation: the weaker half-year also looked less trending, which fits the regime analysis
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
- Risk-budget takeaway:
  - `1` contract per `R$100k` is the right Monday maximum if you want the harsh `3x` spread stress case to stay near a `5%` capital drawdown budget
- Rolling degradation profile:
  - trailing `60`-day PF median: `1.4119`
  - trailing `60`-day PF minimum: `0.8408`
  - share of `60`-day windows below `1.0`: `4.46%`
  - longest underwater stretch: `69` trading days

## Risk-Adjusted Evaluation

- For this WDO intraday strategy, Calmar matters most operationally, even though the composite is Sortino-weighted.
  - Reason: Monday deployment risk is dominated by drawdown tolerance and staying alive through soft tapes, not by squeezing the last bit of upside from already-positive days.
- Sortino is still the best research ranking metric for idea discovery.
  - It rewards upside while penalizing only harmful downside volatility, which is a better fit than plain Sharpe for this asymmetric intraday payoff profile.
- Omega is the sanity-check metric.
  - It confirms whether the overall daily return distribution still has more good mass than bad mass around a `0%` threshold.
- Practical interpretation:
  - if you want the safest live-paper default, keep Tier 1 because it is MT5-validated
  - if you want the strongest exact risk-adjusted refinement, Tier 3 still wins by a hair
  - if you care about Monday deployment quality, Tier 2 is the better choice because it is simpler and the composite gap is trivial

## Methodology

- Daily PnL was normalized to a `R$10,000` starting equity to match the repo's drawdown convention.
- Sortino = annualized mean daily return divided by downside RMS of negative daily returns.
- Calmar = CAGR divided by maximum drawdown fraction.
- Omega = sum of positive daily returns divided by absolute sum of negative daily returns, threshold `0%`.
- Composite = `0.50 * Sortino + 0.30 * Calmar + 0.20 * Omega`.
- The MT5 base uses the actual Every Tick HTML deals ledger, aggregated to daily PnL.
- The exact variants use the exact every-tick engine trade ledger, aggregated to daily PnL.

## Files

- Validated MT5 artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
- Exact max-hold artifact: `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
- Risk-adjusted evaluation artifact: `artifacts/outputs/stalker_v10_1_risk_adjusted_evaluation_20260328/summary.json`
- Final cost follow-up artifact: `artifacts/outputs/stalker_v10_1_session_cost_followups_20260328/summary.json`
- Final wrap-up artifact: `artifacts/outputs/stalker_v10_1_session_wrapup_followups_20260328/summary.json`
- Final patience artifact: `artifacts/outputs/stalker_v10_1_session_patience_followups_20260328/summary.json`
- Recent 30-day check: `artifacts/outputs/stalker_v10_1_recent_30d_check_20260328/summary.json`
- Recent softness analysis: `artifacts/outputs/stalker_v10_1_recent_softness_analysis_20260328/summary.json`
- Frontier note: `docs/research-frontier-2026-03-28.md`
- MT5 playbook: `docs/mt5-paper-trading-playbook-2026-03-28.md`
- Recent tiers follow-up: `artifacts/outputs/stalker_v10_1_recent_tiers_followup_20260328/summary.json`
