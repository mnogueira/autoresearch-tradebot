# Stalker v10.1 Production Comparison - 2026-03-28

## Side-By-Side

| Variant | Net | PF | DD | Win Rate | Trades | Trades/Day | Sortino | Calmar | Omega | Composite | Rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confidence-weighted entry overlay, research-only fractional sizing | `R$18,030.27` | `1.4897` | `3.71%` | `80.55%` | 1568 | `1.2574` | `1.8686` | `6.2356` | `1.6255` | `3.1301` | research |
| Max-hold v2, session winner + cooldown + `120` M1-bar max hold | `R$14,135` | `1.4851` | `3.29%` | `80.55%` | 1568 | `1.2574` | `1.9392` | `5.9153` | `1.6150` | `3.0672` | 1 |
| Time-widened stop, `0.84 -> 1.20` ATR after `30` bars | `R$14,270` | `1.4887` | `3.28%` | `80.87%` | 1568 | `1.2574` | `1.8816` | `5.9908` | `1.6132` | `3.0607` | 2 |
| Minimal moderate, session winner + cooldown | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | 1568 | `1.2574` | `1.9306` | `5.8842` | `1.6115` | `3.0529` | 3 |
| Weekly profit cap `R$300`, cooldown + max-hold | `R$14,095` | `1.4937` | `3.32%` | `80.59%` | 1551 | `1.2446` | `1.9354` | `5.8649` | `1.6202` | `3.0512` | 4 |
| Session winner | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | 1896 | `1.5204` | `2.1977` | `5.2628` | `1.6392` | `3.0055` | 5 |
| Baseline, MT5-validated `sl0p84/tp0p30` | `R$14,330` | `1.36` | `3.94%` | `80.29%` | 2070 | `1.9639` | `1.8158` | `5.3480` | `1.5278` | `2.8179` | 6 |
| Cooldown-only + skip last 3 contract days | `R$12,855` | `1.5250` | `3.50%` | `81.12%` | 1345 | `1.0786` | `1.7673` | `5.1990` | `1.6791` | `2.7792` | 7 |
| Session winner `SL 0.60 / TP 0.42` | `R$13,025` | `1.2851` | `4.45%` | `64.89%` | 1891 | `1.5164` | `2.1894` | `4.1227` | `1.4681` | `2.6251` | 8 |
| Wider stop `SL 1.00 / TP 0.30` | `R$13,930` | `1.4556` | `4.07%` | `82.78%` | 1568 | `1.2574` | `1.6194` | `4.7394` | `1.5593` | `2.5434` | 9 |
| Skip Tuesday and Friday, production candidate | `R$9,200` | `1.6261` | `2.97%` | `81.91%` | 846 | `0.6784` | `1.2315` | `4.7450` | `1.7843` | `2.3961` | 10 |
| Wider stop `SL 1.20 / TP 0.30` | `R$14,475` | `1.4626` | `4.43%` | `85.01%` | 1568 | `1.2574` | `1.4260` | `4.4758` | `1.5552` | `2.3668` | 11 |
| ADX quality mode, prior-day `ADX > 25` | `R$7,485` | `1.9067` | `3.38%` | `84.29%` | 490 | `0.3929` | `1.0426` | `3.5353` | `2.2131` | `2.0245` | 12 |
| Strong-signal gate, top half of executed trend-efficiency | `R$8,555` | `1.4047` | `4.72%` | `79.28%` | 1062 | `0.8516` | `1.1275` | `2.8194` | `1.4699` | `1.7035` | 13 |
| Session winner `SL 0.50 / TP 0.50` | `R$8,480` | `1.1711` | `6.46%` | `54.05%` | 1887 | `1.5132` | `1.3330` | `2.0449` | `1.2940` | `1.5388` | 14 |
| Skip Tuesday and Friday + top-half signal gate | `R$5,460` | `1.4979` | `3.28%` | `80.07%` | 577 | `0.4627` | `0.7092` | `2.8060` | `1.5699` | `1.5104` | 15 |
| Strong-signal gate, top quartile of executed trend-efficiency | `R$5,570` | `1.4829` | `4.61%` | `79.34%` | 605 | `0.4852` | `0.7538` | `2.0293` | `1.5198` | `1.2896` | 16 |
| ADX quality mode, prior-day `ADX > 30` | `R$3,515` | `1.6356` | `4.35%` | `82.37%` | 278 | `0.2230` | `0.4607` | `1.4419` | `1.8573` | `1.0344` | 17 |
| Hot-hand gate, last `10` trades PnL > `0` | `R$630` | `1.9921` | `1.85%` | `84.38%` | 32 | `0.0257` | `0.1002` | `0.6727` | `2.5750` | `0.7669` | 18 |

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
  - the exact `70/30` walk-forward also passed:
    - train `PF 1.5295`
    - test `PF 1.3668`
- Recommended configuration tiers:
  - Tier 1, safest: MT5-validated `sl0p84 / tp0p30`
  - Tier 2, moderate: session winner + `30m` cooldown only
  - Tier 3, aggressive: session winner + `30m` cooldown + `120` M1 max hold
- Risk-adjusted ranking by the Sortino-weighted composite:
  - 1: max-hold v2 at `3.0672`
  - 2: time-widened stop at `3.0607`
  - 3: cooldown-only at `3.0529`
  - 4: weekly cap `R$300` at `3.0512`
  - 5: session winner at `3.0055`
  - 6: MT5-validated base at `2.8179`
  - 7: cooldown-only + skip last 3 contract days at `2.7792`
