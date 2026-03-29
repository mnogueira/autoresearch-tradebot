# MT5 Paper Trading Playbook - 2026-03-28

## Goal

Enable the current WDO Stalker v10.1 leader safely in MetaTrader 5 paper trading for Monday, `2026-03-30`.

Ceiling note:
- the current signal family now looks close to its local ceiling on the available WDO tape
- the remaining practical upside appears to be execution quality, not another small hard filter

## Recommended Presets

### Safest validated preset

- Use this first if the goal is highest confidence:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`
- Validated MT5 Every Tick result:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`
- Artifact:
  - `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`

### Best exact cooldown-sweep winner waiting on MT5 validation

- Use this next if host-side MT5 is stable enough to validate and you want the best full-sample exact cooldown-only line:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m GPT 5.4.set`
- Exact every-tick cooldown-sweep result:
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
- Artifact:
  - `artifacts/outputs/stalker_v10_1_vwap_risk_cooldown_followups_20260328/summary.json`
- Interpretation:
  - this is the new best deployable exact composite score, but it has not yet had the same separate walk-forward and MT5 host validation pass as the older `30m` line

### Walk-forward-validated cooldown fallback

- Use this if the desk wants the more proven cooldown setting first:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
- Exact every-tick result:
  - `R$14,085`, `PF 1.4825`, `DD 3.30%`
- Artifact:
  - `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`

### Spread-resilient research tier

- This is not the Monday default, but it is the only tested variant that stayed barely profitable at a literal fixed `3`-tick spread:
  - `session winner + 30m cooldown + TP 0.48`
- Exact baseline result:
  - `R$18,475`, `PF 1.43`, `DD 4.92%`
- Fixed `3`-tick stress result:
  - `R$215`, `PF 1.0040`, `DD 25.14%`
- Interpretation:
  - this is a research fallback for very hostile cost regimes, not a production promotion
  - it survives `3` ticks, but only by a hair and with much worse drawdown than the main tiers

### New best exact Python refinement

- This is now MT5-ready, but it should be validated only after the simpler cooldown-only refinement:
  - session winner + `25-minute cooldown` + hard exit after `150` M1 bars
- Preset:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m GPT 5.4.set`
- Exact result:
  - `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340`
- Artifact:
  - `artifacts/outputs/stalker_v10_1_maxhold_sweep_followups_20260328/summary.json`
- Operational note:
  - the EA now exposes `MaxMinutesInTrade`, so the remaining work is just one clean MT5 `Every tick` validation run
  - recent weak-tape check says this extra max-hold layer added nothing over the cooldown-only version in the last `30` trading days
  - the broader recent `60`-trading-day check also came back as an exact tie with the cooldown-only line:
    - `R$30`, `PF 1.0157`, `DD 5.62%`
  - fixed-parameter `70/30` walk-forward still passed:
    - train `R$11,245`, `PF 1.5236`, `DD 3.28%`
    - test `R$3,175`, `PF 1.3662`, `DD 4.29%`

### New best exact research line now packaged for MT5 follow-up

- This is the strongest exact Python result so far, and it is now packaged in the EA/preset flow, but it is still not the Monday preset because it has not yet had host-side MT5 validation:
  - session winner + `25m` cooldown + `150` M1 max hold + `ROC(5)` directional agreement
- Preset:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m ROC5 Agreement GPT 5.4.set`
- Exact result:
  - `R$14,630`, `PF 1.4935`, `DD 3.28%`, composite `3.1676`
- Exact `70/30` walk-forward:
  - train `R$11,190`, `PF 1.5272`, `DD 3.28%`
  - test `R$3,440`, `PF 1.4086`, `DD 4.21%`
- Recent `60`-trading-day check:
  - `R$30`, `PF 1.0157`, `DD 5.62%`
- Operational note:
  - if the desk wants to pursue one more post-Monday improvement path, this ROC(5)-agreement preset is now the clearest host-side MT5 validation candidate

### Simpler ROC agreement follow-up

- This is the same ROC(5) confirmation idea on top of the simpler cooldown-only line:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m ROC5 Agreement GPT 5.4.set`
- Exact result:
  - `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493`
- Exact `70/30` walk-forward:
  - train `R$11,190`, `PF 1.5272`, `DD 3.28%`
  - test `R$3,440`, `PF 1.4086`, `DD 4.21%`
- Recent `60`-trading-day check:
  - `R$30`, `PF 1.0157`, `DD 5.62%`
- Recent `10`-trading-day check:
  - exact tie with plain Tier 2 at `R$455`, `PF 4.25`, `DD 0.81%`
