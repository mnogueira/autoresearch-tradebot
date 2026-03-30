# MT5 Corrected-Cost Deployment Sheet - 2026-03-29

## Executive Call

- Monday live paper trading should still start with the validated MT5 Tier 1 base preset.
- The corrected-cost stacked combo is the best exact post-Monday validation target, but it is **not** a one-click MT5 preset yet because three parts of the logic are not directly supported in the current EA.
- Monday Tier 1 preset path:
  - [WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set](/c:/Dev/autoresearch-tradebot/mt5/profiles/tester/WDO%20Stalker%20Strategy%20v10.1%20Surgical%20SLTP%20sl0p84%20tp0p3%20GPT%205.4.set)

## Best Corrected-Cost Leader

- Variant:
  - long ATR-prune + short hours `10/11/12`
  - no ROC
  - no max-hold
  - `SL 1.0`
  - `TP 0.48`
  - `60m` cooldown
  - Friday off
  - skip last contract day
- Exact numbers:
  - full sample: `R$3,317`, `PF 1.1334`, `DD 8.07%`
  - `70/30` test: `R$1,580`, `PF 1.2615`, `DD 6.02%`
  - rolling walk-forward: `4/7` test folds passed

## Python To MQ5 Parameter Map

| Python logic | Value | MQ5 input | Status |
| --- | ---: | --- | --- |
| Contracts per trade | `1.0` | `ContractsPerTrade` | direct |
| Filter as % of contract MA range | `0.30` | `FilterAsPercOfContractMARange` | direct |
| Days to keep previous contract MA range | `2` | `NumDaysToConsiderPreviousContractMARange` | direct |
| Retracement level | `0.25` | `RetracementLevel` | direct |
| Entry start hour | `10` | `EntryStart_Hour` | direct |
| Entry start minute | `0` | `EntryStart_Minute` | direct |
| Last entry hour | `14` | `LastEntry_Hour` | direct |
| Last entry minute | `30` | `LastEntry_Minute` | direct |
| Cooldown | `60m` | `MinMinutesBetweenEntries` | direct |
| Monday enabled | `true` | `AllowMonday` | direct |
| Tuesday enabled | `true` | `AllowTuesday` | direct |
| Wednesday enabled | `true` | `AllowWednesday` | direct |
| Thursday enabled | `true` | `AllowThursday` | direct |
| Friday enabled | `false` | `AllowFriday` | direct |
| Skip all Wednesday trades | `false` | `SkipWednesday` | direct |
| Skip short Wednesday trades | `true` | `SkipShortWednesday` | direct |
| Skip all `13h` trades | `false` | `SkipHour13` | direct |
| Skip short `13h` trades | `true` | `SkipShortHour13` | direct |
| Skip all `14h` trades | `false` | `SkipHour14` | direct |
| Trend-efficiency window | `15` | `TrendEfficiencyWindowMinutes` | direct |
| Apply trend-efficiency to longs | `true` | `ApplyTrendEfficiencyFilterToLongs` | direct |
| Apply trend-efficiency to shorts | `false` | `ApplyTrendEfficiencyFilterToShorts` | direct |
| Minimum directional trend-efficiency | `0.333333` | `MinDirectionalTrendEfficiency15m` | direct |
| Signal-volume window | `30` | `VolumeWindowMinutes` | direct |
| Apply signal-volume to longs | `false` | `ApplyVolumeFilterToLongs` | direct |
| Apply signal-volume to shorts | `true` | `ApplyVolumeFilterToShorts` | direct |
| Minimum signal-volume sum | `30000` | `MinSignalVolumeWindowSum` | direct |
| Relative-volume lookback | `20` | `RelativeVolumeLookbackDays` | direct |
| Apply relative-volume to longs | `false` | `ApplyRelativeVolumeFilterToLongs` | direct |
| Apply relative-volume to shorts | `false` | `ApplyRelativeVolumeFilterToShorts` | direct |
| Minimum relative volume | `0.0` | `MinRelativeVolumeAtTime` | direct |
| Stop ATR multiplier | `1.0` | `SL_ATRMultiplier` | direct |
| Target ATR multiplier | `0.48` | `TP_ATRMultiplier` | direct |
| ATR timeframe | `M15` | `ATRTimeFrame` | direct |
| ATR length | `10` | `ATR_Length` | direct |
| Market close hour | `18` | `MarketClose_Hour` | direct |
| Market close minute | `0` | `MarketClose_Minute` | direct |
| Minutes before close | `5` | `MinutesBeforeMarketCloseToClosePositions` | direct |
| ROC agreement | disabled | `UseROCAgreementFilter=false` | direct |
| Max-hold | disabled | `MaxMinutesInTrade=0` | direct |
| Prior-day ADX gate | disabled | `UsePriorDayADXFilter=false` | direct |