- Sortino target follow-up:
  - no live-ready exact variant broke `Sortino 2.5` while keeping `DD < 5%`
  - the closest exact candidate was the plain session winner with `SL 0.60 / TP 0.42`:
    - `Sortino 2.1894`, `DD 4.45%`, composite `2.6251`
    - but its `PF 1.2851` and `WR 64.89%` were too weak to promote
  - the alternate `SL 0.50 / TP 0.50` ratio was clearly worse:
    - `R$8,480`, `PF 1.1711`, `DD 6.46%`, `Sortino 1.3330`
- Confidence-weighted entry sizing:
  - research-only fractional sizing by absolute trend-efficiency produced the strongest raw composite score in the entire sprint:
    - `R$18,030.27`, `PF 1.4897`, `DD 3.71%`, `Composite 3.1301`
  - interpretation: stronger signals do appear to deserve more size
  - deployment caveat: this is not a real 1-contract MT5 preset, so it is evidence for future discrete sizing research, not a Monday recommendation
- Binary strong-signal gate:
  - top-half absolute trend-efficiency gate already hurt badly:
    - `R$8,555`, `PF 1.4047`, `DD 4.72%`, `Composite 1.7035`
  - top-quartile absolute trend-efficiency over-throttled the production candidate:
    - `R$5,570`, `PF 1.4829`, `DD 4.61%`, `Composite 1.2896`
  - interpretation: the edge wants graded confidence sizing more than a hard yes/no strength gate
- Weekday decomposition:
  - strongest weekdays:
    - Monday: `R$3,835`, `PF 1.7050`, `DD 2.81%`
    - Wednesday: `R$2,175`, `PF 1.8597`, `DD 1.85%`
  - weakest weekdays:
    - Tuesday: `R$2,430`, `PF 1.3535`, `DD 4.93%`
    - Friday: `R$2,505`, `PF 1.3309`, `DD 4.99%`
  - skipping Tuesday and Friday improved PF and DD, but still lost too much net:
    - `R$9,200`, `PF 1.6261`, `DD 2.97%`, `Composite 2.3961`
  - interpretation: Tuesday and Friday are watchlist days, not default hard-skip days
  - combining the weekday skip with the top-half signal gate was worse than either idea alone:
    - `R$5,460`, `PF 1.4979`, `DD 3.28%`, `Composite 1.5104`
- Final stop-management follow-up:
  - time-widened stop (`0.84 -> 1.20` ATR after `30` bars) was the only true headline-metric improvement over max-hold:
    - `R$14,270`, `PF 1.4887`, `DD 3.28%`, `WR 80.87%`
  - but its Sortino-weighted composite slipped slightly below max-hold, `3.0607` vs `3.0672`
  - interpretation: it is a credible future MT5 validation candidate, but not strong enough to replace the simpler exact ranking winner
- Market-close avoidance and weekly caps:
  - closing `30` minutes before market close was an exact no-op on this setup
  - a weekly profit cap at `R$300` per contract slightly improved PF and rolling trade smoothness, but it gave up just enough net and Calmar to stay below the main winners
  - a weekly cap at `R$500` was also a no-op
- Hot-hand follow-up:
  - requiring the last `10` closed trades to sum to a positive PnL over-throttled the system badly:
    - `32` trades, `R$630`, composite `0.7669`
  - interpretation: this strategy does not want a “trade only when already hot” overlay
- ADX quality-mode follow-up on the same composite:
  - cooldown-only: `3.0529`
  - MT5 Tier 1 base: `2.8179`
  - prior-day daily `ADX > 25` quality mode: `2.0245`
  - interpretation: `ADX > 25` is a quality niche, not a better default than the base or Tier 2 once the trade loss is priced in.
- Requested top-3 professional-metric evaluation:
  - max-hold v2 beat the session winner and MT5 base on composite score
  - the session winner still had the best raw Sortino at `2.1977`
  - the max-hold and cooldown overlays won on composite because their Calmar and Omega stayed stronger while drawdown stayed lower
  - the tie-breaker between cooldown-only and max-hold is stability, not composite:
    - both had the same worst month at `R$-275` in `2022-10`
    - both had the same max consecutive losing-day streak of `5`
    - cooldown-only had the slightly lower monthly PnL variance, `78,356.97` vs `78,404.00`
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
- Rolling `20`-trade Sharpe smoothing:
  - weekly cap `R$300`: median `0.7457`, positive windows `78.85%`
  - session winner: median `0.7450`, positive windows `76.82%`
  - max-hold v2: median `0.7390`, positive windows `78.76%`
  - cooldown-only: median `0.7365`, positive windows `78.57%`
  - time-widened stop: median `0.7240`, positive windows `77.15%`
  - MT5 Tier 1 base: median `0.5254`, positive windows `67.14%`
  - interpretation: the capped and exact-filtered variants are noticeably smoother trade-to-trade than the raw MT5 base, but weekly cap `R$300` is still not enough of a total-package improvement to become the default
- Pareto check against the broader exact leaderboard:
  - no exact candidate improved `net profit`, `profit factor`, `drawdown`, and `win rate` simultaneously versus the max-hold leader
  - interpretation: there is no true all-metrics winner hiding elsewhere in the research set

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

## Final Recommendation

- Monday:
  - run Tier 1, the MT5-validated base preset
- Next week, if the first `5` paper sessions are clean:
  - upgrade to Tier 2, the cooldown-only refinement
  - this is the best balance of simplicity, stability, and near-maximum composite score
- Later, only after another week of clean paper behavior:
  - test Tier 3, the cooldown + max-hold refinement
  - save the rollover skip as a discretionary caution rule, not a preset default

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