- Operational note:
  - this is the cleaner ROC-based post-Monday validation target if the desk prefers to stay closer to Tier 2 than Tier 3
  - it is also the strongest out-of-sample post-Monday upgrade in the final exact `70/30` robustness pass:
    - test `R$3,440`, `PF 1.4086`, `DD 4.21%`

### Maximum-quality preset

- Use this if the desk prefers cleaner tape over raw net profit:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
- Exact result:
  - `R$10,665`, `PF 1.4492`, `DD 3.78%`
- Interpretation:
  - all-sides Wednesday skip plus full 13:00 skip is cleaner operationally, but it gives up too much net to replace the main candidate

### Trend-day quality preset

- Use this only if the desk explicitly wants a regime-gated, lower-frequency quality mode:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Trend Day ADX25 Cooldown 30m MaxHold120m GPT 5.4.set`
- Exact regime-slice result:
  - `R$7,535`, `PF 1.9183`, `DD 3.38%`
- Interpretation:
  - this is a quality-biased trend-day niche, not the default Monday preset
  - it is useful if the desk wants the EA itself to stand down in obviously range-bound daily regimes

## Recommended Configuration Tiers

- Tier 1, safest:
  - MT5-validated `sl0p84 / tp0p30`
  - use this as the Monday default because it is the best strategy already validated in MT5 `Every Tick`
  - operational expectation: about `1.96` trades per day on the validated MT5 report
- Tier 2, moderate:
    - session winner + `25m` cooldown only
    - use this as the first new exact refinement to validate because it is now the best deployable full-sample exact composite score
    - operational expectation: about `1.30` trades per day in the exact engine
- Tier 2A, ROC follow-up:
    - session winner + `25m` cooldown + `ROC(5)` agreement
    - use this after the plain Tier 2 validation if the desk wants the simplest ROC-enhanced upgrade path
    - among the tested agreement windows, `ROC(5)` beat `ROC(10)` and `ROC(20)` on the Tier 2 line
- Tier 3, aggressive:
    - session winner + `25m` cooldown + `150` M1 max hold
    - use this only after the simpler cooldown-only refinement looks sane in MT5
    - operational expectation: about `1.30` trades per day in the exact engine
    - out-of-sample it did not beat Tier 2A:
      - test `R$3,175`, `PF 1.3662`, `DD 4.29%`
- Tier 4, research-only:
  - equal-weight blend of Tier 3 and the time-widened stop variant
  - this slightly improved the research composite through portfolio smoothing, but it is not a Monday live preset

## Recommended Rollout Cadence

- Monday through the first full paper-trading week:
  - stay on Tier 1 only
- After `5` paper sessions, upgrade to Tier 2 only if:
  - fills look sane
  - spread behavior stays near the baseline
  - realized behavior is directionally consistent with the saved artifacts
- Consider Tier 3 only after another week of clean paper behavior:
  - the max-hold layer is a real refinement, but it is still the more complex operator choice

## Monday Setup Steps

1. Open the main MetaTrader 5 terminal and let it sync fully before touching the tester.
2. Confirm the EA source is present:
   - `mt5/experts/custom/WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
