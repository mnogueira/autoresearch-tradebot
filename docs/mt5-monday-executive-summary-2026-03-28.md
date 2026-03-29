# MT5 Monday Executive Summary - 2026-03-28

## Strategy

- Strategy name:
  - `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
- Monday default:
  - Tier 1, the validated MT5 `Every Tick` base preset
- First upgrade after clean paper behavior:
  - Tier 2, session winner + `25m` cooldown only
  - keep this as the first upgrade even though the new ATR10/lookback2 Tier 2A scored better in Python, because Tier 2 is still the simplest path and the stronger ROC preset has not yet had host-side MT5 validation

## Best Metrics

- Tier 1 validated MT5 base:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`
- Tier 2 exact refinement:
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
- Tier 3 exact refinement:
  - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
- Best exact static preset-ready research line:
  - Tier 3 + `ROC(5)` agreement + `ATR_Length 10` + contract-range lookback `2`
  - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
  - exact `70/30` walk-forward:
    - train `R$12,020`, `PF 1.5258`, `DD 3.21%`
    - test `R$3,865`, `PF 1.4316`, `DD 3.26%`
  - recent `60`-trading-day check:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
- Best simpler exact research line:
  - Tier 2 + `ROC(5)` agreement + `ATR_Length 10` + contract-range lookback `2`
  - `R$15,970`, `PF 1.5145`, `DD 3.23%`, composite `3.3124`
  - exact `70/30` walk-forward:
    - train `R$12,035`, `PF 1.5403`, `DD 3.23%`
    - test `R$3,935`, `PF 1.4489`, `DD 2.80%`
  - recent `60`-trading-day check:
    - `R$435`, `PF 1.2522`, `DD 3.25%`
- Best advanced exact research line:
  - Tier 2 on range days + Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days
  - `R$14,835`, `PF 1.4987`, `DD 3.27%`, composite `3.2148`
  - finer window sweep confirmed `ROC(5)` stayed optimal over `ROC(3)`, `ROC(7)`, `ROC(8)`, and `ROC(10)`
  - ADX-threshold sweep also confirmed `25` stayed optimal over `20`, `22.5`, `27.5`, and `30`
- Best exact research line overall:
  - use strengthened Tier 2A on the last `1` contract day and on Fridays, with the directional hybrid on all other days
  - `R$16,335`, `PF 1.5244`, `DD 3.18%`, composite `3.4017`
  - exact `70/30` walk-forward:
    - train `R$12,405`, `PF 1.5565`, `DD 3.18%`
    - test `R$3,930`, `PF 1.4436`, `DD 3.26%`
  - recent `60`-trading-day check:
    - `R$480`, `PF 1.2783`, `DD 3.23%`
  - recent `30`-trading-day check:
    - `R$375`, `PF 1.3886`, `DD 3.27%`
  - recent `10`-trading-day check:
    - `R$450`, `PF 3.50`, `DD 1.15%`
  - interpretation:
    - this is now the strongest exact research line overall, but it is still not the Monday upgrade path because it needs contract-cycle switching, weekday-aware routing, and directional sleeve logic that have not been packaged into the MQ5 rollout
    - the corrected rollover-tail sweep still showed `last 1` contract day is the actual local optimum; the new lift comes from routing Fridays back to strengthened Tier 2A
- Best simpler advanced research-only branch:
  - strengthened Tier 2A on Fridays, directional hybrid otherwise
  - `R$16,255`, `PF 1.5205`, `DD 3.19%`, composite `3.3793`
  - exact `70/30` walk-forward:
    - train `R$12,325`, `PF 1.5510`, `DD 3.19%`
    - test `R$3,930`, `PF 1.4436`, `DD 3.26%`
  - recent `60`-trading-day check:
    - `R$480`, `PF 1.2783`, `DD 3.23%`
  - interpretation:
    - this is the cleanest next-week engineering target if we want to implement a simpler advanced routing branch before tackling the full last-contract-day plus Friday version
- Best simpler ROC follow-up, also packaged:
  - Tier 2 + `ROC(5)` agreement
  - `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493`
- Best research-only portfolio sleeve:
  - `25%` strengthened Tier 2A + `75%` advanced weekday-aware directional branch
  - `R$16,243.75`, `PF 1.5219`, `DD 3.19%`, composite `3.3821`
  - interpretation: this is now the strongest research-only smoothing sleeve, but it still remains a later portfolio idea rather than a Monday deployment path
