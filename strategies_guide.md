# WDO Strategy Research Guide

Comprehensive guide for the autoresearch agent. Contains strategies from three sources:
1. **Expert strategies** — From WDO trading expert (Joabe / Sniper / Clarian Solutions)
2. **MT5 optimized code** — Actual backtested MQL5 implementations with tuned parameters
3. **YouTube indicator research** — 50+ indicators tested systematically

---

## EXPERT STRATEGIES (Priority — implement these first)

### Strategy 1: SMA 108 Pullback

**Concept:** Trend-following. Price breaks above/below SMA 108, then pulls back to the MA for entry.

**Rules (from expert notes):**
- Timeframe: 5-minute bars
- Indicator: SMA(108)
- Entry: candle closes above SMA 108 -> wait for pullback (price touches the SMA) -> BUY
- Entry: candle closes below SMA 108 -> wait for pullback (price touches the SMA) -> SELL
- Trading hours: 9:00 to 13:00 (morning session only)
- Stop loss: 5 points (R$50)
- Take profit: 1% of SMA value as target
- Trailing stop: EMA(13) with 0.25 point backstep (Wilder's trailing)
- Filter: "meia perna" — wait for market to move at least half the average daily range before entering

**MT5 optimized version (Extreme v1.0):**
- SMA length was optimized to 180 (vs original 108)
- Bands at 1% and 0.25% incremental from SMA
- Up to 3 bands traded (grid entries)
- SL: 0.5% of average position price

**Implementation notes:**
- The SMA 108 is a WDO-specific "magic number" — approximately 1 full trading day of 5-min bars (108 bars × 5 min = 540 min = 9 hours)
- The pullback entry avoids chasing breakouts and gets better fills
- Morning-only filter avoids choppy afternoon sessions

---

### Strategy 2: Stalker (Dynamic Fibonacci Retracement)

**Concept:** Trend continuation. After market establishes direction (via "meia perna"), enter on retracements expecting continuation.

**Rules (from expert notes):**
- Timeframe: 15-minute bars
- Win rate: 30-40% (low) but payoff ratio 4:1 (high)
- "The question is not how many points, but how many stops does each winner pay"

**Entry logic:**
1. Calculate "meia perna" (half-leg) = average daily range of current contract / 2
   - First 5 days of new contract: use previous contract's average
   - After day 6: use current contract's average
   - Contract changes on first business day of each month
2. Wait until today's range >= meia perna
3. Once triggered:
   - If range made to the downside (bearish): place SELL limit at retracement level
   - If range made to the upside (bullish): place BUY limit at retracement level
4. Retracement levels: test both 20% and 30% separately

**Example (from notes):**
- Daily range so far: min=5427, max=5500 -> range=73 points
- Meia perna = 52.5 points -> 73 > 52.5 -> ACTIVE for sells
- 30% retracement from low: 5427 + (73 × 0.30) = 5449 -> SELL at 5449
- 20% retracement from low: 5427 + (73 × 0.20) = 5442 -> SELL at 5442

**Stop/Target:**
- SL: 1 × ATR(20) on 15-min chart (round to nearest 0.5)
- TP: 4 × SL
- Example: ATR=15 -> SL=15pts (R$150) -> TP=60pts (R$600)

**Re-entry rule:** After being stopped out, NO new entries until price makes new high/low. Then recalculate retracement from new extremes.

**Trading hours:** Full session (9:00-18:00), close 2-3 min before close.

**MT5 optimized version (Stalker v9.0):**
- Retracement: 0.25 (25% — compromise between 20% and 30%)
- Filter: 0.30 (30% of contract MA range)
- SL: 0.78 × ATR(20) on M15
- TP: 0.36 × ATR(20) on M15 (NOTE: optimizer shrunk TP dramatically vs original 4:1)
- Previous contract lookback: 5 days
- Close positions 5 min before 18:00

**Partial exit options (from expert):**
1. Half position exit at ATR multiplier or retracement level
2. Trailing stop options: Wilder MA(13), EMA(9), or HiLo Activator (Robert Krausz)

---

### Strategy 3: VWAP Tunnel (Mean Reversion)

**Concept:** Mean reversion around daily VWAP with asymmetric bands.

**Rules (from expert notes):**
- Timeframe: 15-minute bars (entries), VWAP calculated on 5-min
- Indicator: Daily VWAP with percentage-based bands
- Upper bands: +0.6% (band 1) and +1.2% (band 2) from VWAP
- Lower bands: -0.65% (band 1) and -1.3% (band 2) from VWAP
- NOTE: bands are asymmetric (lower bands wider) — "veio de um fundo foda" (backed by solid research)

**Entry:**
- BUY when price touches lower band 2 (-1.3%)
- SELL when price touches upper band 2 (+1.2%)
- Counter-trend (mean reversion) strategy

**Stop/Target:**
- SL: 1 × ATR(108) on 5-min chart
- TP: 2-3 × ATR (expert uses 1:3 risk-reward)
- Alternative exit: price reaches band 1 (first band)

**MT5 optimized version (VWAP Tunnel v1.0):**
- Confirmed: UBand2=1.2%, UBand1=0.6%, LBand1=0.65%, LBand2=1.3%
- ATR: Period M5, Length 108
- SL: 1.0 × ATR, TP: 3.0 × ATR
- VWAP calculated using (Close+High+Low)/3 price type
- Close 5 min before 18:00

**Key detail from screenshot:** The first image shows the VWAP tunnel with:
- Yellow dotted lines (outer bands)
- Green lines (VWAP and inner levels)
- Pink/magenta lines (possibly SMA or other MA)
- Price oscillating between bands with entries at extremes

---

### Strategy 4: Extreme (SMA Channel Grid)

**Concept:** Mean reversion using SMA envelope bands with grid entries.

**Rules (from expert notes):**
- Timeframe: 5-minute bars
- Indicator: SMA(108) with percentage bands
- First band: 1% from SMA
- Additional bands: every 0.25% further
- "Perna inteira" (full leg = contract avg daily range) used as reference

**Entry:**
- At market open (first minute): calculate SMA 108 and all bands
- Identify the nearest band with best price
- Place limit orders at that band AND the next 2 bands (max 3 entries same direction)
- Fixed contracts per entry

**Stop/Target:**
- SL: 0.5% of average position price
- TP: exit at the 1% band (mean reversion to first band)

**MT5 optimized version (Extreme v1.0):**
- SMA length: 180 (optimized from 108)
- First band: 1.0%, Other bands: 0.25%
- Bands traded: 3
- SL: 0.5% of last band price
- Close 5 min before 18:00

---

## YOUTUBE INDICATOR RESEARCH — TOP PERFORMERS

### Winner Indicators (>60% win rate in testing)

| Indicator | Win Rate | Trades | Type | Notes |
|-----------|----------|--------|------|-------|
| Schaff Trend Cycle (STC) | 100% | 9 | Momentum | MACD + Stochastic cycle |
| Trend Tracker | 88% | 8 | Trend | Only longs tested |
| Coppock Curve | 85% | 7 | Momentum | Long-term momentum |
| DeMark Reversal Points | 83% | - | Reversal | Price exhaustion |
| Cipher B | 83% | - | Composite | Multi-indicator |
| MOST (Moving Stop) | 83% | - | Trend/Trail | Trailing stop variant |
| Cluster Algorithm 1 | 83% | - | Composite | Works on 15-min |
| 123 Trend Continuation | 80% | 10 | Trend | Continuation patterns |
| EMA Distance | 80% | 10 | Mean Reversion | Distance from EMA |
| Ultimate Trader Oscillator | 78% | 27 | Momentum | High volume + accuracy |
| DIDI Index | 75% | - | Trend | Brazilian indicator |
| Tillson T3 | 73% | 11 | Trend | Superior smoothing |
| RSI Inverse Fisher Transform | 72% | 18 | Momentum | Normalized RSI |
| Kijun-Sen Zero Line | 71% | - | Trend | Ichimoku component |
| SSL Channel | 70% | - | Trend | SMA-based channel |

### Best Volatility/Volume Filters
- **Damiani Volatmeter** — Best overall range filter, identifies trending vs ranging
- **Exertion Meter** — Measures market effort, good with EMA 9
- **Range Identifier** — Built-in no-trade zones for choppy markets
- **Money Flow Indicator** — 100% accurate but too few signals (use as filter only)

### Key Findings from Testing
- **EMA > SMA** for moving averages
- **Color-shift method > crossover method > price-break method** for signal generation
- Multi-line crosses filter chop better than 2-line crosses
- Combine: Entry indicator + Confirmation + Volume/Volatility filter + Exit indicator

### Best Combination Ideas (NNFX Framework)
- **Entry:** Donchian / STC / Tillson T3
- **Confirmation:** Stochastic / TSI / SSL
- **Range filter:** Damiani Volatmeter / Range Identifier
- **Exit:** JMA+TS trailing / SSL / Gann HiLo Activator / EMA 13

---

## IMPLEMENTATION PRIORITY FOR AUTORESEARCH AGENT

### Phase 1: Expert Strategies (highest priority — proven on WDO)
1. Stalker 25% retracement with meia perna filter
2. Stalker 20% and 30% variants
3. VWAP Tunnel mean reversion
4. SMA 108/180 pullback
5. Extreme SMA channel grid

### Phase 2: Top YouTube Indicators (adapted for WDO M5)
6. Schaff Trend Cycle (STC) entry + Damiani Volatmeter filter
7. EMA Distance mean reversion (similar to Extreme concept)
8. DIDI Index (Brazilian, may work well on WDO)
9. Tillson T3 trend following
10. RSI Inverse Fisher Transform + SSL confirmation

### Phase 3: Hybrid Strategies (combine expert + indicators)
11. Stalker entries + HiLo Activator trailing stop
12. VWAP Tunnel + Damiani Volatmeter filter (skip trades in low-vol)
13. SMA 108 pullback + Stochastic confirmation + EMA 13 trailing
14. Multi-timeframe: M15 trend (STC) + M5 entry (Stalker retracement)

### Phase 4: Parameter Optimization
15. Sweep retracement levels: 15%, 20%, 25%, 30%, 35%
16. Sweep ATR multipliers for SL/TP
17. Sweep SMA lengths: 72, 108, 144, 180, 216
18. Sweep VWAP band widths
19. Time-of-day filters: morning only, afternoon only, full day
20. Meia perna threshold: 40%, 50%, 60% of average range

---

## WDO CONTRACT REFERENCE

### Contract Calendar
| Month | Letter | Example 2026 |
|-------|--------|-------------|
| Jan | F | WDOF26 |
| Feb | G | WDOG26 |
| Mar | H | WDOH26 |
| Apr | J | WDOJ26 |
| May | K | WDOK26 |
| Jun | M | WDOM26 |
| Jul | N | WDON26 |
| Aug | Q | WDOQ26 |
| Sep | U | WDOU26 |
| Oct | V | WDOV26 |
| Nov | X | WDOX26 |
| Dec | Z | WDOZ26 |

- Contract expires on first business day of each month
- New contract starts trading on last business day of previous month at 9:00
- Day traders: just switch contracts on expiry day
- For meia perna calc: first 5 days use previous contract's average, then switch

### Session Hours
- Regular: 9:00 - 18:00 BRT (no daylight saving)
- With daylight saving: 9:00 - 18:30 BRT
- Day trade close: 2-5 min before session end
- Pre-market: ~8:55

### Capital / Risk
- Expert recommends: R$5,000 per mini contract
- Stop at 70% of account (maximum loss before stopping)
- Point value: R$10 per point
- Tick size: 0.5 points (R$5 per tick)
