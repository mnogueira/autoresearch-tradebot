# Research Frontier - 2026-03-28

## Current Production Leader

- Validated MT5 Every Tick leader:
  - `WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4`
  - artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
  - metrics: `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`

This remains the safest paper-trading candidate because it is the best strategy validated in MT5 `Every tick` mode.

## Final Ranking Follow-up

- No live-ready exact variant broke the target of `Sortino > 2.5` while keeping `DD < 5%`.
- The closest exact ratio variant was the plain session winner at `SL 0.60 / TP 0.42`:
  - `R$13,025`, `PF 1.2851`, `DD 4.45%`, `Sortino 2.1894`
  - interpretation: better downside-adjusted return than many variants, but too weak on PF and win rate to promote
- The stricter 1:1 ratio variant was worse:
  - session winner `SL 0.50 / TP 0.50`: `R$8,480`, `PF 1.1711`, `DD 6.46%`, `Sortino 1.3330`
- A research-only confidence-weighted sizing overlay was the strongest raw risk-adjusted result of the whole sprint:
  - `R$18,030.27`, `PF 1.4897`, `DD 3.71%`, `Composite 3.1301`
  - interpretation: stronger trend-efficiency signals likely deserve more size
  - caveat: this is not deployable yet because it assumes fractional position scaling rather than a discrete MT5 contract-sizing rule
- Turning that same idea into a hard binary gate failed:
  - top-half executed trend-efficiency gate: `R$8,555`, `PF 1.4047`, `DD 4.72%`, composite `1.7035`
  - top-quartile trend-efficiency only: `R$5,570`, `PF 1.4829`, `DD 4.61%`, `Composite 1.2896`
  - interpretation: the signal seems to want graded sizing, not a strong/weak cutoff
- Weekday follow-up on the production candidate:
  - Monday and Wednesday were strongest
  - Tuesday and Friday were weakest
  - skipping Tuesday and Friday improved PF and DD, but still gave up too much net to become a default rule
  - combining the weekday skip with the top-half signal gate also failed to justify itself: `R$5,460`, composite `1.5104`
- Final trailing-stop and target follow-up on the production candidate:
  - ATR trailing `1.0x` slightly hurt: `R$13,910`, `PF 1.4755`, `DD 3.28%`, composite `3.0357`
  - ATR trailing `1.5x` and `2.0x` were exact ties with the current leader
  - dynamic `TP 1.00x ATR` raised gross net to `R$17,915`, but quality broke down: `PF 1.2569`, `DD 6.13%`, composite `2.3129`
  - Monday/Wednesday/Thursday only stayed secondary even with the time-widened stop: `R$9,500`, `PF 1.6525`, `DD 3.19%`, composite `2.3232`
  - interpretation: plain ATR trailing and a wider ATR target do not improve the deployable frontier enough to justify more tuning right now
- Final maximum-quality composite pass:
  - adding the confidence-weighted research overlay on top of the time-widened stop produced the strongest raw composite of the whole sprint:
    - `R$18,359.32`, `PF 1.4993`, `DD 3.72%`, composite `3.1377`
  - a simpler research-only equal-weight blend of the top two exact strategies also nudged past the best single exact variant:
    - `R$14,202.50`, `PF 1.4885`, `DD 3.27%`, composite `3.0724`
  - documentation label for that blend:
    - Tier 4, Research Blend
  - the `70/30` walk-forward stayed positive:
    - train `R$14,407.44`, `PF 1.5535`, `Composite 3.7167`
    - test `R$3,951.88`, `PF 1.3681`, `Composite 2.3270`
  - interpretation: there is still some research-only upside in graded sizing and portfolio smoothing, but the live deployable frontier is still anchored by the simpler exact tiers
- ML signal-overlay follow-up:
  - out-of-fold logistic next-bar classifier: `AUC 0.5987`, accuracy `0.8177`
  - out-of-fold random forest: `AUC 0.5607`, accuracy `0.8238`
  - strategy translation failed:
    - logistic gate `0.55`: `R$-115`, composite `0.1120`
    - logistic overlay: `R$5,364.21`, composite `2.0685`
    - core-feature logistic overlay: `R$5,270.14`, composite `2.1251`
    - random-forest overlay: `R$5,273.39`, composite `2.1265`
  - interpretation: the current signal family is probably close to its ceiling on this data; there is some directional information in the features, but not enough to improve the existing strategy once costs and path dependence are respected

## Near-Term Caution

- The exact max-hold leader stayed positive over the most recent `30` trading days, but only barely:
  - artifact: `artifacts/outputs/stalker_v10_1_recent_30d_check_20260328/summary.json`
  - period: `2026-02-05` to `2026-03-20`
  - metrics: `R$40`, `PF 1.0357`, `DD 4.67%`, `48` trades
- Interpretation: the edge has not obviously broken, but the most recent tape is much weaker than the full-sample average. Monday should be treated as a cautious paper-validation start, not an excuse to scale up.
- Hard cost stress:
  - artifact: `artifacts/outputs/stalker_v10_1_contract_stress_followups_20260328/summary.json`
  - fixed `5`-tick spread on every bar: `R$-16,975`, `PF 0.6614`, `DD 168.02%`, composite `-0.9242`
  - interpretation: severe spread deterioration is a full stop condition, not a scale-down condition
 - Exact spread-tolerance sweep:
   - artifact: `artifacts/outputs/stalker_v10_1_spread_tolerance_followups_20260328/summary.json`
   - Tier 2 cooldown-only: profitable at `2` ticks, negative at `3`
   - Tier 3 cooldown+max-hold: profitable at `2` ticks, negative at `3`
   - wider `TP 0.48` cooldown variant: barely profitable at `3` ticks (`R$215`, `PF 1.0040`)
   - wider `TP 0.48` + max-hold variant: still only barely profitable at `3` ticks (`R$415`, `PF 1.0078`)
   - interpretation: the operational break-even spread for the main deployable strategy is `2` ticks, and anything above that should be treated as a stand-down regime
 - Entry-spread diagnostic:
   - artifact: `artifacts/outputs/stalker_v10_1_spread_entry_diagnostics_20260328/summary.json`
   - the cached historical tape only used `0` or `1` tick spreads at entry
   - interpretation: a `1`-tick spread guard is a live execution safeguard, not a historical alpha feature
