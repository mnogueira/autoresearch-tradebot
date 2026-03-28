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

- Use this next if host-side MT5 is stable enough to validate:
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

### Maximum-quality preset

- Use this if the desk prefers cleaner tape over raw net profit:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Maximum Quality v2 Cooldown 30m MaxHold120m GPT 5.4.set`
- Exact result:
  - `R$10,665`, `PF 1.4492`, `DD 3.78%`
- Interpretation:
  - all-sides Wednesday skip plus full 13:00 skip is cleaner operationally, but it gives up too much net to replace the main candidate

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

## Abort Conditions

- MT5 tester fails to produce a clean report.
- Live-paper spread regime looks materially worse than the historical baseline.
- Execution behavior around the allowed session windows differs from the backtest assumptions.
- Slippage pushes realized behavior toward the exact `3x spread` stress case.

## Current Recommendation

- Paper-trading default: the validated MT5 preset `sl0p84 / tp0p3`
- First upgrade to validate on the host: the `Cooldown 30m + MaxHold120m` preset
- Fallback refinement if the max-hold variant misbehaves in MT5: the plain `Cooldown 30m` preset
- Quality-only alternative: the `Maximum Quality v2 Cooldown 30m MaxHold120m` preset
- Monday runbook:
  - `docs/mt5-monday-morning-checklist-2026-03-30.md`
