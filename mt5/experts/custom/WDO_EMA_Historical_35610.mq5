#property strict
#property version   "2.00"
#property description "Historical port of the final EMA champion with Python test_sharpe=3.5610."
#property description "Strategy: EMA(8/34) crossover + EMA(220) trend + ADX(14)>20"
#property description "RSI(7)>65/<40 + Hurst(100)>0.50 + VWAP direction + VR(3/20)<2.0"
#property description "ATR(20)x2 trailing stop + TRIX(12) rolling median exit + skip 12h/13h"
#property description "Includes a synthetic parity engine that mirrors the Python backtest."

#include <Trade/Trade.mqh>

CTrade trade;

input double InpLots = 1.0;
input long   InpMagicNumber = 35610;
input int    InpDeviationPoints = 20;
input bool   InpRequireM5 = true;
input int    InpHistoryBars = 3000;
input bool   InpMirrorRealOrders = false;

input int    InpEmaFast = 8;
input int    InpEmaSlow = 34;
input int    InpTrendWindow = 220;
input int    InpRsiWindow = 7;
input double InpRsiLong = 65.0;
input double InpRsiShort = 40.0;
input int    InpAdxWindow = 14;
input double InpAdxThreshold = 20.0;
input int    InpAtrWindow = 20;
input double InpAtrMult = 2.0;
input int    InpTrixWindow = 12;
input int    InpTrixMedianWindow = 500;
input int    InpTrixMedianMinPeriods = 100;
input int    InpHurstWindow = 100;
input double InpHurstThreshold = 0.50;
input bool   InpUseVwap = true;
input int    InpVrShortWindow = 3;
input int    InpVrLongWindow = 20;
input double InpVrMax = 2.0;
input bool   InpSkipHour12 = true;
input bool   InpSkipHour13 = true;
input int    InpEntryCutoffHour = 14;
input int    InpEntryCutoffMinute = 55;
input int    InpLastWindowHour = 17;
input int    InpLastWindowMinute = 25;
input bool   InpUseDataWindow = false;
input datetime InpDataWindowStart = 0;
input datetime InpDataWindowEnd = 0;
input bool   InpUseExternalParityCsv = false;
input string InpExternalParityCsvName = "wdo_m5_python_parity.csv";
input bool   InpEnableParityMetrics = true;
input bool   InpWriteParityFiles = true;
input bool   InpUseCommonFiles = true;
input double InpPointValueBrl = 10.0;
input double InpRoundTripCostBrl = 11.0;
input double InpInitialEquityBrl = 100000.0;
input string InpParityOutputPrefix = "wdo_ema_35610_parity";

const int ARRAY_RESERVE = 512;

struct EmaAccumulator
{
   int    valid_count;
   double value;
};

datetime g_last_bar_time = 0;
datetime g_last_processed_closed_time = 0;
string   g_last_status = "";
bool     g_state_ready = false;
bool     g_parity_finalized = false;
bool     g_external_parity_ready = false;

datetime g_times[];
int      g_dates[];
int      g_hours[];
int      g_minutes[];
double   g_close[];
double   g_high[];
double   g_low[];
double   g_volume[];
double   g_returns[];
double   g_ema_fast[];
double   g_ema_slow[];
double   g_ema_trend[];
double   g_rsi[];
double   g_adx[];
double   g_atr[];
double   g_trix[];

double   g_true_range[];
double   g_pos_dm[];
double   g_neg_dm[];
double   g_dx[];

EmaAccumulator g_ema_fast_state;
EmaAccumulator g_ema_slow_state;
EmaAccumulator g_ema_trend_state;
EmaAccumulator g_trix_ema1_state;
EmaAccumulator g_trix_ema2_state;
EmaAccumulator g_trix_ema3_state;

int    g_rsi_count = 0;
double g_rsi_avg_up = 0.0;
double g_rsi_avg_down = 0.0;

int    g_atr_count = 0;
double g_atr_sum_tr = 0.0;
double g_atr_value = 0.0;

double g_adx_smoothed_tr = 0.0;
double g_adx_smoothed_pos = 0.0;
double g_adx_smoothed_neg = 0.0;
double g_adx_value = 0.0;

bool   g_prev_ema3_valid = false;
double g_prev_ema3_value = 0.0;

int    g_vwap_date = 0;
double g_vwap_cum_tp_vol = 0.0;
double g_vwap_cum_vol = 0.0;

int    g_position = 0;
double g_peak = 0.0;
int    g_raw_last = 0;

int      g_parity_position = 0;
double   g_parity_entry_price = 0.0;
datetime g_parity_entry_time = 0;
int      g_parity_prev_date = 0;
int      g_parity_last_seen_date = 0;
int      g_parity_trading_days = 0;
int      g_parity_bar_count = 0;
int      g_parity_position_bar_count = 0;
datetime g_parity_last_bar_time = 0;
double   g_parity_last_fill_price = 0.0;

double   g_parity_trade_pnls[];
datetime g_parity_trade_entries[];
datetime g_parity_trade_exits[];
int      g_parity_trade_directions[];
double   g_parity_trade_entry_prices[];
double   g_parity_trade_exit_prices[];

struct ParityMetrics
{
   double sharpe;
   double profit_factor;
   double max_drawdown_pct;
   double win_rate;
   int    total_trades;
   double net_profit_brl;
   double avg_profit_per_trade;
   double avg_win_brl;
   double avg_loss_brl;
   int    max_consec_losses;
   double exposure_pct;
};

ParityMetrics g_parity_metrics;

struct CsvBar
{
   datetime time;
   double   open;
   double   high;
   double   low;
   double   close;
   double   volume;
   double   spread;
};

double MissingValue()
{
   return DBL_MAX;
}

bool IsMissing(const double value)
{
   return (value == MissingValue());
}

string SanitizeToken(string value)
{
   string sanitized = value;
   StringReplace(sanitized, "\\", "_");
   StringReplace(sanitized, "/", "_");
   StringReplace(sanitized, ":", "_");
   StringReplace(sanitized, "*", "_");
   StringReplace(sanitized, "?", "_");
   StringReplace(sanitized, "\"", "_");
   StringReplace(sanitized, "<", "_");
   StringReplace(sanitized, ">", "_");
   StringReplace(sanitized, "|", "_");
   StringReplace(sanitized, "$", "_");
   StringReplace(sanitized, " ", "_");
   return sanitized;
}

