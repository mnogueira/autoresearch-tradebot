# MT5 New-Signal Frontier (2026-03-30)

This note covers the MT5-native WDO signal exploration that started after the corrected-cost M1 combo plateaued at recent Jan-Mar 2026 results of `R$410`, `PF 1.5640`, `DD 1.75%`.

## Offline 5-year extension

Once the larger offline parquet files were available, I extended the search onto the longer `M5` / `M15` history:

- `data/wdo_m5_2021_2026.parquet`: Sep 2022 to Mar 2026
- `data/wdo_m15_2021_2026.parquet`: Mar 2021 to Mar 2026
- cost model kept at `R$4.00` round-trip
- walk-forward changed to `1y` train / `3m` test

### VWAP z-score mean reversion

This entire family failed the new bar:

- best case `vwap_z12_late_z20`: `R$-519`, `PF 0.8999`, `DD 11.44%`, walk-forward `6/10`
- `vwap_z24_afternoon_z25`: `R$-1,111`, `PF 0.8460`, `DD 22.82%`
- `vwap_z24_afternoon_z20`: `R$-1,792`, `PF 0.7990`, `DD 25.28%`
- `vwap_z12_afternoon_z20_noflat`: `R$-15,391`, `PF 0.7287`, `DD 159.63%`

The useful conclusion is that simple intraday VWAP fade logic is not robust enough on the longer WDO history, even after restricting it to low-volatility days and flatter M15 regimes. It is now documented as a dead end, not a deployment path.

### Bollinger squeeze breakout on M5

This family also failed decisively on the longer offline sample:

- best case `bb30_q20_ema_on`: `R$-3,712`, `PF 0.8213`, `DD 37.73%`, walk-forward `2/10`
- `bb30_q30_ema_off`: `R$-9,945`, `PF 0.8053`, `DD 102.33%`
- `bb20_q30_ema_on`: `R$-9,248`, `PF 0.7333`, `DD 93.96%`
- `bb20_q20_ema_off`: `R$-14,036`, `PF 0.7179`, `DD 144.15%`
- `bb20_q20_ema_on`: `R$-8,258`, `PF 0.6953`, `DD 83.48%`
- `bb20_q10_ema_on`: `R$-6,461`, `PF 0.6443`, `DD 66.66%`

The useful conclusion is that M5 compression-breakout logic is not robust enough for WDO under corrected costs, even with M15 EMA confirmation and multiple squeeze thresholds. It joins VWAP mean reversion as a dead end, not a deployment candidate.

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

## Portfolio follow-up

The next step was to formalize the only sleeve pairing that still looked alive:

- `12h` high-ATR Donchian breakout with volume gate
- `10h` high-ATR RSI divergence with `TP 0.8`

This was tested as a daily-allocation portfolio, where the two sleeves run independently and capital is split between them.

### Best portfolio candidate

`70%` on the `12h` Donchian winner + `30%` on the `10h` RSI sleeve

- full sample: `R$910.10`, `PF 2.4247`, `DD 1.29%`
- recent Jan-Mar 2026: `R$534.60`, `PF 3.4168`, `DD 1.33%`
- walk-forward: `6/6` passed

Closest alternatives:

- `75/25`: `R$937.75`, `PF 2.4219`, `DD 1.37%`, recent `R$522.50`, `PF 3.2377`, walk-forward `6/6`
- `80/20`: `R$965.40`, `PF 2.4193`, `DD 1.46%`, recent `R$510.40`, `PF 3.0765`, walk-forward `6/6`
- `60/40`: `R$854.80`, `PF 2.4134`, `DD 1.11%`, recent `R$558.80`, `PF 3.8423`, walk-forward `6/6`

### Comparison

Standalone `12h` winner:

- full sample: `R$1,076`, `PF 1.8915`, `DD 1.80%`
- recent Jan-Mar 2026: `R$462`, `PF 2.1000`, `DD 1.90%`

Old corrected-cost M1 combo:

- full sample: `R$3,317`, `PF 1.1334`, `DD 8.07%`
- recent Jan-Mar 2026: `R$410`, `PF 1.5640`, `DD 1.75%`

So the honest state of the frontier is now:

- the best **single** MT5-native sleeve is still the `12h` Donchian volume winner
- the best **portfolio** MT5-native deployment candidate is the `70/30` blend of `12h` Donchian + `10h` RSI divergence
- this is the first MT5-native branch in the repo that clears the portfolio target of `PF > 2.0` and `DD < 3%` on the full sample while also staying strong in Jan-Mar 2026
