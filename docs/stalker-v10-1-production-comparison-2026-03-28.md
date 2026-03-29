# Stalker v10.1 Production Comparison - 2026-03-28

## Side-By-Side

| Variant | Net | PF | DD | Win Rate | Trades | Trades/Day | Sortino | Calmar | Omega | Composite | Rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Strengthened Tier 2A on last 1 contract day, strengthened Tier 3 otherwise, exact research candidate | `R$16,080` | `1.5081` | `3.19%` | `80.94%` | 1595 | `1.2791` | `2.0349` | `6.6967` | `1.6566` | `3.3578` | research exact |
| Strengthened Tier 2A longs + strengthened Tier 3 shorts, research-only directional sleeve | `R$16,075` | `1.5115` | `3.19%` | `80.96%` | 1591 | `1.2759` | `2.0109` | `6.6906` | `1.6533` | `3.3433` | research |
| Equal-weight blend of strengthened Tier 2A + strengthened Tier 3 local-geometry, research-only | `R$15,927.50` | `1.5068` | `3.22%` | `80.90%` | 3168 | `2.5405` | `2.0223` | `6.5957` | `1.6553` | `3.3209` | research |
| Cooldown `25m` + max-hold `150m` + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`, exact research candidate | `R$15,885` | `1.4993` | `3.21%` | `80.84%` | 1597 | `1.2815` | `2.0170` | `6.6019` | `1.6474` | `3.3186` | research exact |
| Cooldown `28m` + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`, exact research candidate | `R$15,970` | `1.5145` | `3.23%` | `80.97%` | 1571 | `1.2606` | `2.0094` | `6.5895` | `1.6541` | `3.3124` | research exact |
| Cooldown `25m` + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`, prior exact research candidate | `R$15,840` | `1.4967` | `3.21%` | `80.84%` | 1597 | `1.2815` | `2.0128` | `6.5886` | `1.6436` | `3.3117` | research exact |
| Cooldown `25m` range mode + Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days, exact research candidate | `R$14,835` | `1.4987` | `3.27%` | `80.70%` | 1611 | `1.2927` | `2.0655` | `6.1735` | `1.6501` | `3.2148` | research exact |
| Cooldown `25m` + conditional `ROC(5)` on prior-day `ADX > 25` trend days, exact research candidate | `R$14,765` | `1.4951` | `3.28%` | `80.70%` | 1611 | `1.2927` | `2.0572` | `6.1294` | `1.6450` | `3.1964` | research exact |
| Cooldown `25m` + max-hold `150m` + `ROC(5)` agreement, exact research candidate | `R$14,630` | `1.4935` | `3.28%` | `80.66%` | 1598 | `1.2815` | `2.0283` | `6.0841` | `1.6412` | `3.1676` | research exact |
| Cooldown `25m` + `ROC(5)` agreement, exact research candidate | `R$14,560` | `1.4900` | `3.30%` | `80.66%` | 1598 | `1.2815` | `2.0201` | `6.0402` | `1.6362` | `3.1493` | research exact |
| Confidence-weighted + time-widened stop overlay, research-only fractional sizing | `R$18,359.32` | `1.4993` | `3.72%` | `80.87%` | 1568 | `1.2574` | `1.8410` | `6.3030` | `1.6315` | `3.1377` | research |
| Equal-weight blend of Tier 2 + Tier 2A, research-only | `R$14,455` | `1.4824` | `3.30%` | `80.58%` | 3213 | `2.5766` | `2.0171` | `6.0079` | `1.6315` | `3.1372` | research |
| Cooldown `25m` + max-hold `150m` | `R$14,420` | `1.4784` | `3.28%` | `80.50%` | 1615 | `1.2951` | `2.0067` | `6.0193` | `1.6245` | `3.1340` | 1 |
| Cooldown `25m` + max-hold `120m` | `R$14,400` | `1.4774` | `3.29%` | `80.50%` | 1615 | `1.2951` | `2.0072` | `6.0068` | `1.6231` | `3.1303` | 2 |
| Confidence-weighted entry overlay, research-only fractional sizing | `R$18,030.27` | `1.4897` | `3.71%` | `80.55%` | 1568 | `1.2574` | `1.8686` | `6.2356` | `1.6255` | `3.1301` | research |
| Cooldown-only, `25m` sweep winner | `R$14,350` | `1.4749` | `3.30%` | `80.50%` | 1615 | `1.2951` | `1.9984` | `5.9756` | `1.6196` | `3.1158` | 3 |
| Equal-weight blend of max-hold + time-widened stop, research-only | `R$14,202.50` | `1.4885` | `3.27%` | `80.55%` | 1568 | `1.2574` | `1.9136` | `5.9735` | `1.6178` | `3.0724` | research |
| Max-hold v2, session winner + `30m` cooldown + `120` M1-bar max hold | `R$14,135` | `1.4851` | `3.29%` | `80.55%` | 1568 | `1.2574` | `1.9392` | `5.9153` | `1.6150` | `3.0672` | 4 |
| Time-widened stop, `0.84 -> 1.20` ATR after `30` bars | `R$14,270` | `1.4887` | `3.28%` | `80.87%` | 1568 | `1.2574` | `1.8816` | `5.9908` | `1.6132` | `3.0607` | 5 |
| Cooldown-only, `40m` runner-up | `R$13,945` | `1.5116` | `3.25%` | `80.85%` | 1483 | `1.1893` | `1.9115` | `5.9292` | `1.6279` | `3.0601` | 6 |
| Minimal moderate, cooldown-only `30m` baseline | `R$14,085` | `1.4825` | `3.30%` | `80.55%` | 1568 | `1.2574` | `1.9306` | `5.8842` | `1.6115` | `3.0529` | 7 |
| Weekly profit cap `R$300`, cooldown + max-hold | `R$14,095` | `1.4937` | `3.32%` | `80.59%` | 1551 | `1.2446` | `1.9354` | `5.8649` | `1.6202` | `3.0512` | 8 |
| Session winner | `R$15,965` | `1.4438` | `4.04%` | `80.17%` | 1896 | `1.5204` | `2.1977` | `5.2628` | `1.6392` | `3.0055` | 9 |
| Baseline, MT5-validated `sl0p84/tp0p30` | `R$14,330` | `1.36` | `3.94%` | `80.29%` | 2070 | `1.9639` | `1.8158` | `5.3480` | `1.5278` | `2.8179` | 10 |
| Cooldown-only + skip last 3 contract days | `R$12,855` | `1.5250` | `3.50%` | `81.12%` | 1345 | `1.0786` | `1.7673` | `5.1990` | `1.6791` | `2.7792` | 11 |
| Session winner `SL 0.60 / TP 0.42` | `R$13,025` | `1.2851` | `4.45%` | `64.89%` | 1891 | `1.5164` | `2.1894` | `4.1227` | `1.4681` | `2.6251` | 12 |
| Wider stop `SL 1.00 / TP 0.30` | `R$13,930` | `1.4556` | `4.07%` | `82.78%` | 1568 | `1.2574` | `1.6194` | `4.7394` | `1.5593` | `2.5434` | 13 |
| Skip Tuesday and Friday, production candidate | `R$9,200` | `1.6261` | `2.97%` | `81.91%` | 846 | `0.6784` | `1.2315` | `4.7450` | `1.7843` | `2.3961` | 14 |
| Wider stop `SL 1.20 / TP 0.30` | `R$14,475` | `1.4626` | `4.43%` | `85.01%` | 1568 | `1.2574` | `1.4260` | `4.4758` | `1.5552` | `2.3668` | 15 |
| Mon/Wed/Thu + time-widened stop | `R$9,500` | `1.6525` | `3.19%` | `82.39%` | 846 | `0.6784` | `1.2099` | `4.5249` | `1.8037` | `2.3232` | 16 |
| Dynamic target `TP 1.00 ATR`, production candidate | `R$17,915` | `1.2569` | `6.13%` | `51.78%` | 1541 | `1.2358` | `1.8177` | `3.7590` | `1.3818` | `2.3129` | 17 |
| ADX quality mode, prior-day `ADX > 25` | `R$7,485` | `1.9067` | `3.38%` | `84.29%` | 490 | `0.3929` | `1.0426` | `3.5353` | `2.2131` | `2.0245` | 18 |
| Strong-signal gate, top half of executed trend-efficiency | `R$8,555` | `1.4047` | `4.72%` | `79.28%` | 1062 | `0.8516` | `1.1275` | `2.8194` | `1.4699` | `1.7035` | 19 |
| Session winner `SL 0.50 / TP 0.50` | `R$8,480` | `1.1711` | `6.46%` | `54.05%` | 1887 | `1.5132` | `1.3330` | `2.0449` | `1.2940` | `1.5388` | 20 |
| Skip Tuesday and Friday + top-half signal gate | `R$5,460` | `1.4979` | `3.28%` | `80.07%` | 577 | `0.4627` | `0.7092` | `2.8060` | `1.5699` | `1.5104` | 21 |
| Strong-signal gate, top quartile of executed trend-efficiency | `R$5,570` | `1.4829` | `4.61%` | `79.34%` | 605 | `0.4852` | `0.7538` | `2.0293` | `1.5198` | `1.2896` | 22 |
| ADX quality mode, prior-day `ADX > 30` | `R$3,515` | `1.6356` | `4.35%` | `82.37%` | 278 | `0.2230` | `0.4607` | `1.4419` | `1.8573` | `1.0344` | 23 |
| Hot-hand gate, last `10` trades PnL > `0` | `R$630` | `1.9921` | `1.85%` | `84.38%` | 32 | `0.0257` | `0.1002` | `0.6727` | `2.5750` | `0.7669` | 24 |

## Quality Alternative

| Variant | Net | PF | DD | Win Rate | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Maximum Quality v2 | `R$10,665` | `1.4492` | `3.78%` | `80.16%` | 1255 |

## Readout

- Safest paper-trading choice today: the MT5-validated base preset.
- Best exact research candidate overall: session winner + `25m` cooldown + `150m` max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`.
- Strongest regime-aware exact research candidate now packaged for MT5 follow-up:
  - session winner + `25m` cooldown, using plain Tier 2 on range days and switching to Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days
  - `R$14,835`, `PF 1.4987`, `DD 3.27%`, composite `3.2148`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5407`
    - test `PF 1.3935`
  - recent `60`-trading-day check stayed soft:
    - `R$30`, `PF 1.0157`, `DD 5.62%`
  - unlike the strengthened always-on Tier 2A and Tier 3 local-geometry lines, it did not stay positive on the recent `60`-day readout
  - this is still not the Monday default because it adds both regime and max-hold logic
- Strongest exact research line overall:
  - strengthened Tier 2A on the last `1` contract day, strengthened Tier 3 on all other days
  - `R$16,080`, `PF 1.5081`, `DD 3.19%`, composite `3.3578`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5369`
    - test `PF 1.4350`
  - recent `60`-trading-day check stayed positive:
    - `R$480`, `PF 1.2783`, `DD 3.23%`
  - corrected cutoff sweep confirmed `last 1` contract day is best:
    - `1d`: composite `3.3578`
    - `2d` and `3d`: composite `3.3430`
    - `5d`: composite `3.3295`
  - this is still a research-only branch because the contract-cycle switching rule is not yet part of the Monday MT5 deployment path
