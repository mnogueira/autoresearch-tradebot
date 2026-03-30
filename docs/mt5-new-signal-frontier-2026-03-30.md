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

`donchian20_high_atr_12_only_tp10_volume`

- Full sample: `R$1,076`, `PF 1.8915`, `DD 1.80%`, `56` trades
- Recent Jan-Mar 2026: `R$462`, `PF 2.1000`, `DD 1.90%`, `17` trades
- Walk-forward: `6/6` test months positive with `PF > 1.0`

This is now the cleanest MT5-native corrected-cost branch:

- daily ATR must be above its 20-day average
- trade only at `12h`
- require a `1.5x` volume spike versus the `20`-bar M1 average
- Donchian-20 breakout aligned with the broader M15 trend
- `SL 1.0 ATR`, `TP 1.0 ATR`

### Other refined variants

- `donchian20_high_atr_10_12_tp10`: `R$1,902`, `PF 1.5125`, `DD 2.09%`, walk-forward `6/6`
- `donchian20_high_atr_10_12_tp12`: `R$1,456`, `PF 1.3607`, `DD 2.75%`, walk-forward `6/6`
- `donchian20_high_atr_10_12_m5_tp12`: `R$1,375`, `PF 1.3406`, `DD 2.75%`, walk-forward `6/6`
- `donchian20_high_atr_10_12_volume_tp12`: `R$1,109`, `PF 1.3392`, `DD 2.48%`, walk-forward `5/6`
- `ensemble_vol_regime_10_11_12_dynamic_tp`: `R$1,848`, `PF 1.3345`, `DD 3.74%`, recent Jan-Mar `R$1,075`, walk-forward `5/6`
- `ensemble_vol_regime_10_11_12_volume`: `R$1,390`, `PF 1.3629`, `DD 5.17%`, recent Jan-Mar `R$853`, walk-forward `4/6`
- `donchian20_high_atr_12_only_tp11_volume`: `R$1,154`, `PF 1.9217`, `DD 1.79%`, recent Jan-Mar `R$352`, walk-forward `6/6`

## Late structural checks

These answered the last open questions around the new winner:

- Explicit `<= 1` tick spread gate was a complete no-op on the winner.
- Adding M5 EMA agreement to the `12h` volume branch was also a no-op.
- Old Stalker-style 15-bar directional efficiency confirmation hurt:
  - `R$777`, `PF 1.7006`, `DD 2.20%`, recent Jan-Mar `R$176`, walk-forward `5/6`
- A `10h + 12h` session ensemble improved recent profit, but weakened the long-sample profile:
  - `R$1,861`, `PF 1.5672`, `DD 2.13%`, recent Jan-Mar `R$874`, walk-forward `5/6`
- Tiny TP/SL nudges confirmed the full-sample ceiling is close but still below `2.0`:
  - best full-sample setting: `SL 1.0 / TP 1.1` with volume gate
  - `R$1,154`, `PF 1.9217`, `DD 1.79%`, recent Jan-Mar `R$352`, walk-forward `6/6`
- Trailing-stop exits were dead ends for the long sample:
  - best trailing variant: `R$469`, `PF 1.4911`, `DD 1.74%`, recent Jan-Mar `R$278`, walk-forward `4/6`

So the clean conclusion is:

- `12h` volume branch is still the best balanced leader
- `10h + 12h` is the best recent-regime booster
- trend-efficiency is not the right confirmation layer for this new Donchian family
- a slightly wider target improves full-sample PF, but weakens the current regime too much to replace the `TP 1.0` leader

## Comparison versus the current M1 combo

Current combo reference, Jan-Mar 2026:

- `R$410`, `PF 1.5640`, `DD 1.75%`

New MT5 leader, Jan-Mar 2026:

- `R$462`, `PF 2.1000`, `DD 1.90%`

Interpretation:

- The new MT5 leader beats the combo on recent profit factor and recent profit.
- Drawdown remains very close to the combo.
- On the longer sample, the new leader is dramatically cleaner than the first MT5 scout ideas and much more robust in walk-forward.
- The broader `10h/12h` Donchian branch is still useful as a higher-throughput fallback, but the `12h` + volume version is the best balanced line.

## Honest conclusion

The MT5-native exploration found a real new candidate:

- high-ATR Donchian breakout
- restricted to `12h`
- filtered by `1.5x` M1 volume spike
- `SL 1.0 ATR`, `TP 1.0 ATR`

It still does **not** clear the aspirational full-sample target of `PF > 2.0`, but it is the first new MT5 signal family to produce all of these at once:

- positive full-sample PnL,
- drawdown under `2%`,
- `6/6` walk-forward pass rate,
- and a recent Jan-Mar regime readout with `PF > 2.0`.

That makes it the current best MT5-native new-signal branch for further refinement.

## Expansion batch

I then pushed the search into genuinely different sleeves:

- `10h` RSI divergence with M5/M15 trend confirmation
- `14h-16h` low-volatility VWAP mean reversion
- M5 Bollinger squeeze breakout
- simple multi-sleeve portfolios mixing the new `10h` and `12h` branches

Results:

- `10h` RSI divergence was the only positive new sleeve:
  - `R$468`, `PF 1.1150`, `DD 7.61%`, recent Jan-Mar `R$638`, `PF 1.5869`, walk-forward `4/6`
- `10h` Donchian + volume did **not** work:
  - `R$-44`, `PF 0.9770`, `DD 3.17%`, recent Jan-Mar `R$-160`, walk-forward `3/6`
- afternoon VWAP mean reversion failed:
  - `R$-512`, `PF 0.8582`, `DD 7.12%`, recent Jan-Mar `R$-319`, walk-forward `1/6`
- M5 Bollinger squeeze breakout failed hard:
  - `R$-768`, `PF 0.3600`, `DD 7.68%`, recent Jan-Mar `R$-62`, walk-forward `1/6`

Portfolio checks:

- equal-weight `10h RSI + 12h Donchian + afternoon reversion` was worse than the `12h` winner:
  - `R$344`, `PF 1.2387`, `DD 2.52%`
- best practical mix was `80%` on the `12h` Donchian winner and `20%` on the `10h` RSI sleeve:
  - `R$954.40`, `PF 1.8795`, `DD 1.46%`
  - recent Jan-Mar `R$497.20`, `PF 2.3881`, `DD 1.53%`

So the new expansion conclusion is:

- the `12h` Donchian volume winner still remains the single best branch
- `10h` wants a different signal family than Donchian, and RSI divergence is the first one that helped at all
- the afternoon session still does not justify a dedicated sleeve
- an `80/20` blend of `12h` Donchian plus `10h` RSI is interesting as a research portfolio, but it does not replace the `12h` winner as the clean primary deployment line
