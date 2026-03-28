# Research Frontier - 2026-03-28

## Current Production Leader

- Validated MT5 Every Tick leader:
  - `WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4`
  - artifact: `artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json`
  - metrics: `R$14,330`, `PF 1.36`, `DD 3.94%`, `WR 80.29%`

This remains the safest paper-trading candidate because it is the best strategy validated in MT5 `Every tick` mode.

## Best Python Candidate Pending MT5

- Session winner:
  - exact hours: `10:00, 11:00, 12:00, 14:00`
  - keep `SkipShortWednesday=true`
  - skip the full `13:00` hour
  - `SL 0.84 / TP 0.30`
  - artifact: `artifacts/outputs/stalker_v10_1_session_refinement_20260328/summary.json`
  - metrics: `R$15,965`, `PF 1.4438`, `DD 4.04%`, `OnTester 3950.819156`

- Closest MT5 preset approximation:
  - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides GPT 5.4.set`

## New Findings From Advanced Follow-ups

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

- The Bollinger mean-reversion family was negative and should not be pursued as-is:
  - `R$-13,586`, `PF 0.8837`, `DD 138.39%`

## Month Robustness

The session winner is positive in every calendar month of the continuous WDO sample, but it is not equally strong:

- strongest months: `March`, `May`, `January`, `August`
- weakest months: `February`, `September`, `October`

Because the parquet is a continuous series, this is calendar-month robustness, not true contract-by-contract robustness.

Yearly stability is still acceptable, but 2025 was weaker than 2024:

- 2024: `R$2,995`, `PF 1.6175`, `DD 3.09%`
- 2025: `R$2,445`, `PF 1.3802`, `DD 4.32%`

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
2. Validate the Friday-exclusion preset:
   - `mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 No Friday GPT 5.4.set`
3. If MT5 remains unstable, implement the EMA crossover family in the exact every-tick engine before trusting its huge prototype numbers.
4. Do not spend more time on Bollinger mean reversion, momentum divergence, or additional breakeven tuning unless the exact EMA family fails.