- Ceiling assessment:
  - the current signal family appears to top out around composite `3.21` to `3.31`
  - RSI and MACD directional confirmation both failed to improve the strengthened Tier 2A reference, which is more evidence that `ROC(5)` is the uniquely useful lightweight agreement layer found so far
  - stochastic D centerline did beat the strengthened Tier 2A reference in-sample, but it lost that edge on the `70/30` test and was identical on the recent windows, so it is not a Monday promotion
  - the strongest raw research-only ceiling now comes from trimming top-ATR days on the short sleeve of the advanced directional branch:
    - `0.70x` on high-ATR short days
    - `R$15,618`, `PF 1.5304`, `DD 2.65%`, composite `3.7481`
  - remaining upside is more likely to come from execution quality than from another simple hard filter

## Key Risks

- Spread is the main operational risk.
  - Main strategy break-even is `2` ticks.
  - Do not trade when spread is above `2` ticks.
- Flat commission is not modeled separately in the exact Python harness.
  - Treat spread/slippage as the real live cost risk.
- Low-ADX, range-bound tape is the main underperformance regime.
- The last `3` contract days before rollover are materially weaker.
- MT5 tester stability is imperfect, so paper-trade monitoring matters.

## Recommended Tier

- Monday:
  - Tier 1 only
- After `5` clean paper sessions:
  - Tier 2