- Recent-softness diagnosis:
  - artifact: `artifacts/outputs/stalker_v10_1_recent_softness_analysis_20260328/summary.json`
  - trades per day actually rose from `1.2574` full-sample to `1.6000` recently, so this was not a simple signal drought
  - win rate fell by `5.55` points and average profit per trade fell by `R$8.18`, which points to worse signal quality
  - prior-day daily `ADX(14) > 25` only `16.67%` of the time recently versus `31.57%` over the full sample
  - recent daily ATR14 and daily range were both below the full-sample average
  - feature check inside the recent window:
    - session only: `R$145`, `PF 1.1111`, `DD 3.37%`
    - session + cooldown only: `R$40`, `PF 1.0357`, `DD 4.67%`
    - session + cooldown + max-hold: `R$40`, `PF 1.0357`, `DD 4.67%`
  - interpretation: the recent softness looks much more like a weaker, less-trending tape than a lack of opportunities, and the cooldown specifically over-throttled the recent month; the max-hold layer added nothing on top of it there.
- Fresh Monday-readiness follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_monday_readiness_followups_20260328/summary.json`
  - last `5` trading days (`2026-03-16` to `2026-03-20`) were actually solid:
    - session + cooldown only: `R$110`, `PF 1.7857`, `DD 0.84%`
    - session + cooldown + max-hold: identical
  - first-trade-of-day throttling was clearly worse:
    - `R$8,600`, `PF 1.4531`, `DD 3.82%`, composite `1.8909`
  - EMA50 direction filter was an exact tie with the cooldown baseline:
    - `R$14,085`, `PF 1.4825`, `DD 3.30%`, composite `3.0529`
  - ATR-expansion volatility breakout produced `0` trades in this implementation
  - interpretation: the live-ready strategy did not change; the latest week looks healthier, and the new filters either added nothing or hurt
- Entry/cost follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_entry_cost_followups_20260328/summary.json`
  - smart-entry micro-pullback within `3` bars was not good enough:
    - `1` tick: `R$2,220`, `PF 1.5139`, `DD 3.92%`
    - `2` ticks: `R$1,550`, `PF 1.3944`, `DD 3.73%`
  - two-bar directional confirmation was decisively bad:
    - `R$-1,485`, `PF 0.7564`, `DD 18.63%`
  - volume-weighted relative-volume sizing overlay stayed research-only and weaker than the baseline:
    - `R$10,340`, `PF 1.4388`, `DD 3.70%`, composite `2.3424`
  - the flat commission proxy had no effect because the exact harness still uses `ROUND_TRIP_COST_BRL = 0.0`
  - longer cooldowns did not help enough:
    - `45m`: `R$13,405`, `PF 1.5009`, `DD 3.46%`, composite `2.8604`
    - `60m`: `R$11,930`, `PF 1.4759`, `DD 3.49%`, composite `2.5844`
  - interpretation: the strategy ceiling still looks driven by spread control and signal quality, not by slower entry pacing or delayed confirmation
- Seasonality follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_seasonality_followups_20260328/summary.json`
  - pooled quarter read on Tier 2:
    - `Q1`: `R$4,040`, `PF 1.6418`, `DD 4.26%`, composite `4.4541`
    - `Q2`: `R$4,495`, `PF 1.6538`, `DD 2.68%`, composite `7.2037`
    - `Q3`: `R$3,200`, `PF 1.3958`, `DD 3.32%`, composite `4.1836`
    - `Q4`: `R$2,350`, `PF 1.2962`, `DD 6.63%`, composite `2.0236`
  - interpretation: Q2 has been strongest and Q4 weakest, but the seasonality is not clean enough to justify a hard calendar filter
- Microstructure follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_microstructure_followups_20260328/summary.json`
  - research-only one-tick better fill proxy was extremely strong:
    - `R$21,925`, `PF 1.7925`, `DD 2.64%`, composite `5.0181`
  - interpretation: execution quality is likely the cleanest remaining frontier, but this is not a live-ready alpha claim because it assumes every trade gets one extra tick without affecting fill probability
- Microstructure entry follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_microstructure_entry_followups_20260328/summary.json`
  - plain next-M1-open entry proxy was the worst of the group
  - waiting for the next M1 open only when it was no worse than the signal close was decisively negative
  - requiring the next M1 open to already be one full WDO tick better than the signal close was also decisively negative
  - interpretation: the strategy wants fast retracement execution, not delayed confirmation at the next minute
- Bollinger squeeze follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_bollinger_squeeze_followups_20260328/summary.json`
  - bottom-quartile squeeze gate: `R$2,595`, `PF 1.4428`, `DD 5.24%`, composite `0.7348`
  - bottom-third squeeze gate: `R$2,670`, `PF 1.3160`, `DD 8.27%`, composite `0.6195`
  - interpretation: the squeeze gate strips out too much of the strategy's opportunity set and is not a viable promotion path
- ATR trailing-stop follow-up:
  - artifact: `artifacts/outputs/stalker_v10_1_trailing_stop_followups_20260328/summary.json`
  - trailing by `2.0 x ATR` after the trade reached `50%` of target was an exact tie with Tier 2
  - interpretation: this trailing-stop variant adds complexity without improving the result

## Regime Readout

- Regime split artifact:
  - `artifacts/outputs/stalker_v10_1_regime_followups_20260328/summary.json`
- Trend days, defined as prior-day daily `ADX(14) > 25`, are where most of the strategy's quality comes from:
  - trend-day session only: `R$8,480`, `PF 1.7948`, `DD 4.31%`
  - trend-day session + cooldown + max-hold: `R$7,535`, `PF 1.9183`, `DD 3.38%`
- Range days, defined as prior-day daily `ADX(14) <= 25` or unavailable, are still positive but materially weaker:
  - range-day session only: `R$7,485`, `PF 1.2958`, `DD 5.96%`
  - range-day session + cooldown + max-hold: `R$6,600`, `PF 1.3153`, `DD 4.95%`
- Interpretation:
  - the strategy does not require trend days to stay profitable
  - but trend days are clearly the engine of the best `PF`, average trade quality, and drawdown control
  - weak, low-ADX tape should be expected to feel softer even when the model stays nominally positive
- Full-sample adaptive regime overlays did not clearly beat the main leader:
  - adaptive cooldown (`30m` on trend days, `15m` on range days): `R$14,770`, `PF 1.4670`, `DD 3.75%`
  - regime switch (`session only` on range days, `session + cooldown + max-hold` on trend days): `R$15,020`, `PF 1.4482`, `DD 4.13%`
  - both improved gross net versus the current exact leader, but neither improved the balanced `PF/DD/OnTester` profile enough to replace it as the main recommendation

