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

## Structural Follow-Up Call

- The strongest lightweight overlay on the M1 combo is now an `M5 EMA20` confirmation:
  - full sample: `R$3,812`, `PF 1.1576`, `DD 7.37%`
  - `70/30` test: `R$1,534`, `PF 1.2578`, `DD 5.88%`
  - recent Jan-Mar `2026`: exactly tied with the base combo at `R$410`, `PF 1.5640`, `DD 1.75%`
- The most promising structural alternative is an `M5` proxy of the same corrected-cost combo logic:
  - full sample: `R$6,945`, `PF 1.3841`, `DD 5.18%`, `725` trades
  - `70/30` test: `R$1,605`, `PF 1.3232`, `DD 7.43%`
  - recent Jan-Mar `2026`: `R$-9`, `PF 0.9900`, `DD 3.54%`
- Honest read:
  - the `M5 EMA20` overlay improves the long sample and holdout, but it does **not** improve the current regime
  - `M5` is the strongest longer-sample structural direction I tested
  - but it lost the recent three-month regime check while the current M1 stacked combo stayed positive
  - so it is **not** the new Monday deployment leader
- Structural artifact:
  - [summary.json](/c:/Dev/autoresearch-tradebot/artifacts/outputs/stalker_v10_1_corrected_cost_structural_followups_20260329/summary.json)

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
4. M5 proxy deployment:
   - The current EA and exact harness are both M1-native.
   - A true M5 deployment path would need a dedicated M5 implementation or a carefully validated chart-timeframe translation.

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

## M5 Proxy Parameter Sheet

- The `M5` proxy used the same corrected-cost combo logic and the same core parameter values:
  - `ContractsPerTrade=1`
  - `FilterAsPercOfContractMARange=0.30`
  - `NumDaysToConsiderPreviousContractMARange=2`
  - `RetracementLevel=0.25`
  - `EntryStart_Hour=10`
  - `LastEntry_Hour=14`
  - `MinMinutesBetweenEntries=60`
  - `AllowFriday=false`
  - `SL_ATRMultiplier=1.0`
  - `TP_ATRMultiplier=0.48`
  - `ATRTimeFrame=PERIOD_M15`
  - `ATR_Length=10`
- The only structural difference is the execution bar set:
  - Python resampled the base `M1` tape into `M5` bars and then ran the same logic on that lower-frequency stream
- Deployment implication:
  - this is **not** a parameter-only MT5 switch
  - it would need a dedicated `M5` chart/test harness or a separately validated EA implementation

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
4. If we want the next structural research branch after that:
   - validate the M5 proxy as a separate implementation, not as a quiet swap of the current M1 deployment