## Exact Python Logic Not Supported In Current MQ5 EA

1. Long ATR-prune:
   - Python prunes only **long** entries on top-ATR tercile days, using prior-day `ATR14` versus its rolling `60`-day `67th` percentile.
   - The current EA has no ATR-percentile regime gate and no long-only ATR regime input.
2. Short-hour routing:
   - Python allows shorts only in `10/11/12`, while longs can still trade `14h`.
   - The current EA can skip short `13h`, but it has no `SkipShortHour14` or a general short-hour whitelist.
3. Skip last contract day:
   - Python uses contract-cycle buckets and removes the final contract day.
   - The current EA has no contract-rollover calendar logic.

## Python vs MQ5 Logic Discrepancies

1. Costs:
   - Python exact metrics already subtract `ROUND_TRIP_COST_BRL = 11.0` per trade.
   - MQ5 live paper trading will realize broker fees and slippage externally; the EA does not explicitly model flat round-trip cost.
2. Intrabar execution:
   - Python exact uses synthetic every-tick paths generated from M1 OHLCV.
   - MQ5 tester/live runs on broker ticks or tester modeling, so fill paths will differ.
3. Spread handling:
   - Historical Python spread is compressed to `0/1` ticks, so spread is mostly a live guardrail, not an alpha feature.
   - For live paper trading, keep `MaxAllowedEntrySpreadTicks <= 2` even though the corrected-cost combo backtest itself did not use a spread gate.

## Parameter Sheet For The Closest MQ5 Approximation

- Use these direct EA inputs if you want the closest currently-supported approximation:
  - `ContractsPerTrade=1`
  - `FilterAsPercOfContractMARange=0.30`
  - `NumDaysToConsiderPreviousContractMARange=2`
  - `RetracementLevel=0.25`
  - `EntryStart_Hour=10`
  - `EntryStart_Minute=0`
  - `LastEntry_Hour=14`
  - `LastEntry_Minute=30`
  - `MinMinutesBetweenEntries=60`
  - `AllowFriday=false`
  - `SkipShortWednesday=true`
  - `SkipShortHour13=true`
  - `TrendEfficiencyWindowMinutes=15`
  - `ApplyTrendEfficiencyFilterToLongs=true`
  - `ApplyTrendEfficiencyFilterToShorts=false`
  - `MinDirectionalTrendEfficiency15m=0.333333`
  - `VolumeWindowMinutes=30`
  - `ApplyVolumeFilterToLongs=false`
  - `ApplyVolumeFilterToShorts=true`
  - `MinSignalVolumeWindowSum=30000`
  - `SL_ATRMultiplier=1.0`
  - `TP_ATRMultiplier=0.48`
  - `ATRTimeFrame=PERIOD_M15`
  - `ATR_Length=10`
  - `MaxMinutesInTrade=0`
  - `UseROCAgreementFilter=false`
  - `UsePriorDayADXFilter=false`
  - `MaxAllowedEntrySpreadTicks=2`
- But this is still only an approximation because the current EA cannot express the long ATR-prune, the short `14h` block, or the last-contract-day skip.

## Daily PnL Expectations Under Corrected Costs

- Based on the exact corrected-cost stacked combo:
  - mean daily PnL: `R$5.04`
  - daily PnL std dev: `R$85.39`
  - best day: `R$218` on `2022-11-01`
  - worst day: `R$-377` on `2023-03-30`
- Practical interpretation:
  - the strategy is low-edge and noisy day to day
  - a typical single-day move is small relative to its noise band
  - the desk should expect many quiet days and occasional sharp down days even in the viable branch

## Trade Frequency

- Average trades per all trading days: `0.6720`
- Average trades per active day: `1.2736`
- Active days: `658`

## Deployment Recommendation

1. Monday paper trading:
   - deploy the validated MT5 Tier 1 base preset only
2. First corrected-cost MT5 validation target after Monday:
   - implement the missing routing logic, then validate the corrected-cost stacked combo
3. If implementation simplicity matters more than the last edge gain:
   - validate the long-ATR-prune-only fallback first