## 2025 Stability Split

- Stability split artifact:
  - `artifacts/outputs/stalker_v10_1_2025_half_split_20260328/summary.json`
- First half of `2025`:
  - `R$1,555`, `PF 1.5604`, `DD 2.96%`
  - prior-day `ADX > 25` share: `13.93%`
- Second half of `2025`:
  - `R$655`, `PF 1.2652`, `DD 3.02%`
  - prior-day `ADX > 25` share: `3.91%`
- Interpretation:
  - the production candidate stayed positive in both halves
  - but the second half was clearly weaker, and it coincided with an even less-trending tape
  - that reinforces the regime story rather than contradicting it

## Load-Bearing Components

- Structural ablation artifact:
  - `artifacts/outputs/stalker_v10_1_structural_ablation_rollover_20260328/summary.json`
- Reference exact production candidate:
  - `R$14,135`, `PF 1.4851`, `DD 3.29%`
- Removing the explicit session-hour gate hurt quality:
  - no session filter: `R$13,975`, `PF 1.4545`, `DD 3.92%`
  - interpretation: the session-hour structure is one of the true load-bearing pieces, even though it does not change net profit dramatically by itself
- Removing the cooldown raised gross net, but weakened the quality balance:
  - no cooldown: `R$16,015`, `PF 1.4458`, `DD 4.03%`
  - interpretation: cooldown is primarily a cost-control and drawdown-control feature, not a raw-net booster
- Removing the max hold barely changed the result:
  - no max hold: `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - interpretation: the 120 M1-bar max hold is a small but real refinement, not the main source of the edge
- Removing `SkipShortWednesday` clearly damaged quality:
  - `R$14,105`, `PF 1.4191`, `DD 3.88%`
  - interpretation: short-side Wednesday selectivity is a real contributor
- Removing `SkipShortHour13` did nothing in the exact harness:
  - identical result to the reference
  - interpretation: that is because the explicit session gate already excludes the entire `13:00` hour in the exact research harness
  - deployment caveat: this does not mean the MT5 `13:00` skip should be deleted, because the live preset uses the hour skip to reproduce the same practical behavior
- Minimal fallback readout:
  - cooldown-only variant, dropping the max hold: `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - capture versus the full production candidate: `99.65%` net, `99.82%` PF, `99.38%` OnTester
  - interpretation: the cooldown-only version is the cleanest simplified fallback if the max-hold logic ever misbehaves in MT5

## Contract Rollovers

- Rollover-period artifact:
  - `artifacts/outputs/stalker_v10_1_structural_ablation_rollover_20260328/summary.json`
- Using the dataset's monthly contract proxy, the first `3` trading days of each contract month were the cleanest part of the tape:
  - `R$2,885`, `PF 1.7455`, `DD 3.83%`
- Mid-contract days stayed strong:
  - `R$10,020`, `PF 1.4872`, `DD 5.15%`
- The last `3` contract days were the weakest:
  - `R$1,230`, `PF 1.2614`, `DD 6.50%`
- Full-sample stand-down variant, skipping the last `3` contract days entirely:
  - `R$12,905`, `PF 1.5281`, `DD 3.49%`
- Interpretation:
  - the strategy still works late in the contract cycle, but quality clearly deteriorates there
  - month-end / rollover-tail sessions should be treated more cautiously than fresh-contract sessions
  - the simple stand-down filter improves PF, but it gives up too much net profit and does not improve drawdown enough to replace the main production candidate
- Contract-month robustness addendum:
  - separate contract-month scoring on the production candidate was positive in `47` of `61` monthly contract buckets, or `77.05%`
  - best contract by net: `2022-05`, `R$1,000`, `PF 2.60`
  - worst contract by net: `2022-10`, `R$-275`, `PF 0.7511`
  - recent sequence: `2026-01` and `2026-02` were weak, `2026-03` recovered to `R$225`, `PF 1.4545`

## Rolling Degradation Profile

- Rolling-risk artifact:
  - `artifacts/outputs/stalker_v10_1_minimal_risk_followups_20260328/summary.json`
- Trailing `60`-trading-day profit factor:
  - median: `1.4119`
  - minimum: `0.8408`
  - share of windows below `1.0`: `4.46%`
  - worst window: `2025-12-05` through `2026-03-06`
  - longest consecutive stretch of sub-`1.0` windows: `9`
- Underwater profile:
  - longest underwater stretch: `69` trading days, `2025-04-07` through `2025-07-16`
  - current state at the end of the sample: still underwater versus the prior peak
- Interpretation:
  - this is not a constantly smooth equity curve
  - the strategy can go soft for multiple months without being structurally broken, so operator expectations and sizing discipline matter

## Best Python Candidates Pending MT5

- Best exact Python candidate waiting on MT5 validation:
  - exact hours: `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - skip the full `13:00` hour
  - require at least `30 minutes` between filled entries
  - close any position older than `120` M1 bars
  - `SL 0.84 / TP 0.30`
  - artifact: `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
  - metrics: `R$14,135`, `PF 1.4851`, `DD 3.29%`, `OnTester 4290.320082`
  - walk-forward `70/30`: train `R$11,045`, `PF 1.5332`, `DD 3.29%`; test `R$3,090`, `PF 1.3668`, `DD 4.57%`
  - MT5 preset now prepared:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
  - interpretation: this is the first exact overlay that improves the cooldown winner on net profit, PF, drawdown, and OnTester together while staying positive on the held-out last 30%
- Operationally preferred exact refinement for Monday:
  - validate the plain cooldown-only variant before the max-hold variant
  - artifact: `artifacts/outputs/stalker_v10_1_recent_tiers_followup_20260328/summary.json`
  - recent weak-tape tie:
    - cooldown only: `R$40`, `PF 1.0357`, `DD 4.67%`
    - cooldown + max-hold: `R$40`, `PF 1.0357`, `DD 4.67%`
  - interpretation: the max-hold leader is still the best exact alpha line by a hair, but the cooldown-only variant is the cleaner first deployment step because it keeps `99.65%` of the net and `99.82%` of the PF with less moving logic

