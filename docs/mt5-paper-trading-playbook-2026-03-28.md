# MT5 Paper Trading Playbook - 2026-03-28

## Goal

Enable the safest currently trustworthy WDO Stalker v10.1 configuration for Monday paper trading.

## Current Truth

- Tier 1 validated MT5 base remains valid.
- The Python upgrade ladder has been corrected and is now negative under conservative retail-cost assumptions.
- So Monday is **not** a Tier 2 / Tier 2A / Tier 3 rollout day anymore.

Corrected rerun:
- [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_production_rerun_20260329/summary.json)

## Monday Preset

- Use only:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set`

Validated MT5 result:
- `R$14,330`, `PF 1.36`, `DD 3.94%`

## Presets That Are Now Research-Only

- Tier 2:
  - cooldown-only presets
- Tier 2A:
  - ROC-enhanced cooldown presets
- Tier 3:
  - max-hold + ROC presets

Reason:
- corrected-cost exact rerun turned all of them negative full-sample and negative on the holdout test.

## Monday Setup Steps

1. Open the main MT5 terminal and let it sync.
2. Compile:
   - `mt5/experts/custom/WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
3. In Strategy Tester:
   - Expert: `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
   - Symbol: continuous WDO symbol used by the terminal
   - Timeframe: `M1`
   - Model: `Every Tick`
4. Load only the Tier 1 validated preset.
5. Run one clean sanity backtest.
6. If the report is directionally consistent with the saved artifact, attach the EA to paper trading.

## Live Rules

- Position size:
  - `1` contract per `R$100k` max for Monday paper observation
- Spread:
  - `0-1` tick preferred
  - `2` ticks is the hard upper bound
  - `>2` ticks: stand down
- Rollover caution:
  - reduce size or skip the last `3` trading days before contract rollover if spreads or trend quality are weak

## Known Limitations

- Corrected Python upgrades are not currently cost-robust.
- Recent exact windows are mixed:
  - corrected last `60d` for Tier 2A: `R$-753`, `PF 0.6346`
  - corrected last `30d` for Tier 2A: `R$-348`, `PF 0.7114`
  - corrected last `10d` for Tier 2A: `R$269`, `PF 2.4462`
- MT5 tester stability is still imperfect.

## Promotion Rule

Do not promote off the old exact frontier.

Only revisit Tier 2 / Tier 2A / Tier 3 if:

1. a corrected-cost variant turns positive and robust
2. or host-side MT5 validation proves a specific upgrade survives real execution costs

Best honest corrected-cost branch:
- strengthened Tier 2A geometry
- no ROC
- no max-hold
- `SL 1.0`
- `TP 0.48`
- `60m` cooldown
- `AllowFriday=false`
- skip the last contract day
- full sample `R$3,024`, `PF 1.0966`, `DD 7.06%`
- `70/30` test `R$887`, `PF 1.1091`, `DD 7.91%`
- recent `60d` `R$241`, `PF 1.1911`
- keep this in research status until it has host-side MT5 validation

## Corrected-Cost Survivor Watchlist

- The corrected-cost watchlist leader is now the balanced simplified branch above.
- That means:
  - keep it in research
  - do not treat it as a Monday preset
  - use it as the first corrected-cost candidate for host-side MT5 validation

## Monday Recommendation

- Paper-trading default:
  - Tier 1 only
- Paper-trading mindset:
  - validation-first
  - execution-quality-first
  - no scale-up
