# MT5 New-Signal Frontier (2026-03-30)

This note covers the MT5-native WDO signal exploration that started after the corrected-cost M1 combo plateaued at recent Jan-Mar 2026 results of `R$410`, `PF 1.5640`, `DD 1.75%`.

## Data and cost model

- Symbol: `WDO$N`
- MT5 timeframes fetched directly from the terminal: `M1`, `M5`, `M15`
- Data window: `2025-07-16` to `2026-03-27`
- Cost model: `R$4.00` round-trip per contract
- Walk-forward: `3` month train / `1` month test / `1` month step

## First scout batch

These did not beat the current combo:

- `donchian20_mtf`: `R$57`, `PF 1.0051`, `DD 10.21%`, recent Jan-Mar `R$107`, walk-forward `4/6`
- `vwap_fail_short`: `R$-201`, `PF 0.9618`, `DD 11.70%`, recent Jan-Mar `R$58`, walk-forward `2/6`
- `volume_spike_trend`: `R$-1,333`, `PF 0.9503`, `DD 19.51%`
- `mtf_trend_pullback`: `R$-1,540`, `PF 0.9415`, `DD 19.07%`
- `low_vol_afternoon_mean_revert`: `R$-457`, `PF 0.9278`, `DD 9.54%`

## Refinement batch

The profitable lead came from focusing Donchian breakout on high-volatility days and removing the weak `13h` hour.

### New leader

`donchian20_high_atr_10_12_tp10`

- Full sample: `R$1,902`, `PF 1.5125`, `DD 2.09%`, `137` trades
- Recent Jan-Mar 2026: `R$805`, `PF 1.5310`, `DD 1.86%`, `50` trades
- Walk-forward: `6/6` test months positive with `PF > 1.0`

### Other refined variants

- `donchian20_high_atr_10_12_tp12`: `R$1,456`, `PF 1.3607`, `DD 2.75%`, walk-forward `6/6`
- `donchian20_high_atr_10_12_m5_tp12`: `R$1,375`, `PF 1.3406`, `DD 2.75%`, walk-forward `6/6`
- `donchian20_high_atr_10_12_volume_tp12`: `R$1,109`, `PF 1.3392`, `DD 2.48%`, walk-forward `5/6`
- `ensemble_vol_regime_10_11_12_dynamic_tp`: `R$1,848`, `PF 1.3345`, `DD 3.74%`, recent Jan-Mar `R$1,075`, walk-forward `5/6`
- `ensemble_vol_regime_10_11_12_volume`: `R$1,390`, `PF 1.3629`, `DD 5.17%`, recent Jan-Mar `R$853`, walk-forward `4/6`

## Comparison versus the current M1 combo

Current combo reference, Jan-Mar 2026:

- `R$410`, `PF 1.5640`, `DD 1.75%`

New MT5 leader, Jan-Mar 2026:

- `R$805`, `PF 1.5310`, `DD 1.86%`

Interpretation:

- The new Donchian leader clearly beats the combo on recent profit.
- Drawdown is still very close to the combo.
- Profit factor is slightly lower than the combo on the recent slice.
- On the longer sample, the new leader is materially cleaner than the first MT5 scout ideas and much more robust in walk-forward.

## Honest conclusion

The MT5-native exploration found a real new candidate:

- high-ATR Donchian breakout
- restricted to `10h` and `12h`
- tighter `1.0 ATR` target

It does **not** hit the aspirational target of `PF > 2.0`, but it is the first new MT5 signal family to produce:

- positive full-sample PnL,
- drawdown under `3%`,
- and a clean `6/6` walk-forward pass rate.

That makes it the current best new-signal branch for further refinement.
