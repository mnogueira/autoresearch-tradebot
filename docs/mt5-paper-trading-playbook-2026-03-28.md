# MT5 Paper Trading Playbook - 2026-03-28

## Goal

Enable the current WDO Stalker v10.1 leader safely in MetaTrader 5 paper trading for Monday, `2026-03-30`.

## Recommended Presets

### Safest validated preset

- Use this first if the goal is highest confidence:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`
- Validated MT5 Every Tick result:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`
- Artifact:
  - `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`

### Best exact Python candidate waiting on MT5 validation

- Use this next if host-side MT5 is stable enough to validate and you want the simplest exact refinement:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
- Exact every-tick parity result:
  - `R$14,085`, `PF 1.4825`, `DD 3.30%`
- Artifact:
  - `artifacts/outputs/stalker_v10_1_session_robustness_checks_20260328/summary.json`

### New best exact Python refinement

- This is now MT5-ready and should be the first refinement validated after the already-validated base preset:
  - session winner + `30-minute cooldown` + hard exit after `120` M1 bars
- Preset:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m MaxHold120m GPT 5.4.set`
- Exact result:
  - `R$14,135`, `PF 1.4851`, `DD 3.29%`
- Artifact:
  - `artifacts/outputs/stalker_v10_1_session_maxhold_followups_20260328/summary.json`
- Operational note:
  - the EA now exposes `MaxMinutesInTrade`, so the remaining work is just one clean MT5 `Every tick` validation run
  - recent weak-tape check says this extra max-hold layer added nothing over the cooldown-only version in the last `30` trading days

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
- Tier 2, moderate:
  - session winner + `30m` cooldown only
  - use this as the first exact refinement to validate because it keeps `99.65%` of the max-hold leader's net and `99.82%` of its PF with less moving logic
  - the risk-adjusted composite gap versus Tier 3 is only `0.0143`, and the recent weak tape was identical, so this is the better Monday follow-on choice
- Tier 3, aggressive:
  - session winner + `30m` cooldown + `120` M1 max hold
  - use this only after the simpler cooldown-only refinement looks sane in MT5

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

## Risks And Caveats

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
- Cost sensitivity:
  - the exact max-hold leader still fails badly under `3x` spread stress
  - the historical exact tape was effectively a `0-1` tick spread world, so repeated live spreads above `1` tick are a meaningful warning signal
- MT5 tester instability:
  - MT5 `Every Tick` produced the usable validation runs
  - multiple `real ticks` and main-terminal attempts stalled or produced incomplete artifacts
  - that is why the Monday plan starts with a fresh `Every Tick` sanity run before any paper activation

## Current Recommendation

- Paper-trading default: the validated MT5 preset `sl0p84 / tp0p3`
- First upgrade to validate on the host: the plain `Cooldown 30m` preset
  - this remains the preferred Monday follow-on because it is simpler and the composite-score gap versus the max-hold version is trivial
- Next aggressive upgrade to validate on the host: the `Cooldown 30m + MaxHold120m` preset
- Fallback refinement if the max-hold variant misbehaves in MT5: stay on the plain `Cooldown 30m` preset
- Simplest high-fidelity fallback:
  - the cooldown-only exact variant kept `99.65%` of the max-hold leader's net profit and `99.82%` of its PF
- Quality-only alternative: the `Maximum Quality v2 Cooldown 30m MaxHold120m` preset
- Optional regime-gated alternative: the `Trend Day ADX25 Cooldown 30m MaxHold120m` preset
- Optional operator rule around rollover tail days:
  - reduce size or skip trading in the last `3` trading days before the monthly WDO contract rollover if the tape also looks low-ADX or spread-heavy
- Monday runbook:
  - `docs/mt5-monday-morning-checklist-2026-03-30.md`