- Strongest static research-only sleeve:
  - strengthened Tier 2A longs plus strengthened Tier 3 shorts
  - `R$16,075`, `PF 1.5115`, `DD 3.19%`, composite `3.3433`
  - `70/30` test stayed positive:
    - train `PF 1.5385`
    - test `PF 1.4424`
  - recent `60`-day slice also stayed positive:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
  - this is still research-only because it needs direction-specific sleeve routing rather than one static preset
- Strongest simpler post-Monday follow-up now packaged for MQ5:
  - session winner + `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,970`, `PF 1.5145`, `DD 3.23%`, composite `3.3124`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5403`
    - test `PF 1.4489`
  - recent `60`-trading-day check stayed positive:
    - `R$435`, `PF 1.2522`, `DD 3.25%`
  - this is now the strongest exact post-Tier-2 line, but it still waits on host-side MT5 validation before it changes the Monday rollout order
- Strongest aggressive post-Monday follow-up now packaged for MQ5:
  - session winner + `25m` cooldown + `150m` max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5258`
    - test `PF 1.4316`
  - recent `60`-trading-day check stayed positive:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
  - this is now the strongest aggressive exact research line, but it should still come after the simpler Tier 2A path operationally
- New best exact post-Tier-2 upgrade:
  - session winner + `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,970`, `PF 1.5145`, `DD 3.23%`, composite `3.3124`
  - exact `70/30` walk-forward:
    - train `PF 1.5403`
    - test `PF 1.4489`
  - recent `60`-trading-day check stayed positive:
    - `R$435`, `PF 1.2522`, `DD 3.25%`
  - this is now the cleanest stronger post-Tier-2 research validation target, and it beat the earlier `25m` ROC geometry variant on full sample and holdout
