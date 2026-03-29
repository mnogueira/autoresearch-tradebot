# MT5 Monday Executive Summary - 2026-03-28

## Strategy

- Strategy name:
  - `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
- Monday default:
  - Tier 1, the validated MT5 `Every Tick` base preset
- First upgrade after clean paper behavior:
  - Tier 2, session winner + `25m` cooldown only
  - keep this as the first upgrade even though the new regime-aware ROC line scored better in Python, because Tier 2 is still the simplest path and the regime-aware preset has not yet had host-side MT5 validation

## Best Metrics

- Tier 1 validated MT5 base:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`
- Tier 2 exact refinement:
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
- Tier 3 exact refinement:
  - `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340`
- Best exact research line, now packaged for MT5 follow-up validation:
  - Tier 2 on range days + Tier 2A `ROC(5)` on prior-day `ADX > 25` trend days
  - `R$14,765`, `PF 1.4951`, `DD 3.28%`, composite `3.1964`
- Best advanced exact research line:
  - Tier 2 on range days + Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days
  - `R$14,835`, `PF 1.4987`, `DD 3.27%`, composite `3.2148`
  - finer window sweep confirmed `ROC(5)` stayed optimal over `ROC(3)`, `ROC(7)`, `ROC(8)`, and `ROC(10)`
  - ADX-threshold sweep also confirmed `25` stayed optimal over `20`, `22.5`, `27.5`, and `30`
- Best exact post-Tier-2 upgrade, now packaged:
  - Tier 2 + `ROC(5)` agreement + `ATR_Length 14` + contract-range lookback `3`
  - `R$15,000`, `PF 1.4873`, `DD 3.15%`, composite `3.2811`
  - exact `70/30` walk-forward:
    - train `R$11,360`, `PF 1.5131`, `DD 3.15%`
    - test `R$3,640`, `PF 1.4213`, `DD 3.51%`
  - recent `60`-trading-day check:
    - `R$200`, `PF 1.1087`, `DD 4.69%`
- Best simpler ROC follow-up, also packaged:
  - Tier 2 + `ROC(5)` agreement
  - `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493`
- Best research-only portfolio sleeve:
  - equal-weight blend of Tier 2 and Tier 2A
  - `R$14,455`, `PF 1.4824`, `DD 3.30%`, composite `3.1372`
  - interpretation: smoother than plain Tier 2, but still not better than Tier 2A itself
- Ceiling assessment:
  - the current signal family appears to top out around composite `3.15` to `3.17`
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
  - Tier 2A, `25m` cooldown + `ROC(5)` agreement + `ATR_Length 14` + contract lookback `3`
- After Tier 2A behaves cleanly:
  - Tier 2B, regime-aware switch:
    - Tier 2 on prior-day `ADX <= 25` range days
    - Tier 2A geometry variant on prior-day `ADX > 25` trend days
- Advanced research preset after that:
  - Tier 2 on prior-day `ADX <= 25` range days
  - Tier 3 `ROC(5)` + `150m` max-hold on prior-day `ADX > 25` trend days
- After another clean week:
  - Tier 3
- Tier 4 remains research-only:
  - equal-weight blend of Tier 2 and Tier 2A
  - this did not beat Tier 2A on the full sample, on the recent `60`-day tape, or by contract-month win count
- Best next ROC validation after the plain Tier 2 line:
  - Tier 2 + `ROC(5)` agreement + `ATR_Length 14` + contract lookback `3`
  - it is now the strongest out-of-sample post-Monday upgrade:
    - test `R$3,640`, `PF 1.4213`, `DD 3.51%`

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
  - `R$30`, `PF 1.0157`, `DD 5.62%`
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
  - Tier 2A test: `R$3,440`, `PF 1.4086`, `DD 4.21%`
  - Tier 3 test: `R$3,175`, `PF 1.3662`, `DD 4.29%`
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
    - `R$14,630`, `PF 1.4935`, `DD 3.28%`, composite `3.1676`
  - exact `70/30` walk-forward still passed:
    - train `R$11,190`, `PF 1.5272`, `DD 3.28%`
    - test `R$3,440`, `PF 1.4086`, `DD 4.21%`
  - but the last `60` trading days were still soft:
    - `R$30`, `PF 1.0157`, `DD 5.62%`
  - interpretation: this remains a strong exact research candidate, but it has now been edged out by the simpler regime-aware Tier 2 / Tier 2A switch and is still not the Monday preset because it needs host-side MT5 validation
- Portfolio sleeve follow-up:
  - equal-weight blend of Tier 2 and Tier 2A:
    - `R$14,455`, `PF 1.4824`, `DD 3.30%`, composite `3.1372`
  - exact `70/30` walk-forward test:
    - `R$3,307.50`, `PF 1.3871`, `DD 4.25%`, composite `2.6224`
  - contract-month behavior:
    - Tier 2A beat Tier 2 in `9` of `61` contract months
    - the portfolio blend beat both in `0` of `61`
  - interpretation: the blend is a valid research smoother, but not strong enough to change the upgrade order
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
  - `ATR_Length 14` + contract-range lookback `3` produced the strongest exact post-Tier-2 result so far:
    - `R$15,000`, `PF 1.4873`, `DD 3.15%`, composite `3.2811`
  - the validation also held up:
    - test `R$3,640`, `PF 1.4213`, `DD 3.51%`
    - recent `60` trading days: `R$200`, `PF 1.1087`, `DD 4.69%`
  - interpretation: this is the new Tier 2A geometry upgrade, but it still needs host-side MT5 validation before it can affect the Monday rollout order

## Bottom Line

- The strategy is mature.
- Monday should be a cautious paper-validation launch, not a scale-up day.
- The best live-ready answer is still the validated MT5 base, with Tier 2 as the cleanest next upgrade.
- The new `150m` Tier 3 is the strongest exact full-sample line, but the current `60`-day tape did not reward it over Tier 2.