3. Compile the EA inside MetaEditor.
4. Open Strategy Tester.
5. Select:
   - Expert: `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
   - Symbol: continuous WDO symbol used by the terminal
   - Timeframe: `M1`
   - Model: `Every Tick`
6. Load the preset you want to validate or run.
7. Confirm the spread is realistic for current market conditions.
8. Run one clean backtest before enabling paper automation.
9. If the report is consistent with the artifact, switch to the paper account only after the tester run is complete.

## Live Paper Rules

- Start with the validated MT5 preset before promoting any exact-only refinement.
- Keep position size at `1` contract until live-paper slippage is understood.
- Do not use `Every tick based on real ticks`; stick to `Every Tick`.
- Watch the first two sessions for actual spread behavior at `10:00`, `11:00`, `12:00`, and `14:00`.
- If observed spread looks closer to the exact `2x` stress case than the baseline case, stay cautious about scaling.
- If observed spread ever sits near `5` ticks during the core hours, stand down; the exact `5`-tick stress test was decisively negative.
- Operational spread guardrail:
  - `0-1` tick: normal operating zone
  - `2` ticks: last tolerable integer spread for the main strategy, but already badly degraded
  - `>2` ticks: do not trade
  - only the wider-TP `0.48` research tier stayed barely positive at `3` ticks, and it is not strong enough to replace the main tiers

## Risk Budget

- Recommended maximum size for Monday:
  - `1` contract per `R$100k` of paper capital
- Stretch upper bound after stable paper fills:
  - `2` contracts per `R$100k`, and only if observed spread stays close to the historical `0-1` tick baseline
- Why this is the budget:
  - exact max-hold leader baseline drawdown at `1` contract was about `R$329` on the synthetic `R$10k` book
  - harsh `3x` spread stress drawdown at `1` contract was about `R$4,644`
  - that implies roughly `R$92,880` of capital per contract to keep the harsh stress case near a `5%` drawdown budget
- Practical interpretation:
  - one contract is the right Monday size even for larger paper accounts
  - scaling beyond that should wait until live-paper spread and fill quality confirm the base assumptions
- Account-size examples, assuming you meant `R$50k`, `R$100k`, and `R$500k`:
  - `R$50k`: conservative scalable max is effectively `0` whole contracts; in paper trading, `1` contract is observation-only and above the strict stress budget
  - `R$100k`: conservative max `1` contract; stretch upper bound `2`
  - `R$500k`: conservative max `5` contracts; stretch upper bound `10`

## Abort Conditions

- MT5 tester fails to produce a clean report.
- Live-paper spread regime looks materially worse than the historical baseline.
- Execution behavior around the allowed session windows differs from the backtest assumptions.
- Slippage pushes realized behavior toward the exact `3x spread` stress case.

## When To Stop Trading

- Pause immediately if paper trading produces `5` consecutive losing days.
- Pause if trailing `30` trading-day PF drops below `1.0` on the live-paper log.
- Pause if live spreads are repeatedly above `1` tick during the core `10:00`, `11:00`, `12:00`, and `14:00` windows.
- Pause if MT5 logs repeated order-close or order-modify errors.
- Strongly consider pausing in the last `3` contract days if the tape is also low-ADX and spread-heavy.

## Appendix - Known Limitations And Caveats

- Recent softness:
  - over the most recent `30` trading days (`2026-02-05` to `2026-03-20`), the exact max-hold leader was only marginally positive at `R$40`, `PF 1.0357`, `DD 4.67%`
  - artifact: `artifacts/outputs/stalker_v10_1_recent_30d_check_20260328/summary.json`
- Why the recent tape softened:
  - it was not a signal drought; trades per day actually rose from `1.26` full-sample to `1.60` in the recent window
  - signal quality degraded instead: win rate fell from `80.55%` to `75.00%`, and average profit per trade fell from `R$9.01` to `R$0.83`
  - the recent daily regime looked less trending: prior-day daily `ADX(14) > 25` only `16.67%` of the time recently versus `31.57%` over the full sample
  - recent daily ATR and daily range were both below the full-sample average
- Feature sensitivity inside the recent weak tape:
  - session-only, without cooldown or max-hold: `R$145`, `PF 1.1111`, `DD 3.37%`
  - session + cooldown only: `R$40`, `PF 1.0357`, `DD 4.67%`
  - session + cooldown + max-hold: `R$40`, `PF 1.0357`, `DD 4.67%`
  - interpretation: the cooldown helped over the full sample, but it hurt inside the most recent weak month; the max-hold layer added nothing on top of the cooldown there
- Regime dependence:
  - trend days, defined as prior-day daily `ADX(14) > 25`, are the quality engine
  - trend-day session + cooldown + max-hold: `PF 1.9183`, `DD 3.38%`
  - range-day session + cooldown + max-hold: `PF 1.3153`, `DD 4.95%`
  - interpretation: the strategy remains positive in range days, but it should be expected to underperform in weaker, low-ADX tape
- Contract-rollover sensitivity:
  - first `3` contract days: `R$2,885`, `PF 1.7455`, `DD 3.83%`
  - last `3` contract days: `R$1,230`, `PF 1.2614`, `DD 6.50%`
  - interpretation: late-contract sessions are still tradable, but they are materially weaker than fresh-contract sessions
  - exact full-sample stand-down variant, skipping the last `3` contract days entirely: `R$12,905`, `PF 1.5281`, `DD 3.49%`
  - operational takeaway: for Monday paper trading, treat the last `3` contract days as a caution zone where reducing size or standing down is reasonable if spreads or trend quality look poor, but this is not the new default preset because the stand-down filter gave up too much net profit
- Rolling degradation profile:
  - trailing `60`-day PF median: `1.4119`
  - trailing `60`-day PF minimum: `0.8408`
  - share of trailing `60`-day windows below `1.0`: `4.46%`
  - longest underwater stretch in the full exact equity curve: `69` trading days
  - interpretation: the strategy can stay soft for a couple of months without being structurally dead, so operator patience matters
- 2025 stability split:
  - first half of `2025`: `R$1,555`, `PF 1.5604`, `DD 2.96%`
  - second half of `2025`: `R$655`, `PF 1.2652`, `DD 3.02%`
  - prior-day `ADX > 25` share dropped from `13.93%` in the first half to `3.91%` in the second half
  - interpretation: the strategy stayed positive, but the weaker half-year also looked less trending
- Seasonal tilt on the Tier 2 exact line:
  - pooled `Q2`: `R$4,495`, `PF 1.6538`, `DD 2.68%`
  - pooled `Q4`: `R$2,350`, `PF 1.2962`, `DD 6.63%`
  - pooled `Q1+Q3` composite: `3.8252`
  - pooled `Q2+Q4` composite: `3.5570`
  - interpretation: there is some calendar texture, but not enough to justify a hard seasonal on/off rule
- Cost sensitivity:
  - the exact max-hold leader still fails badly under `3x` spread stress
  - the historical exact tape was effectively a `0-1` tick spread world, so repeated live spreads above `1` tick are a meaningful warning signal
  - exact fixed-spread break-even for the main deployable tiers is `2` ticks:
    - Tier 2 cooldown-only at `2` ticks: `R$4,700`, `PF 1.1320`, `DD 9.87%`
- Tier 3 cooldown+max-hold at `2` ticks: `R$4,735`, `PF 1.1287`, `DD 9.78%`
    - both turn negative at `3` ticks
  - a true fixed `5`-tick spread environment was catastrophic: `R$-16,975`, `PF 0.6614`, `DD 168.02%`
  - the exact Python harness still uses `ROUND_TRIP_COST_BRL = 0.0`, so flat commission doubling inside the research harness had no effect
  - practical interpretation: treat spread/slippage as the real live cost risk until an explicit broker/B3 fee model is added
  - spread-diagnostic artifact:
    - `artifacts/outputs/stalker_v10_1_spread_entry_diagnostics_20260328/summary.json`
  - interpretation:
  - the cached historical spread only ever reached `1` tick at entry, so the new `1`-tick entry guard is a live safety rail, not a historical alpha improvement
  - the opposite experiment was also revealing:
    - a research-only one-tick better fill on every trade would lift Tier 2 to `R$21,925`, `PF 1.7925`, `DD 2.64%`
    - operational interpretation: execution quality is a first-order driver of this strategy's edge
  - but the follow-up entry-timing overlays were strongly negative:
    - waiting for the next M1 open only when it was no worse than the signal close turned the strategy decisively negative
    - requiring the next M1 open to already be one tick better than the signal close was even more restrictive and also decisively negative
    - practical interpretation: the edge is in the current fast retracement entry logic plus good execution, not in delaying the trade by another minute
- MT5 tester instability:
  - MT5 `Every Tick` produced the usable validation runs
  - multiple `real ticks` and main-terminal attempts stalled or produced incomplete artifacts
  - a final main-install retry from the sandbox also failed because the process could not write under `C:\Program Files\MetaTrader 5 Terminal\MQL5`
  - that is why the Monday plan starts with a fresh `Every Tick` sanity run before any paper activation

## Current Recommendation

- Paper-trading default: the validated MT5 preset `sl0p84 / tp0p3`
- First upgrade to validate on the host: the plain `Cooldown 25m` preset
  - this is now the best deployable exact composite score from the cooldown sweep
- More validated fallback if the desk wants the safer exact step first: the plain `Cooldown 30m` preset
  - this remains attractive because it already passed the exact `70/30` walk-forward and matched the max-hold stack in the recent weak tape
- Next aggressive upgrade to validate on the host: the `Cooldown 25m + MaxHold150m` preset
- Tier 4, research blend for later study only:
  - equal-weight blend of Tier 3 and the time-widened stop variant
  - use only if the desk explicitly wants to run two near-identical variants side by side and average the risk
- Fallback refinement if the newer cooldown winner misbehaves in MT5: stay on the plain `Cooldown 30m` preset
- Simplest high-fidelity fallback:
  - the cooldown-only exact variant kept `99.65%` of the max-hold leader's net profit and `99.82%` of its PF
- Quality-only alternative: the `Maximum Quality v2 Cooldown 30m MaxHold120m` preset
- Optional regime-gated alternative: the `Trend Day ADX25 Cooldown 30m MaxHold120m` preset
- Optional operator rule around rollover tail days:
  - reduce size or skip trading in the last `3` trading days before the monthly WDO contract rollover if the tape also looks low-ADX or spread-heavy
- Monday runbook:
  - `docs/mt5-monday-morning-checklist-2026-03-30.md`
- Week 1 monitoring template:
  - `docs/mt5-week-1-monitoring-template-2026-03-28.md`
- Post-Monday roadmap:
  - `docs/mt5-next-steps-after-monday-2026-03-28.md`