- After Tier 2 behaves cleanly:
  - Tier 2A, `28m` cooldown + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`
- After another clean week:
  - Tier 3
- Secondary research branches after Tier 3:
  - regime-aware Tier 2 / Tier 2A switch
  - advanced regime-aware Tier 3 + `ROC(5)` + `150m` max-hold stack
- Tier 4 remains research-only:
  - best current sleeve is `25%` strengthened Tier 2A + `75%` advanced weekday-aware directional branch
  - `R$16,243.75`, `PF 1.5219`, `DD 3.19%`, composite `3.3821`
  - it still does not beat the best single exact research line on full-sample composite, and it is not a live preset because it assumes running multiple sleeves side by side
- strongest exact research-only branch after Tier 3:
  - strengthened Tier 2A on the last `1` contract day and on Fridays, directional hybrid otherwise
  - `R$16,335`, `PF 1.5244`, `DD 3.18%`, composite `3.4017`
  - `70/30` test stayed positive and the recent `60`-day readout improved to `R$480`, `PF 1.2783`, `DD 3.23%`
  - keep this as a next-week engineering candidate, not a Monday promotion
- cleanest simpler advanced routing candidate after Tier 3:
  - strengthened Tier 2A on Fridays, directional hybrid otherwise
  - `R$16,255`, `PF 1.5205`, `DD 3.19%`, composite `3.3793`
  - use this if we want the easiest advanced next-week implementation target before adding contract-cycle logic
- Best next ROC validation after the plain Tier 2 line:
  - Tier 2 + `ROC(5)` agreement + `ATR_Length 10` + contract lookback `2`, refined to `28m` cooldown
  - it is now the strongest out-of-sample post-Monday upgrade:
    - test `R$3,935`, `PF 1.4489`, `DD 2.80%`

## Deployment Steps

1. Open MT5 and let it sync.
2. Compile:
   - `mt5/experts/custom/WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5`
3. In Strategy Tester, use:
   - `M1`
   - `Every Tick`
   - the Tier 1 preset first
4. Confirm live spread is `0-1` tick and stand down above `2`.
5. Run one clean sanity backtest before attaching the EA to paper trading.
6. Keep size at `1` contract per `R$100k` on Monday.

## Recent Context

- Last `30` trading days: soft but still positive
  - `R$40`, `PF 1.0357`, `DD 4.67%`
- Last `60` trading days: Tier 2 and Tier 3 were identical
  - legacy plain Tier 2 and plain Tier 3 max-hold both came in at `R$30`, `PF 1.0157`, `DD 5.62%`
  - the strengthened Tier 2A / Tier 3 local-geometry branches stayed positive:
    - Tier 2A: `R$435`, `PF 1.2522`, `DD 3.25%`
    - Tier 3: `R$450`, `PF 1.2609`, `DD 3.24%`
- Last `10` trading days: strong recovery
  - `R$455`, `PF 4.25`, `DD 0.81%`
  - Tier 2 and Tier 2A were identical in that latest `10`-day window
- Last `5` trading days: still solid
  - `R$110`, `PF 1.7857`, `DD 0.84%`
- Exact last `5` realized trades on the Monday default analog:
  - `4` winners, `1` loser, net `R$35`, `PF 1.25`
  - interpretation: still positive and broadly in-family, but softer than the long-sample average
- Seasonal context on the Tier 2 exact line:
  - `Q2` has been the strongest pooled quarter
  - `Q4` has been the weakest pooled quarter
  - not strong enough to justify a hard calendar filter

## Latest Experiments

- Smart-entry micro-pullbacks `1-2` ticks in `3` bars:
  - both worse than Tier 2
- Cooldown duration sweep:
  - `25m` is the new best deployable exact composite score
  - `40m` is the cleaner PF/DD runner-up
  - the older `30m` line still matters because it already passed the exact `70/30` walk-forward
- `25m + max-hold` follow-up:
  - `150` M1 bars now edge past `120` and become the new best deployable exact composite overall
  - fixed-parameter `70/30` walk-forward on the `150m` line still passed:
    - train `R$11,245`, `PF 1.5236`, `DD 3.28%`
    - test `R$3,175`, `PF 1.3662`, `DD 4.29%`
- Final robustness pass:
  - Tier 1 exact analog test: `R$3,760`, `PF 1.3562`, `DD 4.94%`
  - Tier 2 test: `R$3,175`, `PF 1.3662`, `DD 4.29%`
  - Tier 2A test: `R$3,935`, `PF 1.4489`, `DD 2.80%`
  - Tier 3 test: `R$3,865`, `PF 1.4316`, `DD 3.26%`
  - Tier 2B test: `R$3,345`, `PF 1.3935`, `DD 4.23%`
  - advanced regime-aware Tier 3 test: `R$3,345`, `PF 1.3935`, `DD 4.23%`
  - interpretation: among the post-Monday upgrades, Tier 2A remains the cleanest simpler out-of-sample line, while the advanced regime-aware Tier 3 stack is now the strongest overall exact research line
- Two-bar trend confirmation:
  - clearly negative, rejected
- Volume-weighted entry sizing:
  - research-only and weaker than Tier 2
- One-tick better fill proxy:
  - very strong research-only upside
  - `R$21,925`, `PF 1.7925`, `DD 2.64%`
  - interpretation: execution quality matters a lot
- Next-bar patience / better-next-open entry overlays:
  - both decisively negative
  - interpretation: the current exact strategy already benefits from fast retracement fills, so delaying to the next minute destroys edge rather than improving it
- Plain next-open entry proxy:
  - even worse than the patience filter
  - interpretation: the strategy should not be converted into a wait-for-next-minute execution workflow
- Bollinger squeeze gate on Tier 2:
  - strongly worse than baseline
  - interpretation: low-volatility compression is not the right additional gate for this signal family
- RSI mean-reversion family:
  - decisively negative in the prototype screen
  - interpretation: a fundamentally different mean-reversion edge did not complement this WDO tape
- Volume and extra skip-hour pruning:
  - signal-bar volume gate hurt
  - skip `12h` hurt
  - skip `14h` was nearly flat but still worse than Tier 2
  - skip `15h` was a structural no-op
- ROC family replacement:
  - `ROC(5)` was the closest simpler signal, but still worse than the current Tier 3 on the composite
  - `ROC(10)` and `ROC(20)` were weaker still
  - interpretation: the current trend-efficiency signal remains the better production signal family
- ROC agreement follow-up:
  - keeping trend-efficiency and adding `ROC(5)` directional agreement on top of Tier 3 was the first exact post-Tier-3 improvement
  - exact result:
    - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
  - exact `70/30` walk-forward still passed:
    - train `R$12,020`, `PF 1.5258`, `DD 3.21%`
    - test `R$3,865`, `PF 1.4316`, `DD 3.26%`
  - recent `60` trading days stayed positive:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
  - interpretation: this is now the strongest aggressive exact research branch, but it is still not the Monday preset because the simpler Tier 2A line remains the cleaner first upgrade
- Portfolio sleeve follow-up:
  - earlier equal-weight blend of Tier 2 and Tier 2A:
    - `R$14,455`, `PF 1.4824`, `DD 3.30%`, composite `3.1372`
    - useful as the first proof that portfolio smoothing helps, but no longer the best research-only sleeve
  - stronger advanced sleeve weighting after the Friday-aware directional promotion:
    - `25%` strengthened Tier 2A + `75%` advanced weekday-aware directional branch:
    - `R$16,243.75`, `PF 1.5219`, `DD 3.19%`, composite `3.3821`
  - exact `70/30` walk-forward test:
    - train `R$12,312.50`, `PF 1.5525`, `DD 3.19%`, composite `3.8615`
    - test `R$3,931.25`, `PF 1.4449`, `DD 3.08%`, composite `3.6611`
  - recent `60`-trading-day check:
    - `R$468.75`, `PF 1.2717`, `DD 3.24%`
  - interpretation: portfolio smoothing still helps in research-only form, but even the weighted sleeve does not beat the strongest single advanced branch, so it stays a later portfolio idea rather than a Monday path
- Regime-aware ROC follow-up:
  - Tier 2 on range days + Tier 2A `ROC(5)` on trend days:
    - `R$14,765`, `PF 1.4951`, `DD 3.28%`, composite `3.1964`
  - exact `70/30` walk-forward still passed:
    - train `R$11,420`, `PF 1.5356`, `DD 3.28%`
    - test `R$3,345`, `PF 1.3935`, `DD 4.23%`
  - recent `60`-trading-day check stayed soft and identical to Tier 2 / Tier 2A:
    - `R$30`, `PF 1.0157`, `DD 5.62%`
  - interpretation: this is now the strongest simpler regime-aware research line, but it is still one step too complex to jump ahead of Tier 2 or Tier 2A in the Monday rollout order
- ATR-adaptive target scaling:
  - exact daily-ATR-scaled TP on Tier 3 was worse than the fixed `0.30 ATR` target
  - interpretation: the target already seems tuned tightly enough for this tape
- Combined promising overlays:
  - confidence-weighted sizing still looked strongest in research-only form
  - but it remains non-deployable because it assumes fractional contract scaling
- H1 proxy sanity check:
  - bar-based H1 translation of the retracement family was decisively negative
  - core proxy: `R$-31,120`, `PF 0.4899`, `DD 310.91%`
  - max-hold `3` H1 bars: `R$-31,280`, `PF 0.4804`, `DD 311.55%`
  - interpretation: there is no reason to pivot the strategy family to H1 for Monday or as a near-term research branch
- Core geometry sweep on Tier 2A:
  - lowering `FilterAsPercOfContractMARange` from `0.30` to `0.25` improved the long-sample score:
    - `R$14,775`, `PF 1.4944`, `DD 3.28%`, composite `3.1932`
  - but the same variant was worse in the current regime:
    - last `60` trading days: `R$-225`, `PF 0.8941`, `DD 5.62%`
  - interpretation: good research signal, not a Monday promotion
- Core horizon sweep on Tier 2A:
  - the local refinement around the first horizon winner moved the frontier again:
    - `ATR_Length 10` + contract-range lookback `2`
    - `R$15,840`, `PF 1.4967`, `DD 3.21%`, composite `3.3117`
  - the validation also held up:
    - test `R$3,895`, `PF 1.4350`, `DD 3.26%`
    - recent `60` trading days: `R$480`, `PF 1.2783`, `DD 3.23%`
  - interpretation: this established the stronger ATR10/lookback2 Tier 2A geometry, but it was then refined one more step by the local cooldown sweep
- Tier 2A local cooldown refinement:
  - `28m` cooldown on top of the promoted `ATR10/lookback2 + ROC(5)` line:
    - `R$15,970`, `PF 1.5145`, `DD 3.23%`, composite `3.3124`
  - exact `70/30` walk-forward:
    - train `R$12,035`, `PF 1.5403`, `DD 3.23%`
    - test `R$3,935`, `PF 1.4489`, `DD 2.80%`
  - recent `60`-trading-day check:
    - `R$435`, `PF 1.2522`, `DD 3.25%`
  - interpretation:
    - this is now the promoted Tier 2A preset
    - the improvement over `25m` is small, but it held up on the holdout and kept the recent tape positive
- Tier 3 local-geometry refinement:
  - carrying the same `ATR10/lookback2` geometry into the aggressive ROC/max-hold branch improved that line too:
    - `R$15,885`, `PF 1.4993`, `DD 3.21%`, composite `3.3186`
  - exact `70/30` walk-forward:
    - train `R$12,020`, `PF 1.5258`, `DD 3.21%`
    - test `R$3,865`, `PF 1.4316`, `DD 3.26%`
  - recent `60`-trading-day check:
    - `R$450`, `PF 1.2609`, `DD 3.24%`
  - interpretation:
    - this is now the promoted aggressive Tier 3 research branch
    - it edges Tier 2A on full-sample composite, but Tier 2A remains the cleaner first upgrade because it is simpler and slightly stronger on the out-of-sample test

## Bottom Line

- The strategy is mature.
- Monday should be a cautious paper-validation launch, not a scale-up day.
- The best live-ready answer is still the validated MT5 base, with Tier 2 as the cleanest next upgrade.
- The promoted ATR10/lookback2 Tier 2A with the local `28m` cooldown refinement is now the strongest exact post-Tier-2 line, and the follow-up regime switch still did not beat it.