- Best max-hold ROC research candidate:
  - session winner + `25m` cooldown + `150` M1 max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5258`
    - test `PF 1.4316`
  - recent `60`-trading-day check stayed positive:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
- Simpler ROC agreement alternative:
  - session winner + `25m` cooldown + `ROC(5)` agreement
  - `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493`
  - exact `70/30` walk-forward still passed:
    - train `PF 1.5272`
    - test `PF 1.4086`
  - recent `60`-trading-day check stayed soft but stable:
    - `R$30`, `PF 1.0157`, `DD 5.62%`
  - this is now the clearest simpler ROC-based host-side MT5 validation target
- Best exact cooldown sweep winner: session winner + `25m` cooldown only.
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
  - this is now the best deployable exact cooldown-only composite score in the full-sample sweep
  - it slightly beats the old `30m` cooldown line, but not the new `25m + 150m` max-hold leader
- Simplest holdout-validated fallback: session winner + `30m` cooldown only.
  - `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - that retains `97.68%` of the new `150m` max-hold leader's net profit and `100.28%` of its PF
  - it matched the max-hold stack exactly in the recent weak 30-day tape
  - the exact `70/30` walk-forward also passed:
    - train `PF 1.5295`
    - test `PF 1.3668`
- Recommended configuration tiers:
  - Tier 1, safest: MT5-validated `sl0p84 / tp0p30`
  - Tier 2, moderate: session winner + `25m` cooldown only
  - Tier 2A, next research validation: session winner + `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - secondary research branches after Tier 3: regime-aware ROC and advanced regime-aware ROC + max-hold
  - Tier 3, aggressive: session winner + `25m` cooldown + `150m` max-hold + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
  - Tier 4, research-only: equal-weight blend of Tier 2 and Tier 2A
- Risk-adjusted ranking by the Sortino-weighted composite:
  - strongest exact research line overall: strengthened Tier 2A on the last `1` contract day and strengthened Tier 3 otherwise at `3.3578`
- strongest research-only sleeve: strengthened Tier 2A longs plus strengthened Tier 3 shorts at `3.3433`
- next strongest research-only sleeve: equal-weight blend of strengthened Tier 2A and strengthened Tier 3 local-geometry at `3.3209`
  - best exact research line: cooldown `25m` + max-hold `150m` + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2` at `3.3186`
  - next exact research line: cooldown `28m` + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2` at `3.3124`
  - next exact research line: cooldown `25m` range mode + Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days at `3.2148`
  - next exact research line: cooldown `25m` + conditional `ROC(5)` on prior-day `ADX > 25` trend days at `3.1964`
  - next exact research line: cooldown `25m` + `ROC(5)` agreement at `3.1493`
  - research-only leader: confidence overlay + time-widened stop at `3.1377`
  - next research-only: equal-weight blend of Tier 2 and Tier 2A at `3.1372`
  - 1: cooldown `25m` + max-hold `150m` at `3.1340`
  - 2: cooldown `25m` + max-hold `120m` at `3.1303`
  - next research-only: confidence overlay at `3.1301`
  - 3: cooldown-only `25m` at `3.1158`
  - next research-only: equal-weight blend of max-hold + time-widened stop at `3.0724`
  - 4: max-hold v2 at `3.0672`
  - 5: time-widened stop at `3.0607`
  - 6: cooldown-only `40m` at `3.0601`
  - 7: cooldown-only `30m` at `3.0529`
  - 8: weekly cap `R$300` at `3.0512`
  - 9: session winner at `3.0055`
  - 10: MT5-validated base at `2.8179`
  - 11: cooldown-only + skip last 3 contract days at `2.7792`
- Spread-tolerance ranking:
  - main deployable break-even integer spread is `2` ticks for both Tier 2 and Tier 3
  - Tier 2 at `2` ticks: `R$4,700`, `PF 1.1320`, `DD 9.87%`
- Tier 3 at `2` ticks: `R$4,735`, `PF 1.1287`, `DD 9.78%`
  - both are negative at `3` ticks
  - only the wider `TP 0.48` cooldown variant stayed barely positive at `3` ticks:
    - `R$215`, `PF 1.0040`, `DD 25.14%`
  - adding max-hold to that same `TP 0.48` hostile-spread fallback helped only slightly:
    - `R$415`, `PF 1.0078`, `DD 24.72%`, composite `0.2378`
  - interpretation: `TP 0.48` is a spread-resilient research tier, not a production promotion
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
- Confidence-weighted overlay plus time-widened stop:
  - this became the single best composite-scoring result of the whole sprint:
    - `R$18,359.32`, `PF 1.4993`, `DD 3.72%`, `Composite 3.1377`
  - interpretation: the tiny exact quality gain from the time-widened stop survives the confidence-weighted overlay and nudges the research frontier slightly higher
  - deployment caveat: still research-only because the sizing layer is fractional and not yet mirrored in MQ5
- Simple equal-weight ensemble of the top two exact strategies:
  - blending the max-hold leader and the time-widened stop `50/50` slightly beat the best single exact strategy:
    - `R$14,202.50`, `PF 1.4885`, `DD 3.27%`, `Composite 3.0724`
  - interpretation: the single-strategy frontier is probably close to its ceiling, but portfolio-level smoothing can still squeeze out a tiny risk-adjusted improvement
  - deployment caveat: this is not Monday’s default because it assumes running two nearly identical exact variants side by side and averaging the risk
- New portfolio blend follow-up:
  - equal-weight blend of Tier 2 and Tier 2A:
    - `R$14,455`, `PF 1.4824`, `DD 3.30%`, `Composite 3.1372`
  - walk-forward test:
    - train `R$11,147.50`, `PF 1.5204`, `Composite 3.6141`
    - test `R$3,307.50`, `PF 1.3871`, `Composite 2.6224`
  - contract-month behavior:
    - Tier 2A beat Tier 2 in `9` of `61` contract months
    - the equal-weight blend beat both in `0` of `61`
  - interpretation: it is the cleanest research-only portfolio smoother, but not strong enough to change the live upgrade order
  - documentation label: Tier 4, Research Blend
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
  - Monday/Wednesday/Thursday plus the time-widened stop also stayed secondary:
    - `R$9,500`, `PF 1.6525`, `DD 3.19%`, `Composite 2.3232`
- Final stop-management follow-up:
  - time-widened stop (`0.84 -> 1.20` ATR after `30` bars) was the only true headline-metric improvement over max-hold:
    - `R$14,270`, `PF 1.4887`, `DD 3.28%`, `WR 80.87%`
  - but its Sortino-weighted composite slipped slightly below max-hold, `3.0607` vs `3.0672`
  - interpretation: it is a credible future MT5 validation candidate, but not strong enough to replace the simpler exact ranking winner
- ATR trailing-stop follow-up:
  - `1.0x` ATR trailing was slightly worse than the reference:
    - `R$13,910`, `PF 1.4755`, `DD 3.28%`, `Composite 3.0357`
  - `1.5x` and `2.0x` ATR trailing were exact ties with the current leader:
    - `R$14,135`, `PF 1.4851`, `DD 3.29%`, `Composite 3.0672`
  - interpretation: there is no reason to spend more optimization budget on plain ATR trailing multiples right now
- Dynamic ATR target follow-up:
  - replacing the fixed `0.30 ATR` target with `1.00 ATR` raised gross net but hurt quality too much:
    - `R$17,915`, `PF 1.2569`, `DD 6.13%`, `Composite 2.3129`
  - interpretation: wider volatility-scaled targets are not the right risk-adjusted direction for the production candidate
- ML signal-overlay follow-up:
  - logistic next-bar model had mild directional skill (`AUC 0.5987`) and the random forest was weaker (`AUC 0.5607`)
  - but none of the ML trade overlays helped the strategy:
    - logistic gate `0.55`: `R$-115`, `Composite 0.1120`
    - logistic overlay: `R$5,364.21`, `Composite 2.0685`
    - simple-core logistic overlay: `R$5,270.14`, `Composite 2.1251`
    - random-forest overlay: `R$5,273.39`, `Composite 2.1265`
  - interpretation: there is a little predictive signal in the features, but not enough to improve the current strategy once it is translated into a tradable overlay
- Latest live-tape check:
  - last `10` trading days (`2026-03-09` to `2026-03-20`) were strong for the production candidate:
    - `R$455`, `PF 4.25`, `DD 0.81%`, `16` trades
  - interpretation: the soft `30`-day window was real, but the most recent `10` days recovered sharply
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
- Fixed `5`-tick spread stress:
  - a true fixed `5`-tick spread environment was catastrophic for the exact leader:
    - `R$-16,975`, `PF 0.6614`, `DD 168.02%`, `Composite -0.9242`
  - interpretation: if live WDO spread behaves like a persistent `5`-tick tape, the strategy should be considered off rather than merely "degraded"
- Contract-month robustness:
  - the exact leader was positive in `47` of `61` contract months, or `77.05%`
  - best contract by net: `2022-05`, `R$1,000`, `PF 2.60`
  - worst contract by net: `2022-10`, `R$-275`, `PF 0.7511`
  - recent path: `2026-01` and `2026-02` were weak, while `2026-03` recovered to `R$225`, `PF 1.4545`
  - interpretation: robustness across contracts is real, but weak contract months do happen and line up with the same range-bound episodes already flagged by the regime analysis
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
- Live spread-guard follow-up:
  - the new optional `1`-tick spread guard does not change historical results because the cached entry spread distribution was:
    - `0` tick: `5` trades
    - `1` tick: `1563` trades
  - all `305` historical losing trades also entered at `1` tick simply because the tape never exceeded `1`
  - interpretation: the spread guard is still worth having, but as a live risk-control rail rather than a backtest enhancer
- Monday-readiness follow-up:
  - last `5` trading days (`2026-03-16` to `2026-03-20`) were solid for both Tier 2 and Tier 3:
    - `R$110`, `PF 1.7857`, `DD 0.84%`, `7` trades
  - first-trade-of-day restriction underperformed badly:
    - `R$8,600`, `PF 1.4531`, `DD 3.82%`, composite `1.8909`
  - EMA50 direction filter was an exact tie with Tier 2:
    - `R$14,085`, `PF 1.4825`, `DD 3.30%`, composite `3.0529`
  - ATR-expansion volatility breakout was too restrictive and produced `0` trades
  - interpretation: the current signal family still looks mature; the latest tape improved, but the new filters did not beat the existing tiers
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
- if you want the strongest exact risk-adjusted refinement, Tier 3 still wins by a hair, and `150m` is now the best max-hold duration
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
