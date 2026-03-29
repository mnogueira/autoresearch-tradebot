# MT5 Monday Executive Summary - 2026-03-28

## Strategy

- Strategy name:
  - `WDO Stalker Strategy v10.1 Time Filters GPT 5.4`
- Monday default:
  - Tier 1, the validated MT5 `Every Tick` base preset
- First upgrade after clean paper behavior:
  - Tier 2, session winner + `25m` cooldown only
  - keep this as the upgrade even though the new `ROC(5)` agreement line scored better in Python, because Tier 2 is still the simpler path and the ROC-enhanced preset has not yet had host-side MT5 validation

## Best Metrics

- Tier 1 validated MT5 base:
  - `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`
- Tier 2 exact refinement:
  - `R$14,350`, `PF 1.4749`, `DD 3.30%`, composite `3.1158`
- Tier 3 exact refinement:
  - `R$14,420`, `PF 1.4784`, `DD 3.28%`, composite `3.1340`
- Best exact research line, now packaged for MT5 follow-up validation:
  - Tier 3 + `ROC(5)` agreement
  - `R$14,630`, `PF 1.4935`, `DD 3.28%`, composite `3.1676`
- Best simpler ROC follow-up, also packaged:
  - Tier 2 + `ROC(5)` agreement
  - `R$14,560`, `PF 1.4900`, `DD 3.30%`, composite `3.1493`

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
  - Tier 2A, `25m` cooldown + `ROC(5)` agreement
- After another clean week:
  - Tier 3
- Best next ROC validation after the plain Tier 2 line:
  - Tier 2 + `ROC(5)` agreement, because it keeps the simpler cooldown-only structure while still improving the composite
  - it is also now the strongest out-of-sample post-Monday upgrade:
    - test `R$3,440`, `PF 1.4086`, `DD 4.21%`

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
  - interpretation: among the post-Monday upgrades, Tier 2A is now the strongest out-of-sample line
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
  - interpretation: this is the new best exact research candidate, but not the new Monday preset because it still needs host-side MT5 validation
- ATR-adaptive target scaling:
  - exact daily-ATR-scaled TP on Tier 3 was worse than the fixed `0.30 ATR` target
  - interpretation: the target already seems tuned tightly enough for this tape
- Combined promising overlays:
  - confidence-weighted sizing still looked strongest in research-only form
  - but it remains non-deployable because it assumes fractional contract scaling

## Bottom Line

- The strategy is mature.
- Monday should be a cautious paper-validation launch, not a scale-up day.
- The best live-ready answer is still the validated MT5 base, with Tier 2 as the cleanest next upgrade.
- The new `150m` Tier 3 is the strongest exact full-sample line, but the current `60`-day tape did not reward it over Tier 2.