- Optional trend-day quality preset:
  - session winner + `30-minute cooldown` + `120` M1-bar max hold + prior-day daily `ADX(14) > 25`
  - MT5 preset:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`
  - exact regime-slice metrics:
    - `R$7,535`, `PF 1.9183`, `DD 3.38%`
  - interpretation:
    - this is not the new main preset because it over-prunes too hard for full-sample deployment
    - but it is a valid quality-focused option if the desk explicitly wants trend-day selectivity

- Best cost-robust exact refinement:
  - exact hours: `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - skip the full `13:00` hour
  - require at least `30 minutes` between filled entries
  - `SL 0.84 / TP 0.30`
  - artifact: `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`
  - metrics: `R$14,085`, `PF 1.4825`, `DD 3.30%`, `OnTester 4263.59877`
  - interpretation: lower raw net than the unconstrained session winner, but materially better `PF`, `DD`, and `OnTester` while directly reducing trade frequency and transaction-cost exposure
  - deployment note: this variant also beat the same cooldown applied without the session filter (`R$13,925`, `PF 1.4522`, `DD 3.93%`), so the exact hour scheduling still matters even after throttling entries

- Best gross-net exact refinement:
  - exact hours: `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - skip the full `13:00` hour
  - `SL 0.84 / TP 0.50`
  - artifact: `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`
  - metrics: `R$21,170`, `PF 1.3762`, `DD 4.76%`, `OnTester 4445.7`
  - interpretation: best raw net and top exact objective from the latest pass, but weaker quality balance than the cooldown variant

- Previous session-winner reference:
  - `SL 0.84 / TP 0.30`
  - artifact: `artifacts/outputs/stalker_v10_1_session_refinement_20260328/summary.json`
  - metrics: `R$15,965`, `PF 1.4438`, `DD 4.04%`, `OnTester 3950.819156`

- MT5 presets now prepared for the leading exact refinements:
  - cooldown leader:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
  - max-hold leader:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
  - maximum-quality v2:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
  - note: the MQ5 EA now exposes both cooldown and max-hold controls, so the next blocker is only a clean MT5 `Every tick` validation run

## New Findings From Advanced Follow-ups

- Exact execution refinement says the current session winner is already near a local optimum:
  - artifact: `artifacts/outputs/stalker_v10_1_session_execution_refinement_20260328/summary.json`
  - reference still best overall: `R$15,965`, `PF 1.4438`, `DD 4.04%`
  - tighter stops `0.60`, `0.66`, `0.72` all underperformed the reference
  - time exits `30`, `60`, `90` bars did not beat the reference in a meaningful way
  - partial-profit plus trail was a clear miss: `R$5,472.5`, `PF 1.31`, `DD 6.09%`

- Wider take-profits improved raw net profit, but not the overall quality balance:
  - `TP 0.42`: `R$17,505`, `PF 1.3591`, `DD 4.99%`
  - `TP 0.48`: `R$20,475`, `PF 1.3882`, `DD 5.21%`
  - `TP 0.54`: `R$20,320`, `PF 1.3505`, `DD 5.52%`
  - interpretation: wider TPs raise gross PnL, but the current `TP 0.30` session winner still has the best combined `PF/DD/OnTester`

- A wider ATR-based stop also improved raw net, but not enough to displace the reference:
  - artifact: `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`
  - `ATR14` with `SL 1.50 x ATR`, `TP 0.30`: `R$16,950`, `PF 1.4074`, `DD 5.78%`
  - interpretation: higher gross profit, but weaker `PF/DD/OnTester` than the current `ATR20 x 0.84` reference

- The new exact cost-robustness pass changed the frontier meaningfully:
  - artifact: `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`
  - `30-minute cooldown`: `R$14,085`, `PF 1.4825`, `DD 3.30%`, `OnTester 4263.59877`
  - `30-minute cooldown` without the exact session filter: `R$13,925`, `PF 1.4522`, `DD 3.93%`
  - `ATR14 TP 0.50`: `R$21,170`, `PF 1.3762`, `DD 4.76%`, `OnTester 4445.7`
  - `ATR14 TP 1.00`: `R$19,730`, `PF 1.2350`, `DD 7.14%`
  - `ATR14 SL 1.00`: `R$15,565`, `PF 1.3933`, `DD 5.26%`
  - `ATR14 SL 2.00`: `R$16,090`, `PF 1.3671`, `DD 6.86%`
  - interpretation: the session winner already uses ATR-based exits, so the “dynamic ATR” tests are really multiplier changes. The best gross-net change is `TP 0.50`, but the best cost-robust exact refinement is the `30-minute cooldown`.

- Final stop-management and profit-throttle follow-ups:
  - artifact: `artifacts/outputs/stalker_v10_1_wider_sl_followups_20260328/summary.json`
  - `SL 1.00 / TP 0.30`: `R$13,930`, `PF 1.4556`, `DD 4.07%`, composite `2.5434`
  - `SL 1.20 / TP 0.30`: `R$14,475`, `PF 1.4626`, `DD 4.43%`, composite `2.3668`
  - `SL 0.84`, widen to `1.20` after `30` bars: `R$14,270`, `PF 1.4887`, `DD 3.28%`, composite `3.0607`
  - interpretation: the time-widened stop is the only real headline-metric improvement over max-hold, but it still loses by a hair on the Sortino-weighted composite and is more complex to ship.

- Final session-end and weekly-cap controls:
  - artifact: `artifacts/outputs/stalker_v10_1_session_close_weekly_followups_20260328/summary.json`
  - market-close avoidance (`30` minutes before session end): identical to the reference exact leader
  - weekly cap `R$300`: `R$14,095`, `PF 1.4937`, `DD 3.32%`, composite `3.0512`
  - weekly cap `R$500`: identical to the reference exact leader
  - interpretation: market-close avoidance is a structural no-op under the current session and max-hold settings; the `R$300` weekly cap is smoother trade-to-trade but still not strong enough overall to replace the current main candidates.

- Final trade-momentum overlay:
  - artifact: `artifacts/outputs/stalker_v10_1_session_hot_hand_followup_20260328/summary.json`
  - trailing `10`-trade realized PnL must be positive: `32` trades, `R$630`, `PF 1.9921`, `DD 1.85%`, composite `0.7669`
  - interpretation: this is classic over-throttling. It cleans up the surviving trades but destroys the strategy by starving it of opportunities.

- Rolling `20`-trade Sharpe smoothing:
  - artifact: `artifacts/outputs/stalker_v10_1_trade_sharpe_smoothing_20260328/summary.json`
  - smoothest exact trade-to-trade variant: weekly cap `R$300`, median rolling Sharpe `0.7457`
  - next smoothest: session winner `0.7450`, max-hold v2 `0.7390`, cooldown-only `0.7365`
  - MT5 Tier 1 base was rougher at `0.5254`
  - interpretation: the weekly-cap variant is slightly smoother, but not enough to override the stronger total-package candidates.

- Trend-efficiency lookback optimization says the default `15-minute` window is still the right anchor:
  - artifact: `artifacts/outputs/stalker_v10_1_session_trend_window_sweep_20260328/summary.json`
  - `5 minutes`: `R$13,580`, `PF 1.4251`, `DD 3.75%`
  - `10 minutes`: `R$13,385`, `PF 1.4323`, `DD 3.47%`
  - `15 minutes`: `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - `20 minutes`: `R$12,795`, `PF 1.4443`, `DD 3.39%`
  - `25 minutes`: `R$12,255`, `PF 1.4544`, `DD 3.74%`
  - interpretation: shortening the lookback can clean up some noise, but `15 minutes` still wins on net profit, PF, drawdown, and OnTester together.