string NormalizeInputString(string value)
{
   const int separator = StringFind(value, "||");
   if(separator >= 0)
      value = StringSubstr(value, 0, separator);

   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

int CommonFlag()
{
   return InpUseCommonFiles ? FILE_COMMON : 0;
}

bool IsInsideDataWindow(const datetime value)
{
   if(!InpUseDataWindow)
      return true;
   if(InpDataWindowStart != 0 && value < InpDataWindowStart)
      return false;
   if(InpDataWindowEnd != 0 && value > InpDataWindowEnd)
      return false;
   return true;
}

void ResetEmaAccumulator(EmaAccumulator &state)
{
   state.valid_count = 0;
   state.value = 0.0;
}

void AppendDateTime(datetime &values[], const datetime value)
{
   const int size = ArraySize(values);
   ArrayResize(values, size + 1, ARRAY_RESERVE);
   values[size] = value;
}

void AppendInt(int &values[], const int value)
{
   const int size = ArraySize(values);
   ArrayResize(values, size + 1, ARRAY_RESERVE);
   values[size] = value;
}

void AppendDouble(double &values[], const double value)
{
   const int size = ArraySize(values);
   ArrayResize(values, size + 1, ARRAY_RESERVE);
   values[size] = value;
}

void ReverseRates(MqlRates &rates[])
{
   const int count = ArraySize(rates);
   for(int i = 0; i < count / 2; ++i)
   {
      MqlRates tmp = rates[i];
      rates[i] = rates[count - 1 - i];
      rates[count - 1 - i] = tmp;
   }
}

void EnsureAscendingRates(MqlRates &rates[])
{
   const int count = ArraySize(rates);
   if(count > 1 && rates[0].time > rates[count - 1].time)
      ReverseRates(rates);
}

int DateKey(const datetime value)
{
   MqlDateTime ts;
   TimeToStruct(value, ts);
   return (ts.year * 10000 + ts.mon * 100 + ts.day);
}

void DecomposeTime(const datetime value, int &date_key, int &hour, int &minute)
{
   MqlDateTime ts;
   TimeToStruct(value, ts);
   date_key = ts.year * 10000 + ts.mon * 100 + ts.day;
   hour = ts.hour;
   minute = ts.min;
}

bool IsLastWindowBar(const int hour, const int minute)
{
   return (hour > InpLastWindowHour || (hour == InpLastWindowHour && minute >= InpLastWindowMinute));
}

bool IsEntryCutoffOrLater(const int hour, const int minute)
{
   return (hour > InpEntryCutoffHour || (hour == InpEntryCutoffHour && minute >= InpEntryCutoffMinute));
}

double UpdateEma(EmaAccumulator &state, const double source, const int period)
{
   if(IsMissing(source))
      return MissingValue();

   const double alpha = 2.0 / (period + 1.0);
   if(state.valid_count == 0)
      state.value = source;
   else
      state.value = alpha * source + (1.0 - alpha) * state.value;

   state.valid_count++;
   if(state.valid_count >= period)
      return state.value;

   return MissingValue();
}

double UpdateRsi(const int index)
{
   double gain = 0.0;
   double loss = 0.0;

   if(index > 0)
   {
      const double diff = g_close[index] - g_close[index - 1];
      gain = (diff > 0.0 ? diff : 0.0);
      loss = (diff < 0.0 ? -diff : 0.0);
   }

   const double alpha = 1.0 / InpRsiWindow;
   if(g_rsi_count == 0)
   {
      g_rsi_avg_up = gain;
      g_rsi_avg_down = loss;
   }
   else
   {
      g_rsi_avg_up = alpha * gain + (1.0 - alpha) * g_rsi_avg_up;
      g_rsi_avg_down = alpha * loss + (1.0 - alpha) * g_rsi_avg_down;
   }

   g_rsi_count++;
   if(g_rsi_count < InpRsiWindow)
      return MissingValue();

   if(g_rsi_avg_down == 0.0)
      return 100.0;

   const double rs = g_rsi_avg_up / g_rsi_avg_down;
   return 100.0 - (100.0 / (1.0 + rs));
}

double UpdateAtr(const int index)
{
   double tr = g_high[index] - g_low[index];
   if(index > 0)
   {
      const double tr2 = MathAbs(g_high[index] - g_close[index - 1]);
      const double tr3 = MathAbs(g_low[index] - g_close[index - 1]);
      tr = MathMax(tr, MathMax(tr2, tr3));
   }

   if(g_atr_count < InpAtrWindow)
   {
      g_atr_sum_tr += tr;
      g_atr_count++;
      if(g_atr_count == InpAtrWindow)
         g_atr_value = g_atr_sum_tr / InpAtrWindow;
      return (g_atr_count >= InpAtrWindow ? g_atr_value : 0.0);
   }

   g_atr_value = ((g_atr_value * (InpAtrWindow - 1)) + tr) / InpAtrWindow;
   g_atr_count++;
   return g_atr_value;
}

double UpdateTrix(const double close_value)
{
   const double ema1 = UpdateEma(g_trix_ema1_state, close_value, InpTrixWindow);
   const double ema2 = UpdateEma(g_trix_ema2_state, ema1, InpTrixWindow);
   const double ema3 = UpdateEma(g_trix_ema3_state, ema2, InpTrixWindow);

   double trix_value = MissingValue();
   if(!IsMissing(ema3) && g_prev_ema3_valid && g_prev_ema3_value != 0.0)
      trix_value = ((ema3 - g_prev_ema3_value) / g_prev_ema3_value) * 100.0;

   if(!IsMissing(ema3))
   {
      g_prev_ema3_value = ema3;
      g_prev_ema3_valid = true;
   }

   return trix_value;
}

double ComputeShiftedRollingMedianForCurrent(const int index)
{
   const int end_index = index - 1;
   if(end_index < 0)
      return MissingValue();

   const int start_index = MathMax(0, end_index - InpTrixMedianWindow + 1);
   int valid_count = 0;

   for(int i = start_index; i <= end_index; ++i)
   {
      if(!IsMissing(g_trix[i]))
         valid_count++;
   }

   if(valid_count < InpTrixMedianMinPeriods)
      return MissingValue();

   double temp[];
   ArrayResize(temp, valid_count);
   int cursor = 0;
   for(int i = start_index; i <= end_index; ++i)
   {
      if(IsMissing(g_trix[i]))
         continue;
      temp[cursor++] = g_trix[i];
   }

   ArraySort(temp);
   if((valid_count % 2) == 1)
      return temp[valid_count / 2];

   const int upper = valid_count / 2;
   return 0.5 * (temp[upper - 1] + temp[upper]);
}

double ComputeHurstForCurrent(const int index)
{
   if(index < InpHurstWindow - 1)
      return MissingValue();

   const int start_index = index - InpHurstWindow + 1;
   const int returns_count = InpHurstWindow - 1;
   if(returns_count < 10)
      return 0.5;

   double returns[];
   ArrayResize(returns, returns_count);

   double mean = 0.0;
   for(int i = 0; i < returns_count; ++i)
   {
      const double prev = g_close[start_index + i];
      if(prev == 0.0)
         return 0.5;
      returns[i] = (g_close[start_index + i + 1] - prev) / prev;
      mean += returns[i];
   }
   mean /= returns_count;

   double cumulative = 0.0;
   double max_dev = -DBL_MAX;
   double min_dev = DBL_MAX;
   double variance = 0.0;

   for(int i = 0; i < returns_count; ++i)
   {
      const double centered = returns[i] - mean;
      cumulative += centered;
      if(cumulative > max_dev)
         max_dev = cumulative;
      if(cumulative < min_dev)
         min_dev = cumulative;
      variance += centered * centered;
   }

   const double range = max_dev - min_dev;
   const double std_sample = MathSqrt(variance / (returns_count - 1));
   if(std_sample == 0.0 || range == 0.0)
      return 0.5;

   return MathLog(range / std_sample) / MathLog((double)returns_count);
}

double SampleStdTrailingWindow(const double &source[], const int end_index, const int window)
{
   if(window <= 1)
      return MissingValue();

   const int start_index = end_index - window + 1;
   if(start_index < 0)
      return MissingValue();

   double sum = 0.0;
   double sum_sq = 0.0;
   for(int i = start_index; i <= end_index; ++i)
   {
      if(IsMissing(source[i]))
         return MissingValue();
      sum += source[i];
      sum_sq += source[i] * source[i];
   }

   const double n = (double)window;
   double numerator = sum_sq - (sum * sum) / n;
   if(numerator < 0.0 && MathAbs(numerator) < 1e-12)
      numerator = 0.0;
   if(numerator < 0.0)
      return MissingValue();

   return MathSqrt(numerator / (n - 1.0));
}

double ComputeVrForCurrent(const int index)
{
   if(index < InpVrLongWindow)
      return MissingValue();

   const double short_std = SampleStdTrailingWindow(g_returns, index, InpVrShortWindow);
   const double long_std = SampleStdTrailingWindow(g_returns, index, InpVrLongWindow);

   if(IsMissing(short_std) || IsMissing(long_std))
      return MissingValue();
   if(long_std == 0.0)
      return (short_std > 0.0 ? 1.0e100 : MissingValue());

   return short_std / long_std;
}

double UpdateAdx(const int index)
{
   if(index == 0)
   {
      AppendDouble(g_true_range, MissingValue());
      AppendDouble(g_pos_dm, MissingValue());
      AppendDouble(g_neg_dm, MissingValue());
      AppendDouble(g_dx, MissingValue());
      return 0.0;
   }

   const double tr = MathMax(g_high[index], g_close[index - 1]) - MathMin(g_low[index], g_close[index - 1]);
   const double diff_up = g_high[index] - g_high[index - 1];
   const double diff_down = g_low[index - 1] - g_low[index];
   const double pos_dm = ((diff_up > diff_down && diff_up > 0.0) ? MathAbs(diff_up) : 0.0);
   const double neg_dm = ((diff_down > diff_up && diff_down > 0.0) ? MathAbs(diff_down) : 0.0);

   AppendDouble(g_true_range, tr);
   AppendDouble(g_pos_dm, pos_dm);
   AppendDouble(g_neg_dm, neg_dm);

   double dx_value = MissingValue();
   if(index == InpAdxWindow)
   {
      g_adx_smoothed_tr = 0.0;
      g_adx_smoothed_pos = 0.0;
      g_adx_smoothed_neg = 0.0;
      for(int i = 1; i <= InpAdxWindow; ++i)
      {
         g_adx_smoothed_tr += g_true_range[i];
         g_adx_smoothed_pos += g_pos_dm[i];
         g_adx_smoothed_neg += g_neg_dm[i];
      }
   }
   else if(index > InpAdxWindow)
   {
      g_adx_smoothed_tr = g_adx_smoothed_tr - (g_adx_smoothed_tr / InpAdxWindow) + tr;
      g_adx_smoothed_pos = g_adx_smoothed_pos - (g_adx_smoothed_pos / InpAdxWindow) + pos_dm;
      g_adx_smoothed_neg = g_adx_smoothed_neg - (g_adx_smoothed_neg / InpAdxWindow) + neg_dm;
   }

   if(index >= InpAdxWindow)
   {
      double di_plus = 0.0;
      double di_minus = 0.0;
      if(g_adx_smoothed_tr != 0.0)
      {
         di_plus = 100.0 * (g_adx_smoothed_pos / g_adx_smoothed_tr);
         di_minus = 100.0 * (g_adx_smoothed_neg / g_adx_smoothed_tr);
      }
      const double denom = di_plus + di_minus;
      if(denom != 0.0)
         dx_value = 100.0 * MathAbs((di_plus - di_minus) / denom);
   }

   AppendDouble(g_dx, dx_value);

   if(index == (2 * InpAdxWindow) - 1)
   {
      double dx_sum = 0.0;
      for(int i = InpAdxWindow; i <= (2 * InpAdxWindow) - 1; ++i)
         dx_sum += (IsMissing(g_dx[i]) ? 0.0 : g_dx[i]);
      g_adx_value = dx_sum / InpAdxWindow;
      return g_adx_value;
   }

   if(index > (2 * InpAdxWindow) - 1 && !IsMissing(dx_value))
   {
      g_adx_value = ((g_adx_value * (InpAdxWindow - 1)) + dx_value) / InpAdxWindow;
      return g_adx_value;
   }

   return 0.0;
}

void ResetAllState()
{
   ArrayResize(g_times, 0);
   ArrayResize(g_dates, 0);
   ArrayResize(g_hours, 0);
   ArrayResize(g_minutes, 0);
   ArrayResize(g_close, 0);
   ArrayResize(g_high, 0);
   ArrayResize(g_low, 0);
   ArrayResize(g_volume, 0);
   ArrayResize(g_returns, 0);
   ArrayResize(g_ema_fast, 0);
   ArrayResize(g_ema_slow, 0);
   ArrayResize(g_ema_trend, 0);
   ArrayResize(g_rsi, 0);
   ArrayResize(g_adx, 0);
   ArrayResize(g_atr, 0);
   ArrayResize(g_trix, 0);
   ArrayResize(g_true_range, 0);
   ArrayResize(g_pos_dm, 0);
   ArrayResize(g_neg_dm, 0);
   ArrayResize(g_dx, 0);

   ResetEmaAccumulator(g_ema_fast_state);
   ResetEmaAccumulator(g_ema_slow_state);
   ResetEmaAccumulator(g_ema_trend_state);
   ResetEmaAccumulator(g_trix_ema1_state);
   ResetEmaAccumulator(g_trix_ema2_state);
   ResetEmaAccumulator(g_trix_ema3_state);

   g_rsi_count = 0;
   g_rsi_avg_up = 0.0;
   g_rsi_avg_down = 0.0;

   g_atr_count = 0;
   g_atr_sum_tr = 0.0;
   g_atr_value = 0.0;

   g_adx_smoothed_tr = 0.0;
   g_adx_smoothed_pos = 0.0;
   g_adx_smoothed_neg = 0.0;
   g_adx_value = 0.0;

   g_prev_ema3_valid = false;
   g_prev_ema3_value = 0.0;

   g_vwap_date = 0;
   g_vwap_cum_tp_vol = 0.0;
   g_vwap_cum_vol = 0.0;

   g_position = 0;
   g_peak = 0.0;
   g_raw_last = 0;
   g_parity_position = 0;
   g_parity_entry_price = 0.0;
   g_parity_entry_time = 0;
   g_parity_prev_date = 0;
   g_parity_last_seen_date = 0;
   g_parity_trading_days = 0;
   g_parity_bar_count = 0;
   g_parity_position_bar_count = 0;
   g_parity_last_bar_time = 0;
   g_parity_last_fill_price = 0.0;
   ArrayResize(g_parity_trade_pnls, 0);
   ArrayResize(g_parity_trade_entries, 0);
   ArrayResize(g_parity_trade_exits, 0);
   ArrayResize(g_parity_trade_directions, 0);
   ArrayResize(g_parity_trade_entry_prices, 0);
   ArrayResize(g_parity_trade_exit_prices, 0);
   g_parity_metrics.sharpe = 0.0;
   g_parity_metrics.profit_factor = 0.0;
   g_parity_metrics.max_drawdown_pct = 0.0;
   g_parity_metrics.win_rate = 0.0;
   g_parity_metrics.total_trades = 0;
   g_parity_metrics.net_profit_brl = 0.0;
   g_parity_metrics.avg_profit_per_trade = 0.0;
   g_parity_metrics.avg_win_brl = 0.0;
   g_parity_metrics.avg_loss_brl = 0.0;
   g_parity_metrics.max_consec_losses = 0;
   g_parity_metrics.exposure_pct = 0.0;

   g_last_processed_closed_time = 0;
   g_state_ready = false;
   g_parity_finalized = false;
   g_external_parity_ready = false;
}

void AppendParityTrade(
   const datetime entry_time,
   const datetime exit_time,
   const int direction,
   const double entry_price,
   const double exit_price,
   const double pnl_brl
)
{
   const int size = ArraySize(g_parity_trade_pnls);
   ArrayResize(g_parity_trade_pnls, size + 1, ARRAY_RESERVE);
   ArrayResize(g_parity_trade_entries, size + 1, ARRAY_RESERVE);
   ArrayResize(g_parity_trade_exits, size + 1, ARRAY_RESERVE);
   ArrayResize(g_parity_trade_directions, size + 1, ARRAY_RESERVE);
   ArrayResize(g_parity_trade_entry_prices, size + 1, ARRAY_RESERVE);
   ArrayResize(g_parity_trade_exit_prices, size + 1, ARRAY_RESERVE);

   g_parity_trade_pnls[size] = pnl_brl;
   g_parity_trade_entries[size] = entry_time;
   g_parity_trade_exits[size] = exit_time;
   g_parity_trade_directions[size] = direction;
   g_parity_trade_entry_prices[size] = entry_price;
   g_parity_trade_exit_prices[size] = exit_price;
}

void CloseParityPosition(const datetime exit_time, const double fill_price)
{
   if(g_parity_position == 0)
      return;

   const double pnl_brl = (fill_price - g_parity_entry_price) * g_parity_position * InpPointValueBrl - InpRoundTripCostBrl;
   AppendParityTrade(
      g_parity_entry_time,
      exit_time,
      g_parity_position,
      g_parity_entry_price,
      fill_price,
      pnl_brl
   );

   g_parity_position = 0;
   g_parity_entry_price = 0.0;
   g_parity_entry_time = 0;
}

void UpdateParityState(const int desired_direction, const datetime bar_time, const double fill_price)
{
   if(!InpEnableParityMetrics || g_parity_finalized)
      return;

   const int current_date = DateKey(bar_time);
   if(g_parity_last_seen_date != current_date)
   {
      g_parity_last_seen_date = current_date;
      g_parity_trading_days++;
   }

   g_parity_last_bar_time = bar_time;
   g_parity_last_fill_price = fill_price;
   g_parity_bar_count++;
   if(desired_direction != 0)
      g_parity_position_bar_count++;

   if(g_parity_prev_date != 0 && current_date != g_parity_prev_date && g_parity_position != 0)
      CloseParityPosition(bar_time, fill_price);

   if(desired_direction != g_parity_position)
   {
      if(g_parity_position != 0)
         CloseParityPosition(bar_time, fill_price);

      if(desired_direction != 0)
      {
         g_parity_entry_price = fill_price;
         g_parity_entry_time = bar_time;
      }

      g_parity_position = desired_direction;
   }

   g_parity_prev_date = current_date;
}

double ComputeParitySharpe()
{
   const int total_trades = ArraySize(g_parity_trade_pnls);
   if(total_trades <= 1)
      return 0.0;

   double mean = 0.0;
   for(int i = 0; i < total_trades; ++i)
      mean += g_parity_trade_pnls[i];
   mean /= total_trades;

   double variance = 0.0;
   for(int i = 0; i < total_trades; ++i)
   {
      const double diff = g_parity_trade_pnls[i] - mean;
      variance += diff * diff;
   }
   variance /= (total_trades - 1);
   if(variance <= 0.0)
      return 0.0;

   const double std_sample = MathSqrt(variance);
   const double trades_per_day = (g_parity_trading_days > 0 ? (double)total_trades / g_parity_trading_days : 0.0);
   const double trades_per_year = trades_per_day * 252.0;
   return (mean / std_sample) * MathSqrt(trades_per_year);
}

void FinalizeParityMetrics()
{
   if(!InpEnableParityMetrics || g_parity_finalized)
      return;

   if(g_parity_position != 0 && g_parity_last_bar_time != 0)
      CloseParityPosition(g_parity_last_bar_time, g_parity_last_fill_price);

   const int total_trades = ArraySize(g_parity_trade_pnls);
   g_parity_metrics.total_trades = total_trades;
   if(g_parity_bar_count > 0)
      g_parity_metrics.exposure_pct = 100.0 * (double)g_parity_position_bar_count / g_parity_bar_count;

   if(total_trades == 0)
   {
      g_parity_finalized = true;
      return;
   }

   double gross_profit = 0.0;
   double gross_loss = 0.0;
   double net_profit = 0.0;
   int wins = 0;
   int current_consec_losses = 0;
   int max_consec_losses = 0;
   double avg_win_sum = 0.0;
   double avg_loss_sum = 0.0;

   double equity = InpInitialEquityBrl;
   double peak_equity = equity;
   double max_dd_pct = 0.0;

   for(int i = 0; i < total_trades; ++i)
   {
      const double pnl = g_parity_trade_pnls[i];
      net_profit += pnl;

      if(pnl > 0.0)
      {
         wins++;
         gross_profit += pnl;
         avg_win_sum += pnl;
         current_consec_losses = 0;
      }
      else if(pnl < 0.0)
      {
         gross_loss += -pnl;
         avg_loss_sum += pnl;
         current_consec_losses++;
         if(current_consec_losses > max_consec_losses)
            max_consec_losses = current_consec_losses;
      }
      else
      {
         current_consec_losses = 0;
      }

      equity += pnl;
      if(equity > peak_equity)
         peak_equity = equity;
      if(peak_equity > 0.0)
      {
         const double dd_pct = (peak_equity - equity) / peak_equity * 100.0;
         if(dd_pct > max_dd_pct)
            max_dd_pct = dd_pct;
      }
   }

   g_parity_metrics.net_profit_brl = net_profit;
   g_parity_metrics.win_rate = (double)wins / total_trades;
   g_parity_metrics.avg_profit_per_trade = net_profit / total_trades;
   g_parity_metrics.avg_win_brl = (wins > 0 ? avg_win_sum / wins : 0.0);
   g_parity_metrics.avg_loss_brl = ((total_trades - wins) > 0 ? avg_loss_sum / (total_trades - wins) : 0.0);
   g_parity_metrics.profit_factor = (gross_loss > 0.0 ? gross_profit / gross_loss : (gross_profit > 0.0 ? DBL_MAX : 0.0));
   g_parity_metrics.max_drawdown_pct = max_dd_pct;
   g_parity_metrics.max_consec_losses = max_consec_losses;
   g_parity_metrics.sharpe = ComputeParitySharpe();
   g_parity_finalized = true;
}

void WriteParityFiles()
{
   if(!InpEnableParityMetrics || !InpWriteParityFiles)
      return;

   FinalizeParityMetrics();

   const string prefix = SanitizeToken(NormalizeInputString(InpParityOutputPrefix) + "_" + _Symbol);
   const int summary_flags = FILE_WRITE | FILE_TXT | FILE_ANSI | CommonFlag();
   const int trades_flags = FILE_WRITE | FILE_CSV | FILE_ANSI | CommonFlag();

   const string summary_name = prefix + "_summary.txt";
   const string trades_name = prefix + "_trades.csv";

   int summary_handle = FileOpen(summary_name, summary_flags);
   if(summary_handle != INVALID_HANDLE)
   {
      FileWriteString(summary_handle, StringFormat("symbol=%s\n", _Symbol));
      FileWriteString(summary_handle, StringFormat("timeframe=%s\n", EnumToString(_Period)));
      FileWriteString(summary_handle, StringFormat("sharpe=%.6f\n", g_parity_metrics.sharpe));
      FileWriteString(summary_handle, StringFormat("profit_factor=%.6f\n", g_parity_metrics.profit_factor));
      FileWriteString(summary_handle, StringFormat("max_drawdown_pct=%.6f\n", g_parity_metrics.max_drawdown_pct));
      FileWriteString(summary_handle, StringFormat("win_rate=%.6f\n", g_parity_metrics.win_rate));
      FileWriteString(summary_handle, StringFormat("total_trades=%d\n", g_parity_metrics.total_trades));
      FileWriteString(summary_handle, StringFormat("net_profit_brl=%.2f\n", g_parity_metrics.net_profit_brl));
      FileWriteString(summary_handle, StringFormat("avg_profit_per_trade=%.2f\n", g_parity_metrics.avg_profit_per_trade));
      FileWriteString(summary_handle, StringFormat("avg_win_brl=%.2f\n", g_parity_metrics.avg_win_brl));
      FileWriteString(summary_handle, StringFormat("avg_loss_brl=%.2f\n", g_parity_metrics.avg_loss_brl));
      FileWriteString(summary_handle, StringFormat("max_consec_losses=%d\n", g_parity_metrics.max_consec_losses));
      FileWriteString(summary_handle, StringFormat("exposure_pct=%.6f\n", g_parity_metrics.exposure_pct));
      FileClose(summary_handle);
   }
   else
      Print("Could not open parity summary file ", summary_name, ". Error=", GetLastError());

   int trades_handle = FileOpen(trades_name, trades_flags, ',');
   if(trades_handle != INVALID_HANDLE)
   {
      FileWrite(trades_handle, "entry_time", "exit_time", "direction", "entry_price", "exit_price", "pnl_brl");
      const int total_trades = ArraySize(g_parity_trade_pnls);
      for(int i = 0; i < total_trades; ++i)
      {
         FileWrite(
            trades_handle,
            TimeToString(g_parity_trade_entries[i], TIME_DATE | TIME_MINUTES | TIME_SECONDS),
            TimeToString(g_parity_trade_exits[i], TIME_DATE | TIME_MINUTES | TIME_SECONDS),
            (g_parity_trade_directions[i] > 0 ? "long" : "short"),
            DoubleToString(g_parity_trade_entry_prices[i], 3),
            DoubleToString(g_parity_trade_exit_prices[i], 3),
            DoubleToString(g_parity_trade_pnls[i], 2)
         );
      }
      FileClose(trades_handle);
   }
   else
      Print("Could not open parity trades file ", trades_name, ". Error=", GetLastError());
}

bool LoadExternalParityBars(CsvBar &bars[], string &status)
{
   ArrayResize(bars, 0);

   const string file_name = NormalizeInputString(InpExternalParityCsvName);
   if(file_name == "")
   {
      status = "external_csv_empty_name";
      return false;
   }

   const int flags = FILE_READ | FILE_CSV | FILE_ANSI | CommonFlag();
   int handle = FileOpen(file_name, flags, ',');
   if(handle == INVALID_HANDLE)
   {
      status = StringFormat("external_csv_open_failed_%d", GetLastError());
      return false;
   }

   while(!FileIsEnding(handle))
   {
      string time_text = FileReadString(handle);
      if(FileIsEnding(handle) && time_text == "")
         break;
      if(time_text == "")
         continue;

      string open_text = FileReadString(handle);
      string high_text = FileReadString(handle);
      string low_text = FileReadString(handle);
      string close_text = FileReadString(handle);
      string volume_text = FileReadString(handle);
      string spread_text = FileReadString(handle);

      if(StringCompare(time_text, "time", false) == 0)
         continue;

      const int size = ArraySize(bars);
      ArrayResize(bars, size + 1, ARRAY_RESERVE);
      bars[size].time = StringToTime(time_text);
      bars[size].open = StringToDouble(open_text);
      bars[size].high = StringToDouble(high_text);
      bars[size].low = StringToDouble(low_text);
      bars[size].close = StringToDouble(close_text);
      bars[size].volume = StringToDouble(volume_text);
      bars[size].spread = StringToDouble(spread_text);
   }

   FileClose(handle);
   status = StringFormat("external_csv_loaded_%d", ArraySize(bars));
   return (ArraySize(bars) > 0);
}

bool RunExternalParityBacktest(string &status)
{
   CsvBar bars[];
   if(!LoadExternalParityBars(bars, status))
      return false;

   ResetAllState();
   const int total_bars = ArraySize(bars);
   for(int i = 0; i < total_bars; ++i)
   {
      int desired_direction = 0;
      const int state_size = ArraySize(g_dates);
      if(state_size > 0)
      {
         const int previous_closed_date = g_dates[state_size - 1];
         desired_direction = (DateKey(bars[i].time) == previous_closed_date ? g_raw_last : 0);
      }

      UpdateParityState(desired_direction, bars[i].time, bars[i].open);

      MqlRates bar;
      bar.time = bars[i].time;
      bar.open = bars[i].open;
      bar.high = bars[i].high;
      bar.low = bars[i].low;
      bar.close = bars[i].close;
      bar.tick_volume = (long)MathRound(bars[i].volume);
      bar.spread = (int)MathRound(bars[i].spread);
      ProcessClosedBar(bar);
   }

   FinalizeParityMetrics();
   g_external_parity_ready = true;
   status = StringFormat("external_parity_ready_%d_bars_%d_trades", total_bars, g_parity_metrics.total_trades);
   return true;
}

void ProcessClosedBar(const MqlRates &bar)
{
   if(!IsInsideDataWindow(bar.time))
      return;

   int date_key = 0;
   int hour = 0;
   int minute = 0;
   DecomposeTime(bar.time, date_key, hour, minute);

   AppendDateTime(g_times, bar.time);
   AppendInt(g_dates, date_key);
   AppendInt(g_hours, hour);
   AppendInt(g_minutes, minute);
   AppendDouble(g_close, bar.close);
   AppendDouble(g_high, bar.high);
   AppendDouble(g_low, bar.low);
   AppendDouble(g_volume, (double)bar.tick_volume);

   const int index = ArraySize(g_close) - 1;

   double ret_value = MissingValue();
   if(index > 0 && g_close[index - 1] != 0.0)
      ret_value = (g_close[index] / g_close[index - 1]) - 1.0;
   AppendDouble(g_returns, ret_value);

   if(g_vwap_date != date_key)
   {
      g_vwap_date = date_key;
      g_vwap_cum_tp_vol = 0.0;
      g_vwap_cum_vol = 0.0;
   }

   const double typical = (bar.high + bar.low + bar.close) / 3.0;
   g_vwap_cum_tp_vol += typical * (double)bar.tick_volume;
   g_vwap_cum_vol += (double)bar.tick_volume;
   const double current_vwap = (g_vwap_cum_vol > 0.0 ? g_vwap_cum_tp_vol / g_vwap_cum_vol : MissingValue());

   const double ema_fast = UpdateEma(g_ema_fast_state, bar.close, InpEmaFast);
   const double ema_slow = UpdateEma(g_ema_slow_state, bar.close, InpEmaSlow);
   const double ema_trend = UpdateEma(g_ema_trend_state, bar.close, InpTrendWindow);
   const double rsi_value = UpdateRsi(index);
   const double atr_value = UpdateAtr(index);
   const double trix_value = UpdateTrix(bar.close);
   const double adx_value = UpdateAdx(index);
   const double hurst_value = ComputeHurstForCurrent(index);
   const double vr_value = ComputeVrForCurrent(index);
   const double trix_median = ComputeShiftedRollingMedianForCurrent(index);

   AppendDouble(g_ema_fast, ema_fast);
   AppendDouble(g_ema_slow, ema_slow);
   AppendDouble(g_ema_trend, ema_trend);
   AppendDouble(g_rsi, rsi_value);
   AppendDouble(g_adx, adx_value);
   AppendDouble(g_atr, atr_value);
   AppendDouble(g_trix, trix_value);

   const bool is_first_bar = (index == 0 || g_dates[index] != g_dates[index - 1]);
   const bool is_last_window = IsLastWindowBar(hour, minute);
   int raw = 0;

   if(is_first_bar)
   {
      g_position = 0;
      g_peak = 0.0;
      g_raw_last = 0;
      return;
   }

   if(is_last_window)
   {
      g_position = 0;
      g_peak = 0.0;
      g_raw_last = 0;
      return;
   }

   if(IsMissing(ema_fast) || IsMissing(ema_slow) || IsMissing(ema_trend))
   {
      g_raw_last = g_position;
      return;
   }

   if(g_position != 0)
   {
      const double median_value = (IsMissing(trix_median) ? 0.0 : trix_median);
      const double current_trix = (IsMissing(trix_value) ? median_value : trix_value);
      const double previous_trix = (index > 0 && !IsMissing(g_trix[index - 1]) ? g_trix[index - 1] : median_value);

      bool trix_exit = false;
      if(g_position == 1 && current_trix < median_value && previous_trix >= median_value)
         trix_exit = true;
      else if(g_position == -1 && current_trix > median_value && previous_trix <= median_value)
         trix_exit = true;

      if(trix_exit)
      {
         g_position = 0;
         g_peak = 0.0;
         raw = 0;
      }
      else if(g_position == 1)
      {
         g_peak = MathMax(g_peak, g_close[index]);
         if(atr_value > 0.0 && g_close[index] < g_peak - InpAtrMult * atr_value)
         {
            g_position = 0;
            g_peak = 0.0;
            raw = 0;
         }
         else
            raw = 1;
      }
      else
      {
         g_peak = MathMin(g_peak, g_close[index]);
         if(atr_value > 0.0 && g_close[index] > g_peak + InpAtrMult * atr_value)
         {
            g_position = 0;
            g_peak = 0.0;
            raw = 0;
         }
         else
            raw = -1;
      }

      g_raw_last = raw;
      return;
   }

   if((InpSkipHour12 && hour == 12) || (InpSkipHour13 && hour == 13))
   {
      g_raw_last = 0;
      return;
   }

   if(IsEntryCutoffOrLater(hour, minute))
   {
      g_raw_last = 0;
      return;
   }

   if(adx_value < InpAdxThreshold)
   {
      g_raw_last = 0;
      return;
   }

   if(!IsMissing(hurst_value) && hurst_value < InpHurstThreshold)
   {
      g_raw_last = 0;
      return;
   }

   if(!IsMissing(vr_value) && vr_value > InpVrMax)
   {
      g_raw_last = 0;
      return;
   }

   const double current_rsi = (IsMissing(rsi_value) ? 50.0 : rsi_value);
   if(index > 0 && !IsMissing(g_ema_fast[index - 1]) && !IsMissing(g_ema_slow[index - 1]))
   {
      const bool cross_up = (ema_fast > ema_slow && g_ema_fast[index - 1] <= g_ema_slow[index - 1]);
      const bool cross_down = (ema_fast < ema_slow && g_ema_fast[index - 1] >= g_ema_slow[index - 1]);
      const double vwap_reference = (IsMissing(current_vwap) ? g_close[index] : current_vwap);

      if(cross_up &&
         g_close[index] > ema_trend &&
         current_rsi > InpRsiLong &&
         (!InpUseVwap || g_close[index] > vwap_reference))
      {
         g_position = 1;
         g_peak = g_close[index];
         raw = 1;
      }
      else if(cross_down &&
              g_close[index] < ema_trend &&
              current_rsi < InpRsiShort &&
              (!InpUseVwap || g_close[index] < vwap_reference))
      {
         g_position = -1;
         g_peak = g_close[index];
         raw = -1;
      }
   }

   g_raw_last = raw;
}

bool BootstrapState(string &status)
{
   ResetAllState();

   MqlRates rates[];
   const int copied = CopyRates(_Symbol, _Period, 0, InpHistoryBars + 1, rates);
   if(copied <= 1)
   {
      status = "not_enough_rates";
      return false;
   }

   EnsureAscendingRates(rates);
   const int closed_count = copied - 1;
   if(closed_count <= 0)
   {
      status = "no_closed_bar";
      return false;
   }

   for(int i = 0; i < closed_count; ++i)
      ProcessClosedBar(rates[i]);

   g_last_processed_closed_time = rates[closed_count - 1].time;
   g_state_ready = true;
   status = "bootstrapped";
   return true;
}

bool UpdateStateToLatestClosedBar(string &status)
{
   if(!g_state_ready)
      return BootstrapState(status);

   if(g_last_processed_closed_time == 0)
      return BootstrapState(status);

   const int processed_shift = iBarShift(_Symbol, _Period, g_last_processed_closed_time, true);
   if(processed_shift < 0)
      return BootstrapState(status);

   const int missing_count = processed_shift - 1;
   if(missing_count <= 0)
   {
      status = "current";
      return true;
   }

   MqlRates new_rates[];
   const int copied = CopyRates(_Symbol, _Period, 1, missing_count, new_rates);
   if(copied != missing_count)
   {
      status = "copy_rates_failed";
      return false;
   }

   EnsureAscendingRates(new_rates);
   for(int i = 0; i < copied; ++i)
      ProcessClosedBar(new_rates[i]);

   g_last_processed_closed_time = new_rates[copied - 1].time;
   status = StringFormat("updated_%d", copied);
   return true;
}

int CurrentPositionDirection()
{
   if(!PositionSelect(_Symbol))
      return 0;

   const long type = PositionGetInteger(POSITION_TYPE);
   if(type == POSITION_TYPE_BUY)
      return 1;
   if(type == POSITION_TYPE_SELL)
      return -1;
   return 0;
}

bool CloseCurrentPosition()
{
   if(!PositionSelect(_Symbol))
      return true;

   if(trade.PositionClose(_Symbol))
      return true;

   Print("PositionClose failed. Retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   return false;
}

bool OpenDesiredPosition(const int desired_direction)
{
   if(!InpMirrorRealOrders)
      return true;

   if(desired_direction == 0)
      return true;

   bool ok = false;
   if(desired_direction > 0)
      ok = trade.Buy(InpLots, _Symbol, 0.0, 0.0, 0.0, "EMA 35610 historical");
   else
      ok = trade.Sell(InpLots, _Symbol, 0.0, 0.0, 0.0, "EMA 35610 historical");

   if(ok)
      return true;

   Print("Open order failed. Retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   return false;
}

bool ComputeDesiredDirection(int &desired_direction, string &status)
{
   desired_direction = 0;
   status = "idle";

   const bool updated = UpdateStateToLatestClosedBar(status);
   if(!updated)
      return false;

   const datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == 0)
   {
      status = "no_current_bar";
      return false;
   }

   if(!IsInsideDataWindow(current_bar_time))
   {
      status = "outside_data_window";
      desired_direction = 0;
      return true;
   }

   if(ArraySize(g_dates) <= 0)
   {
      status = "empty_state";
      return false;
   }

   const int current_date = DateKey(current_bar_time);
   const int previous_closed_date = g_dates[ArraySize(g_dates) - 1];
   desired_direction = (current_date == previous_closed_date ? g_raw_last : 0);
   status = StringFormat("%s desired=%d cached_bars=%d", status, desired_direction, ArraySize(g_close));
   return true;
}

void ProcessNewBar()
{
   int desired_direction = 0;
   string status = "";
   const bool computed = ComputeDesiredDirection(desired_direction, status);
   const int current_direction = CurrentPositionDirection();
   const datetime current_bar_time = iTime(_Symbol, _Period, 0);
   const double current_open = iOpen(_Symbol, _Period, 0);
   const bool current_bar_in_window = IsInsideDataWindow(current_bar_time);

   g_last_status = StringFormat(
      "status=%s current=%d desired=%d parity_trades=%d time=%s",
      status,
      current_direction,
      desired_direction,
      ArraySize(g_parity_trade_pnls),
      TimeToString(current_bar_time, TIME_DATE | TIME_MINUTES)
   );

   if(!computed)
   {
      if(current_bar_in_window)
         UpdateParityState(0, current_bar_time, current_open);
      return;
   }

   if(current_bar_in_window)
      UpdateParityState(desired_direction, current_bar_time, current_open);

   if(current_direction == desired_direction)
      return;

   if(current_direction != 0)
   {
      if(!CloseCurrentPosition())
         return;
   }

   if(desired_direction != 0)
      OpenDesiredPosition(desired_direction);
}

int OnInit()
{
   if(InpRequireM5 && _Period != PERIOD_M5)
   {
      Print("This EA was ported for M5 only.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpHistoryBars < 1200)
   {
      Print("InpHistoryBars should be at least 1200 for stable TRIX median and EMA warm-up.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpTrixMedianMinPeriods > InpTrixMedianWindow)
   {
      Print("InpTrixMedianMinPeriods cannot exceed InpTrixMedianWindow.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpVrShortWindow <= 1 || InpVrLongWindow <= InpVrShortWindow)
   {
      Print("VR windows must satisfy long > short > 1.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpUseExternalParityCsv && InpMirrorRealOrders)
   {
      Print("External parity CSV mode is virtual-only. Disable InpMirrorRealOrders.");
      return INIT_PARAMETERS_INCORRECT;
   }

   ResetAllState();
   trade.SetExpertMagicNumber((int)InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetAsyncMode(false);
   g_last_bar_time = 0;
   g_last_status = "initialized";

   if(InpUseExternalParityCsv)
   {
      string status = "";
      if(!RunExternalParityBacktest(status))
      {
         Print("External parity backtest failed: ", status);
         return INIT_FAILED;
      }
      g_last_status = status;
   }

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   WriteParityFiles();
   Comment("");
}

double OnTester()
{
   WriteParityFiles();
   return g_parity_metrics.sharpe;
}

void OnTick()
{
   if(InpUseExternalParityCsv)
   {
      Comment(
         "WDO EMA Historical 35610\n",
         "External parity CSV mode\n",
         g_last_status, "\n",
         "Parity Sharpe: ", DoubleToString(g_parity_metrics.sharpe, 4),
         "  Net: ", DoubleToString(g_parity_metrics.net_profit_brl, 2)
      );
      return;
   }

   const datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == 0)
      return;

   if(current_bar_time != g_last_bar_time)
   {
      g_last_bar_time = current_bar_time;
      ProcessNewBar();
   }

   Comment(
      "WDO EMA Historical 35610\n",
      "Symbol: ", _Symbol, "  TF: ", EnumToString(_Period), "\n",
      g_last_status, "\n",
      "Parity Sharpe: ", DoubleToString(g_parity_metrics.sharpe, 4),
      "  Net: ", DoubleToString(g_parity_metrics.net_profit_brl, 2)
   );
}
