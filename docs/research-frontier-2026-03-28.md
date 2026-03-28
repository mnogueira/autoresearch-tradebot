# Research Frontier - 2026-03-28

## Current Production Leader

- Validated MT5 Every Tick leader:
  - `WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4`
  - artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
  - metrics: `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`

This remains the safest paper-trading candidate because it is the best strategy validated in MT5 `Every tick` mode.

## Best Python Candidates Pending MT5

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

- Closest current MT5 preset approximation:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides GPT 5.4.set`
  - exact cooldown preset is now prepared too:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
  - note: the MQ5 cooldown support is wired in, but it still needs one clean MT5 `Every tick` validation run

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
  - PTAX reference prints can matter intraday, which is one plausible reason Friday behaves differently:
    - https://einvestidor.estadao.com.br/ultimas/ibovespa-hoje-ipca-15-leilao-bc-iof/

## Best Next Host-Side Validations

1. Validate the session winner approximation in MT5 `Every tick` once the tester is stable again.
   - the latest main-installation attempt still produced no HTML report in either the workspace output folder or the main terminal AppData tree, only the generated config file
2. Implement and validate the `30-minute cooldown` refinement in MT5 `Every tick`.
   - this is now the highest-priority exact Python candidate because it directly targets the strategy's main weakness: transaction-cost sensitivity
3. If the cooldown is added to the EA, validate the exact session+cooldown winner before spending more time on ATR multiplier tweaks.
4. Validate the Friday-exclusion preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 No Friday GPT 5.4.set`
5. If MT5 remains unstable, prioritize cost-robustness and live-paper safety checks over more entry-family exploration.
6. Do not spend more time on Bollinger mean reversion, inside-bar breakout, or the current EMA crossover family unless the entry/exit mechanics are materially redesigned.

## Production Recommendation

- Paper-trading default:
  - validated MT5 preset `WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4`
- Best exact Python candidate:
  - session winner with hours `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - keep `SkipShortHour13=true`
  - require at least `30 minutes` between filled entries
  - keep `SL 0.84 / TP 0.30`
- Known risks:
  - the edge weakens sharply under higher transaction costs; `2x` spread is still positive, `3x` spread is not
  - MT5 tester instability means the best exact refinements still need one clean host-side validation
- Next paper-trading step:
  - run the validated MT5 preset first
  - validate the new cooldown preset in MT5 `Every tick` next:
    - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 30m GPT 5.4.set`
  - monitor real slippage/spread conditions closely before promoting the exact cooldown refinement