- The latest exact signal overlays did not beat the session+cooldown leader:
  - artifact: `artifacts/outputs/stalker_v10_1_session_signal_followups_20260328/summary.json`
  - `ROC(10)` replacing trend-efficiency: `R$14,330`, `PF 1.4388`, `DD 3.92%`
  - `ROC(20)` replacing trend-efficiency: `R$13,960`, `PF 1.4229`, `DD 3.93%`
  - `current volume > 1.5x prior 20-bar mean`: `R$11,750`, `PF 1.4646`, `DD 6.19%`
  - `skip first 15 minutes of the 10:00 hour`: `R$12,670`, `PF 1.5198`, `DD 4.34%`
  - `stop after 2 consecutive daily losses`: identical to the reference cooldown winner
  - interpretation: ROC is a credible simplification, but it still gives up too much edge versus the trend-efficiency reference. The practical session-gap filter improves PF, but loses too much net profit. The daily loss-stop adds nothing on this tape because the current session+cooldown structure already throttles the weakest clusters.

- The latest structural overlays also failed to displace the session+cooldown leader:
  - artifact: `artifacts/outputs/stalker_v10_1_session_structure_followups_20260328/summary.json`
  - rolling signal-strength gate (`trend_eff` above its rolling `75th` percentile for longs, below its `25th` percentile for shorts): `R$11,270`, `PF 1.4314`, `DD 3.81%`
  - weighted composite score (`0.7 * z(trend_eff_15) + 0.3 * z(ROC10)`): `R$12,985`, `PF 1.4807`, `DD 3.36%`
  - Tuesday-through-Thursday only: `R$7,795`, `PF 1.4833`, `DD 4.07%`
  - max open time `45` exact M1 bars: `R$13,420`, `PF 1.4616`, `DD 3.48%`
  - max open time `660` M1 bars, roughly `11` M15 hours: identical to the reference cooldown winner
  - interpretation: the composite score is the closest challenger, but it still gives up too much net and a little drawdown protection. The rolling-strength gate over-prunes. Weekly seasonality is basically neutral, and the “45 bars” request only helps if interpreted as a much looser, effectively inactive time stop.

- The latest deployment-quality follow-ups still leave the session+cooldown leader on top:
  - artifact: `artifacts/outputs/stalker_v10_1_session_quality_followups_20260328/summary.json`
  - rolling signal-strength gate with a `100-bar` history: `R$11,300`, `PF 1.4213`, `DD 3.62%`
  - adaptive exit-based cooldown (`15` minutes after a win, `30` after a loss): `R$14,575`, `PF 1.4697`, `DD 3.83%`
  - maximum-quality all-sides timing preset (`full Wednesday skip`, `full 13:00 skip`, `30-minute cooldown`): `R$10,665`, `PF 1.4492`, `DD 3.78%`
  - interpretation: adaptive cooldown raises raw net profit, but it weakens PF, DD, and OnTester relative to the fixed `30-minute` cooldown. The 100-bar strength gate is too restrictive. The all-sides Wednesday version is a cleaner operational preset, but not the best exact strategy.

- The latest macro/context overlays found one genuine new best exact candidate:
  - artifact: `artifacts/outputs/stalker_v10_1_session_macro_followups_20260328/summary.json`
  - daily ADX regime (`prior-day ADX(14) > 25`): `R$7,485`, `PF 1.9067`, `DD 3.38%`
  - DXY correlation (`prior-day 20-session corr > 0.70`): `R$-120`, `PF 0.7670`, `DD 2.42%`
  - `120` M1-bar max position duration plus `30-minute` cooldown: `R$14,135`, `PF 1.4851`, `DD 3.29%`, `OnTester 4290.320082`
  - interpretation: the DXY filter is too sparse and should be dropped. The daily ADX regime is an interesting high-quality niche, but it over-prunes too hard. The `120`-minute max hold is the first macro/risk overlay that actually improves the session+cooldown leader on net profit, PF, drawdown, and OnTester all at once.

- The latest max-hold follow-up closed the loop on deployment confidence:
  - artifact: `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
  - exact `70/30` holdout for the max-hold leader:
    - train: `R$11,045`, `PF 1.5332`, `DD 3.29%`
    - test: `R$3,090`, `PF 1.3668`, `DD 4.57%`
  - volatility-based loss/age proxy (`0.5 ATR` loss exit, `600` M1 bars): `R$11,510`, `PF 1.4057`, `DD 3.53%`
  - half-target ratchet/trail on top of max-hold: `R$9,775`, `PF 1.3874`, `DD 4.42%`
  - maximum-quality v2 (`full Wednesday skip`, `full 13:00 skip`, `30-minute cooldown`, `120` M1-bar max hold): `R$10,665`, `PF 1.4492`, `DD 3.78%`
  - interpretation: the plain `120`-bar max hold remains the best refinement; the ATR proxy and half-target trail are useful negative controls, and the full Wednesday version stays a quality-biased operator preset rather than the main alpha line

- The final innovation pass did not displace the max-hold leader:
  - artifact: `artifacts/outputs/stalker_v10_1_session_final_innovations_20260328/summary.json`
  - repeated exact `70/30` walk-forward for the max-hold leader:
    - train: `R$11,045`, `PF 1.5332`, `DD 3.29%`
    - test: `R$3,090`, `PF 1.3668`, `DD 4.57%`
  - M30 confirmation from aggregated M15 bars: `R$12,460`, `PF 1.5335`, `DD 3.25%`
  - TP scaling after three consecutive wins: `R$12,600`, `PF 1.3966`, `DD 3.45%`
  - M30 confirmation plus TP scaling: `R$12,315`, `PF 1.4971`, `DD 3.31%`
  - interpretation: M30 confirmation is a credible quality niche because it slightly improves PF and DD, but it gives up too much net profit and OnTester. TP streak-scaling weakens the strategy and should not be promoted.

- The final stress/deployability pass reinforces the same conclusion:
  - artifact: `artifacts/outputs/stalker_v10_1_session_final_stress_followups_20260328/summary.json`
  - 30-bar VWAP slope sign filter: `R$13,405`, `PF 1.4628`, `DD 4.26%`
  - position-sizing grid on the max-hold leader:
    - `0.5` contract: `R$7,067.5`, `PF 1.4851`, `DD 2.14%`
    - `1.0` contract: `R$14,135`, `PF 1.4851`, `DD 3.29%`
    - `2.0` contracts: `R$28,270`, `PF 1.4851`, `DD 5.03%`
    - `3.0` contracts: `R$42,405`, `PF 1.4851`, `DD 6.32%`
  - max-hold leader under `3x` spread stress: `R$-3,300`, `PF 0.9198`, `DD 46.44%`
  - interpretation: the VWAP-slope gate is not worth the net-profit giveback, size scales cleanly in PF terms but predictably amplifies drawdown, and severe execution deterioration still breaks the edge.

- The final cost-focused pass did not change the recommendation:
  - artifact: `artifacts/outputs/stalker_v10_1_session_cost_followups_20260328/summary.json`
  - max-hold leader plus `TP 0.42`: `R$15,660`, `PF 1.3951`, `DD 5.16%`
  - max-hold leader plus `TP 0.48`: `R$18,625`, `PF 1.4356`, `DD 4.92%`
  - strict spread-aware entry (`current spread < prior session average spread`): `0` trades
  - max-hold leader Monte Carlo:
    - shuffled trade-order drawdown `95th` percentile: `8.79%`
    - bootstrap ending PnL `5th/95th`: `R$10,483.25` / `R$17,686.75`
  - interpretation: the wider targets are viable gross-net variants, but the plain `TP 0.30` max-hold leader still wins on the combined `PF/DD/OnTester` balance. The spread-aware idea is a dead end on this historical tape because the cached spread is almost always `1` tick, so there are no real “wide-spread moments” for the filter to dodge in the backtest data.

- The final wrap-up pass confirmed that the production line is already mature:
  - artifact: `artifacts/outputs/stalker_v10_1_session_wrapup_followups_20260328/summary.json`
  - quarter-adaptive hours (derived from the reference tape): `R$14,030`, `PF 1.4889`, `DD 3.41%`
  - month-adaptive hours (derived from the reference tape): `R$14,355`, `PF 1.5991`, `DD 3.50%`
  - max-daily-profit rule at `R$27.69`: `R$10,190`, `PF 1.4506`, `DD 3.66%`
  - interpretation: the month-adaptive hour map is the strongest exploratory niche left, but it is explicitly in-sample and therefore not production-safe. The daily profit-cap idea clearly hurt. The production recommendation stays with the fixed-hour max-hold leader.

- The final “patience entry” idea was decisively debunked:
  - artifact: `artifacts/outputs/stalker_v10_1_session_patience_followups_20260328/summary.json`
  - wait up to `3` bars for a `30%` signal-bar pullback: `R$-10,050`, `PF 0.4857`, `DD 100.94%`
  - `40%` pullback: `R$-12,430`, `PF 0.5443`, `DD 125.06%`
  - `50%` pullback: `R$-11,885`, `PF 0.6497`, `DD 119.47%`
  - interpretation: this strategy’s edge depends on entering close to the original signal, not on waiting for a nicer-looking retracement. The “patience” instinct is directionally wrong for this setup.

- The last entry-management ideas were also decisively rejected:
  - artifact: `artifacts/outputs/stalker_v10_1_session_confirmation_followups_20260328/summary.json`
  - one-candle confirmation before entry: `R$-3,515`, `PF 0.8739`, `DD 38.49%`
  - static profit-lock at `75%`/`25%` of target: `R$5,480`, `PF 1.2426`, `DD 9.66%`
  - confirmation plus profit-lock: `R$-5,920`, `PF 0.7372`, `DD 61.28%`
  - interpretation: this signal wants immediate participation and a clean fixed target; both delayed confirmation and early profit-locking damage the edge badly.

- A stricter trend-day gate (`prior-day ADX > 30`) was too narrow even on the simpler cooldown tier:
  - artifact: `artifacts/outputs/stalker_v10_1_high_adx_followups_20260328/summary.json`
  - cooldown-only reference: `R$14,085`, `PF 1.4825`, `DD 3.30%`
  - `ADX > 25`: `R$7,485`, `PF 1.9067`, `DD 3.38%`
  - `ADX > 30`: `R$3,515`, `PF 1.6356`, `DD 4.35%`
  - interpretation: the regime idea is real, but `ADX > 30` over-prunes too hard. If the desk wants a quality-only niche, `ADX > 25` is the upper bound worth considering.

- Risk-adjusted scoring confirms that the ADX quality mode is not a better production default:
  - artifact: `artifacts/outputs/stalker_v10_1_adx_risk_adjusted_followup_20260328/summary.json`
  - cooldown-only composite: `3.0529`
  - MT5 Tier 1 base composite: `2.8179`
  - `ADX > 25` quality composite: `2.0245`
  - interpretation: the ADX gate is useful as a discretionary quality mode, but once trade scarcity is priced in, it is clearly inferior to both Tier 1 and Tier 2 for default deployment.

- ATR percentile regimes show the edge is not concentrated in extreme high-volatility days:
  - artifact: `artifacts/outputs/stalker_v10_1_atr_regime_followups_20260328/summary.json`
  - low ATR regime: `R$6,400`, `PF 1.5305`, `DD 3.31%`
  - medium ATR regime: `R$3,475`, `PF 1.5711`, `DD 4.34%`
  - high ATR regime: `R$3,605`, `PF 1.3346`, `DD 5.08%`
  - interpretation: the strategy is actually cleaner in low-to-medium ATR tapes than in the most volatile third of days, so “more volatility” is not automatically better for this setup.

- The latest deployment follow-up increased confidence in the cooldown winner:
  - artifact: `artifacts/outputs/stalker_v10_1_session_deployment_followups_20260328/summary.json`
  - exact `70/30` holdout for the cooldown winner:
    - train: `R$10,995`, `PF 1.5295`, `DD 3.30%`
    - test: `R$3,090`, `PF 1.3668`, `DD 4.57%`
  - interpretation: weaker than the in-sample train segment, but still comfortably positive on the held-out last 30% of the sample

- Longer cooldowns did not beat the `30-minute` winner:
  - `45 minutes`: `R$13,405`, `PF 1.5009`, `DD 3.46%`, `OnTester 3877.467553`
  - `60 minutes`: `R$11,930`, `PF 1.4759`, `DD 3.49%`, `OnTester 3420.356383`
  - interpretation: slower trading can raise PF a bit, but `30 minutes` is still the best overall quality/net balance

- The time-weighted exit did not justify itself:
  - cooldown winner plus profitable-trade stop ratchet after `15` bars, with a tick-aligned `+0.5` every `10` bars
  - metrics: `R$12,875`, `PF 1.4967`, `DD 3.64%`, `OnTester 3536.163366`
  - interpretation: slightly cleaner PF, but too much net-profit giveback and weaker overall objective than the plain cooldown winner

- Overnight continuation did nothing in the current exact implementation:
  - cooldown winner plus “keep only profitable trades overnight”
  - metrics were identical to the plain cooldown winner
  - interpretation: in this strategy, positions that survive to the session cutoff are not a meaningful continuation edge under the current stop/target logic

- A recent-entry-density sizing overlay is promising, but only as an analysis overlay for now:
  - size rule: `1 / recent filled entries within 60 minutes`
  - metrics: `R$13,800`, `PF 1.5035`, `DD 3.18%`, `OnTester 4336.689655`
  - interpretation: it improves quality a bit on the cooldown tape, but it assumes fractional down-scaling at a `1`-contract baseline, so it is not directly deployable without a higher base size or a discrete contract-sizing redesign

- A slower H1-style proxy did not look attractive enough to replace the current engine:
  - hourly-boundary-only proxy over the cooldown winner
  - metrics: `R$1,450`, `PF 1.5598`, `DD 4.27%`, `OnTester 339.554945`
  - interpretation: it over-prunes too hard; fewer trades alone are not enough

- Monte Carlo says the cooldown winner is path-dependent, but not fragile:
  - permutation of trade order (`1000` runs) keeps final PnL fixed at `R$14,085` by construction
  - permutation max drawdown:
    - median `5.53%`
    - `95th` percentile `8.81%`
  - bootstrap resampling (`1000` runs) for ending PnL dispersion:
    - mean `R$14,036.88`
    - `5th` percentile `R$10,453.75`
    - `95th` percentile `R$17,630.25`
  - bootstrap max drawdown:
    - median `5.78%`
    - `95th` percentile `9.86%`

- Rolling intraday retracement windows create cleaner but smaller variants:
  - `8 bars`: `R$4,075`, `PF 1.5348`, `DD 3.68%`
  - `12 bars`: `R$8,260`, `PF 1.5091`, `DD 3.38%`
  - `20 bars`: `R$11,880`, `PF 1.3650`, `DD 5.64%`
  - `30 bars`: `R$12,770`, `PF 1.2954`, `DD 8.58%`
  - interpretation: the shorter windows improve selectivity, but none beat the full session-range winner overall

- Friday exclusion is the best exact quality variant from the latest pass:
  - artifact: `artifacts/outputs/stalker_v10_1_session_advanced_followups_20260328/summary.json`
  - metrics: `R$13,100`, `PF 1.4902`, `DD 3.57%`
  - interpretation: better quality than the session winner, but lower net profit

- Monday and Thursday exclusions did not beat the session winner:
  - Monday off: `R$12,120`, `PF 1.4216`, `DD 4.83%`
  - Thursday off: `R$11,850`, `PF 1.4247`, `DD 3.74%`

- Daily ATR normal-range filter helped quality but not enough to beat the session winner:
  - best exact regime: ATR20 daily `10-90` percentile band
  - metrics: `R$12,890`, `PF 1.4552`, `DD 4.28%`

- Tighter rolling volatility regime also improved quality but over-pruned too hard:
  - ATR14 inside the `25th-75th` percentile of its own trailing `60-day` range
  - metrics: `R$6,735`, `PF 1.5465`, `DD 3.52%`

- Exact breakeven did not help:
  - best trigger tested: `0.20 ATR`
  - metrics: `R$10,605`, `PF 1.3798`, `DD 4.83%`
  - tighter breakeven triggers were much worse

- EMA `5/21` direction filter did not beat the session winner:
  - metrics: `R$14,480`, `PF 1.3847`, `DD 4.28%`

- Pyramiding is only a proxy result right now:
  - the proxy looks attractive, but it is not decision-grade until implemented in the exact engine

- The lightweight alternate-family prototype that looks most promising is a session-filtered EMA crossover entry family:
  - artifact: `artifacts/outputs/stalker_wdo_alt_session_signal_families_20260328/summary.json`
  - best lightweight variant: `EMA 5/21` crossover with `SL 0.84 / TP 0.42`
  - metrics: `R$70,557`, `PF 2.2923`, `DD 1.10%`
  - interpretation: too good to trust yet; this is a bar-based prototype screen, not an exact every-tick or MT5-parity backtest

- Exact every-tick EMA crossover validation failed and should not be promoted:
  - artifact: `artifacts/outputs/wdo_ema_crossover_exact_20260328/summary.json`
  - `EMA 5/21`, `SL 0.84 / TP 0.42`: `R$-1,805`, `PF 0.9554`, `DD 39.89%`
  - `EMA 5/21`, `SL 0.84 / TP 0.30`: `R$-3,880`, `PF 0.8857`, `DD 44.60%`
  - `EMA 8/34`, `SL 0.84 / TP 0.42`: `R$-2,030`, `PF 0.9322`, `DD 29.31%`
  - `EMA 3/13`, `SL 0.84 / TP 0.42`: `R$-9,300`, `PF 0.8552`, `DD 93.10%`
  - interpretation: the huge EMA prototype edge does not survive exact every-tick execution; keep this family on hold unless the entry/exit mechanics are redesigned

- The Bollinger mean-reversion family was negative and should not be pursued as-is:
  - `R$-13,586`, `PF 0.8837`, `DD 138.39%`

- A fresh exact inside-bar breakout family also failed:
  - artifact: `artifacts/outputs/wdo_inside_bar_breakout_exact_20260328/summary.json`
  - `SL 0.84 / TP 0.30`: `R$-4,775`, `PF 0.86`, `DD 58.41%`
  - `SL 0.84 / TP 0.48`: `R$-6,675`, `PF 0.8557`, `DD 76.68%`
  - interpretation: do not pursue the current inside-bar breakout implementation

## Month Robustness

The session winner is positive in every calendar month of the continuous WDO sample, but it is not equally strong:

- strongest months: `March`, `May`, `January`, `August`
- weakest months: `February`, `September`, `October`

Because the parquet is a continuous series, this is calendar-month robustness, not true contract-by-contract robustness.

Yearly stability is still acceptable, but 2025 was weaker than 2024:

- 2024: `R$2,995`, `PF 1.6175`, `DD 3.09%`
- 2025: `R$2,445`, `PF 1.3802`, `DD 4.32%`

Equity concentration is better than it looked by eye:

- top 10 trades account for only `4.82%` of total net profit
- top 20 trades account for `9.11%`
- top 10 days account for `12.03%`
- max consecutive losing days: `5`
- max consecutive winning days: `15`
- result: the equity curve is not dominated by a handful of outlier trades

Tuesday-through-Thursday is not a hidden magic sub-regime:

- Tuesday-through-Thursday trade subset: `R$7,795`, `PF 1.4833`, `DD 4.07%`
- Monday-and-Friday trade subset: `R$6,290`, `PF 1.4816`, `DD 4.97%`
- interpretation: the middle of the week is a little cleaner on drawdown, but not enough to justify throwing away Monday/Friday net profit

But cost sensitivity is real:

- exact `2x spread` stress: `R$4,790`, `PF 1.11`, `DD 12.48%`
- exact `3x spread` stress: `R$-4,570`, `PF 0.9081`, `DD 57.15%`
- interpretation: the edge survives moderate deterioration, but not severe execution slippage

## What To Stop Spending Time On

- Momentum divergence overlays
- VWAP reversion overlays on this entry logic
- Bollinger squeeze overlays
- M30 and H1 signal-timeframe replacements
- Opening-auction mean reversion prototype
- Consolidation-breakout prototype
- MT5 `Every tick based on real ticks`

## External Notes

- Web search did not surface a cleaner public 2025-2026 WDO edge than the repo's current session winner.
- The few recurring public motifs were still consistent with the local research:
  - VWAP and DI context are common in Brazilian mini-dollar discretionary/robot discussions:
    - https://www.mql5.com/en/job/186179
  - MQL5 optimization guidance still points to the same robustness workflow we are already using: optimization followed by forward checks and Monte Carlo rather than trusting raw in-sample tops:
    - https://www.mql5.com/en/articles/15116
  - PTAX reference prints can matter intraday, which is one plausible reason Friday behaves differently:
    - https://einvestidor.estadao.com.br/ultimas/ibovespa-hoje-ipca-15-leilao-bc-iof/
  - Current discretionary commentary on WDO still describes the contract as selective and often range-bound intraday, which matches the repo's finding that tighter session selection matters more than broader signal family changes:
    - https://analisa.genialinvestimentos.com.br/analises-tecnicas/analises-diarias/dolar-futuro/

## Blocked Tracks

- `WIN` cross-asset validation is currently blocked because the repo has no local `WIN` dataset.
- `WDO/WIN` pairs or spread research is blocked for the same reason; there is no second leg to build a ratio or z-score series.
- There is also no existing IB Gateway or brokerage data-ingestion code in the repo, so fetching `WIN` from the current workspace would be a separate integration project rather than a quick extension of the backtest loop.
- A historical news filter for CPI, NFP, and FOMC is still conceptually interesting, but it needs a timestamped macro calendar dataset first. Without that dataset, an exact backtest would be guesswork rather than research.

## Best Next Host-Side Validations

1. Validate the session winner approximation in MT5 `Every tick` once the tester is stable again.
   - the latest main-installation attempt still produced no HTML report in either the workspace output folder or the main terminal AppData tree, only the generated config file
2. Validate the plain exact session+cooldown refinement in MT5 `Every tick`.
   - it is the preferred next-week upgrade because it keeps almost all of the max-hold edge, matched the max-hold stack in the recent weak tape, and is operationally simpler
3. Implement and validate the `120`-minute max-hold plus `30-minute cooldown` refinement in MT5 `Every tick`.
   - this is still the highest exact alpha line, but it should come after the cooldown-only refinement in the host-side rollout order
4. Validate the Friday-exclusion preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 No Friday GPT 5.4.set`
5. If MT5 remains unstable, prioritize cost-robustness and live-paper safety checks over more entry-family exploration.
6. Do not spend more time on Bollinger mean reversion, inside-bar breakout, or the current EMA crossover family unless the entry/exit mechanics are materially redesigned.
7. Do not spend time on `WIN`, `WDO/WIN spread`, or news-filter backtests until the required external datasets are added.
8. If further experimentation continues inside the current family, prioritize only ideas that reduce transaction-cost sensitivity without materially giving up net profit. The current exact winners already look close to a local optimum.

## Production Recommendation

- Paper-trading default:
  - validated MT5 preset `WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4`
- Best exact Python candidate:
  - session winner with hours `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - keep `SkipShortHour13=true`
  - require at least `30 minutes` between filled entries
  - close any position older than `120` M1 bars
  - keep `SL 0.84 / TP 0.30`
- Known risks:
  - the edge weakens sharply under higher transaction costs; `2x` spread is still positive, `3x` spread is not
  - the edge is materially weaker in low-ADX, range-bound tape; the recent softness and the second half of 2025 both support that read
  - MT5 tester instability means the best exact refinements still need one clean host-side validation
- Next paper-trading step:
  - run the validated MT5 preset first
  - validate the plain cooldown preset in MT5 `Every tick` next:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
  - validate the max-hold leader only after that:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
  - monitor real slippage/spread conditions closely before promoting the exact refinements
- Operational guide:
  - `docs/mt5-paper-trading-playbook-2026-03-28.md`
  - `docs/mt5-monday-morning-checklist-2026-03-30.md`
  - `docs/stalker-v10-1-production-comparison-2026-03-28.md`
