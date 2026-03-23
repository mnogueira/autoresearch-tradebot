#property strict
#property version   "1.00"
#property description "Historical port of strategy.py from git commit 1c947fe."
#property description "Strategy: EMA(8/34) crossover + EMA(220) trend + ADX(14)>20"
#property description "RSI(7)>65/<40 + Hurst(100)>0.50 + ATR(20)x2 trailing stop"
#property description "TRIX(12) rolling median exit + skip 12h/13h + no entry after 14:55"
#property description "Execution model: decide on closed M5 bar, act at next bar open."

#include <Trade/Trade.mqh>

CTrade trade;

input double InpLots = 1.0;
input long   InpMagicNumber = 1947;
input int    InpDeviationPoints = 20;
input bool   InpRequireM5 = true;
input int    InpHistoryBars = 3000;

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
input bool   InpSkipHour12 = true;
input bool   InpSkipHour13 = true;
input int    InpEntryCutoffHour = 14;
input int    InpEntryCutoffMinute = 55;
input int    InpLastWindowHour = 17;
input int    InpLastWindowMinute = 25;

datetime g_last_bar_time = 0;
string   g_last_status = "";

double MissingValue()
{
   return DBL_MAX;
}

bool IsMissing(const double value)
{
   return (value == MissingValue());
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

void InitMissingArray(double &values[], const int size)
{
   ArrayResize(values, size);
   for(int i = 0; i < size; ++i)
      values[i] = MissingValue();
}

void InitZeroArray(double &values[], const int size)
{
   ArrayResize(values, size);
   ArrayInitialize(values, 0.0);
}

void ComputeEmaExact(const double &source[], const int size, const int period, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || period <= 0)
      return;

   const double alpha = 2.0 / (period + 1.0);
   int valid_count = 0;
   double ema_value = 0.0;

   for(int i = 0; i < size; ++i)
   {
      if(IsMissing(source[i]))
         continue;

      if(valid_count == 0)
         ema_value = source[i];
      else
         ema_value = alpha * source[i] + (1.0 - alpha) * ema_value;

      valid_count++;
      if(valid_count >= period)
         output[i] = ema_value;
   }
}

void ComputeEwmaAlpha(const double &source[], const int size, const double alpha, const int min_periods, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || min_periods <= 0)
      return;

   int valid_count = 0;
   double ewma_value = 0.0;

   for(int i = 0; i < size; ++i)
   {
      if(IsMissing(source[i]))
         continue;

      if(valid_count == 0)
         ewma_value = source[i];
      else
         ewma_value = alpha * source[i] + (1.0 - alpha) * ewma_value;

      valid_count++;
      if(valid_count >= min_periods)
         output[i] = ewma_value;
   }
}

void ComputeRsiExact(const double &close[], const int size, const int period, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || period <= 0)
      return;

   double gains[];
   double losses[];
   ArrayResize(gains, size);
   ArrayResize(losses, size);
   gains[0] = 0.0;
   losses[0] = 0.0;

   for(int i = 1; i < size; ++i)
   {
      const double diff = close[i] - close[i - 1];
      gains[i] = (diff > 0.0 ? diff : 0.0);
      losses[i] = (diff < 0.0 ? -diff : 0.0);
   }

   double avg_up[];
   double avg_down[];
   ComputeEwmaAlpha(gains, size, 1.0 / period, period, avg_up);
   ComputeEwmaAlpha(losses, size, 1.0 / period, period, avg_down);

   for(int i = 0; i < size; ++i)
   {
      if(IsMissing(avg_up[i]) || IsMissing(avg_down[i]))
         continue;

      if(avg_down[i] == 0.0)
         output[i] = 100.0;
      else
      {
         const double rs = avg_up[i] / avg_down[i];
         output[i] = 100.0 - (100.0 / (1.0 + rs));
      }
   }
}

void ComputeAtrExact(const double &high[], const double &low[], const double &close[], const int size, const int period, double &output[])
{
   InitZeroArray(output, size);
   if(size <= 0 || period <= 0 || size < period)
      return;

   double true_range[];
   ArrayResize(true_range, size);
   true_range[0] = high[0] - low[0];

   for(int i = 1; i < size; ++i)
   {
      const double tr1 = high[i] - low[i];
      const double tr2 = MathAbs(high[i] - close[i - 1]);
      const double tr3 = MathAbs(low[i] - close[i - 1]);
      true_range[i] = MathMax(tr1, MathMax(tr2, tr3));
   }

   double sum_tr = 0.0;
   for(int i = 0; i < period; ++i)
      sum_tr += true_range[i];

   output[period - 1] = sum_tr / period;

   for(int i = period; i < size; ++i)
      output[i] = ((output[i - 1] * (period - 1)) + true_range[i]) / period;
}

void ComputeTrixExact(const double &close[], const int size, const int period, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || period <= 0)
      return;

   double ema1[];
   double ema2[];
   double ema3[];
   ComputeEmaExact(close, size, period, ema1);
   ComputeEmaExact(ema1, size, period, ema2);
   ComputeEmaExact(ema2, size, period, ema3);

   for(int i = 1; i < size; ++i)
   {
      if(IsMissing(ema3[i]) || IsMissing(ema3[i - 1]) || ema3[i - 1] == 0.0)
         continue;

      output[i] = ((ema3[i] - ema3[i - 1]) / ema3[i - 1]) * 100.0;
   }
}

double ComputeMedian(const double &source[], const int start_index, const int end_index, int &valid_count)
{
   valid_count = 0;

   for(int i = start_index; i <= end_index; ++i)
   {
      if(!IsMissing(source[i]))
         valid_count++;
   }

   if(valid_count == 0)
      return MissingValue();

   double temp[];
   ArrayResize(temp, valid_count);
   int cursor = 0;

   for(int i = start_index; i <= end_index; ++i)
   {
      if(IsMissing(source[i]))
         continue;
      temp[cursor++] = source[i];
   }

   ArraySort(temp);

   if((valid_count % 2) == 1)
      return temp[valid_count / 2];

   const int upper = valid_count / 2;
   return 0.5 * (temp[upper - 1] + temp[upper]);
}

void ComputeShiftedRollingMedian(const double &source[], const int size, const int window, const int min_periods, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || window <= 0 || min_periods <= 0)
      return;

   for(int i = 0; i < size; ++i)
   {
      const int end_index = i - 1;
      if(end_index < 0)
         continue;

      const int start_index = MathMax(0, end_index - window + 1);
      int valid_count = 0;
      const double median = ComputeMedian(source, start_index, end_index, valid_count);
      if(valid_count >= min_periods && !IsMissing(median))
         output[i] = median;
   }
}

double ComputeHurstWindow(const double &close[], const int end_index, const int window)
{
   const int start_index = end_index - window + 1;
   const int returns_count = window - 1;
   if(start_index < 0 || returns_count < 10)
      return 0.5;

   double returns[];
   ArrayResize(returns, returns_count);

   double mean = 0.0;
   for(int i = 0; i < returns_count; ++i)
   {
      const double prev = close[start_index + i];
      if(prev == 0.0)
         return 0.5;
      returns[i] = (close[start_index + i + 1] - prev) / prev;
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

void ComputeRollingHurst(const double &close[], const int size, const int window, double &output[])
{
   InitMissingArray(output, size);
   if(size <= 0 || window <= 0)
      return;

   for(int i = window - 1; i < size; ++i)
      output[i] = ComputeHurstWindow(close, i, window);
}

void ComputeAdxExact(const double &high[], const double &low[], const double &close[], const int size, const int window, double &output[])
{
   InitZeroArray(output, size);
   if(size <= 0 || window <= 0 || size <= window)
      return;

   double true_range[];
   double pos_dm[];
   double neg_dm[];
   ArrayResize(true_range, size);
   ArrayResize(pos_dm, size);
   ArrayResize(neg_dm, size);

   true_range[0] = MissingValue();
   pos_dm[0] = MissingValue();
   neg_dm[0] = MissingValue();

   for(int i = 1; i < size; ++i)
   {
      const double pdm = MathMax(high[i], close[i - 1]);
      const double pdn = MathMin(low[i], close[i - 1]);
      true_range[i] = pdm - pdn;

      const double diff_up = high[i] - high[i - 1];
      const double diff_down = low[i - 1] - low[i];
      pos_dm[i] = ((diff_up > diff_down && diff_up > 0.0) ? MathAbs(diff_up) : 0.0);
      neg_dm[i] = ((diff_down > diff_up && diff_down > 0.0) ? MathAbs(diff_down) : 0.0);
   }

   const int work_size = size - (window - 1);
   if(work_size <= 0)
      return;

   double trs[];
   double dip[];
   double din[];
   ArrayResize(trs, work_size);
   ArrayResize(dip, work_size);
   ArrayResize(din, work_size);
   ArrayInitialize(trs, 0.0);
   ArrayInitialize(dip, 0.0);
   ArrayInitialize(din, 0.0);

   double initial_tr = 0.0;
   double initial_pos = 0.0;
   double initial_neg = 0.0;
   for(int i = 1; i <= window; ++i)
   {
      initial_tr += true_range[i];
      initial_pos += pos_dm[i];
      initial_neg += neg_dm[i];
   }
   trs[0] = initial_tr;
   dip[0] = initial_pos;
   din[0] = initial_neg;

   for(int i = 1; i < work_size - 1; ++i)
   {
      const int source_index = window + i;
      trs[i] = trs[i - 1] - (trs[i - 1] / window) + true_range[source_index];
      dip[i] = dip[i - 1] - (dip[i - 1] / window) + pos_dm[source_index];
      din[i] = din[i - 1] - (din[i - 1] / window) + neg_dm[source_index];
   }

   double di_plus[];
   double di_minus[];
   double dx[];
   ArrayResize(di_plus, work_size);
   ArrayResize(di_minus, work_size);
   ArrayResize(dx, work_size);
   ArrayInitialize(di_plus, 0.0);
   ArrayInitialize(di_minus, 0.0);
   ArrayInitialize(dx, 0.0);

   for(int i = 0; i < work_size; ++i)
   {
      if(trs[i] != 0.0)
      {
         di_plus[i] = 100.0 * (dip[i] / trs[i]);
         di_minus[i] = 100.0 * (din[i] / trs[i]);
      }
      const double denom = di_plus[i] + di_minus[i];
      if(denom != 0.0)
         dx[i] = 100.0 * MathAbs((di_plus[i] - di_minus[i]) / denom);
   }

   double adx_internal[];
   ArrayResize(adx_internal, work_size);
   ArrayInitialize(adx_internal, 0.0);

   if(window < work_size)
   {
      double dx_sum = 0.0;
      for(int i = 0; i < window; ++i)
         dx_sum += dx[i];
      adx_internal[window] = dx_sum / window;

      for(int i = window + 1; i < work_size; ++i)
         adx_internal[i] = ((adx_internal[i - 1] * (window - 1)) + dx[i - 1]) / window;
   }

   for(int i = 0; i < work_size; ++i)
      output[i + window - 1] = adx_internal[i];
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
   if(desired_direction == 0)
      return true;

   bool ok = false;
   if(desired_direction > 0)
      ok = trade.Buy(InpLots, _Symbol, 0.0, 0.0, 0.0, "EMA 1c947fe historical");
   else
      ok = trade.Sell(InpLots, _Symbol, 0.0, 0.0, 0.0, "EMA 1c947fe historical");

   if(ok)
      return true;

   Print("Open order failed. Retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   return false;
}

bool ComputeDesiredDirection(int &desired_direction, string &status)
{
   desired_direction = 0;
   status = "idle";

   MqlRates rates[];
   const int copied = CopyRates(_Symbol, _Period, 0, InpHistoryBars + 1, rates);
   if(copied <= 1)
   {
      status = "not_enough_rates";
      return false;
   }

   EnsureAscendingRates(rates);

   const int closed_count = copied - 1;
   const datetime current_bar_time = rates[copied - 1].time;
   if(closed_count <= 0)
   {
      status = "no_closed_bar";
      return false;
   }

   double close[];
   double high[];
   double low[];
   int dates[];
   int hours[];
   int minutes[];
   ArrayResize(close, closed_count);
   ArrayResize(high, closed_count);
   ArrayResize(low, closed_count);
   ArrayResize(dates, closed_count);
   ArrayResize(hours, closed_count);
   ArrayResize(minutes, closed_count);

   for(int i = 0; i < closed_count; ++i)
   {
      close[i] = rates[i].close;
      high[i] = rates[i].high;
      low[i] = rates[i].low;
      DecomposeTime(rates[i].time, dates[i], hours[i], minutes[i]);
   }

   double ema_fast[];
   double ema_slow[];
   double ema_trend[];
   double rsi[];
   double adx[];
   double atr[];
   double trix[];
   double hurst[];
   double trix_median[];

   ComputeEmaExact(close, closed_count, InpEmaFast, ema_fast);
   ComputeEmaExact(close, closed_count, InpEmaSlow, ema_slow);
   ComputeEmaExact(close, closed_count, InpTrendWindow, ema_trend);
   ComputeRsiExact(close, closed_count, InpRsiWindow, rsi);
   ComputeAdxExact(high, low, close, closed_count, InpAdxWindow, adx);
   ComputeAtrExact(high, low, close, closed_count, InpAtrWindow, atr);
   ComputeTrixExact(close, closed_count, InpTrixWindow, trix);
   ComputeRollingHurst(close, closed_count, InpHurstWindow, hurst);
   ComputeShiftedRollingMedian(trix, closed_count, InpTrixMedianWindow, InpTrixMedianMinPeriods, trix_median);

   int position = 0;
   double peak = 0.0;
   int raw_last = 0;

   for(int i = 0; i < closed_count; ++i)
   {
      const bool is_first_bar = (i == 0 || dates[i] != dates[i - 1]);
      const bool is_last_window = IsLastWindowBar(hours[i], minutes[i]);
      int raw = 0;

      if(is_first_bar)
      {
         position = 0;
         peak = 0.0;
         raw_last = 0;
         continue;
      }

      if(is_last_window)
      {
         position = 0;
         peak = 0.0;
         raw_last = 0;
         continue;
      }

      if(IsMissing(ema_fast[i]) || IsMissing(ema_slow[i]) || IsMissing(ema_trend[i]) || IsMissing(atr[i]))
      {
         raw_last = position;
         continue;
      }

      if(position != 0)
      {
         const double current_atr = atr[i];
         const double median_value = (IsMissing(trix_median[i]) ? 0.0 : trix_median[i]);
         const double current_trix = (IsMissing(trix[i]) ? median_value : trix[i]);
         const double previous_trix = (i > 0 && !IsMissing(trix[i - 1]) ? trix[i - 1] : median_value);

         bool trix_exit = false;
         if(position == 1 && current_trix < median_value && previous_trix >= median_value)
            trix_exit = true;
         else if(position == -1 && current_trix > median_value && previous_trix <= median_value)
            trix_exit = true;

         if(trix_exit)
         {
            position = 0;
            peak = 0.0;
            raw = 0;
         }
         else if(position == 1)
         {
            peak = MathMax(peak, close[i]);
            if(current_atr > 0.0 && close[i] < peak - InpAtrMult * current_atr)
            {
               position = 0;
               peak = 0.0;
               raw = 0;
            }
            else
               raw = 1;
         }
         else
         {
            peak = MathMin(peak, close[i]);
            if(current_atr > 0.0 && close[i] > peak + InpAtrMult * current_atr)
            {
               position = 0;
               peak = 0.0;
               raw = 0;
            }
            else
               raw = -1;
         }

         raw_last = raw;
         continue;
      }

      if((InpSkipHour12 && hours[i] == 12) || (InpSkipHour13 && hours[i] == 13))
      {
         raw_last = 0;
         continue;
      }

      if(IsEntryCutoffOrLater(hours[i], minutes[i]))
      {
         raw_last = 0;
         continue;
      }

      if(adx[i] < InpAdxThreshold)
      {
         raw_last = 0;
         continue;
      }

      if(!IsMissing(hurst[i]) && hurst[i] < InpHurstThreshold)
      {
         raw_last = 0;
         continue;
      }

      const double current_rsi = (IsMissing(rsi[i]) ? 50.0 : rsi[i]);

      if(i > 0 && !IsMissing(ema_fast[i - 1]) && !IsMissing(ema_slow[i - 1]))
      {
         const bool cross_up = (ema_fast[i] > ema_slow[i] && ema_fast[i - 1] <= ema_slow[i - 1]);
         const bool cross_down = (ema_fast[i] < ema_slow[i] && ema_fast[i - 1] >= ema_slow[i - 1]);

         if(cross_up && close[i] > ema_trend[i] && current_rsi > InpRsiLong)
         {
            position = 1;
            peak = close[i];
            raw = 1;
         }
         else if(cross_down && close[i] < ema_trend[i] && current_rsi < InpRsiShort)
         {
            position = -1;
            peak = close[i];
            raw = -1;
         }
      }

      raw_last = raw;
   }

   const int current_date = DateKey(current_bar_time);
   const int previous_closed_date = dates[closed_count - 1];
   desired_direction = (current_date == previous_closed_date ? raw_last : 0);
   status = "ok";
   return true;
}

void ProcessNewBar()
{
   int desired_direction = 0;
   string status = "";
   const bool computed = ComputeDesiredDirection(desired_direction, status);
   const int current_direction = CurrentPositionDirection();

   g_last_status = StringFormat(
      "status=%s desired=%d current=%d time=%s",
      status,
      desired_direction,
      current_direction,
      TimeToString(iTime(_Symbol, _Period, 0), TIME_DATE | TIME_MINUTES)
   );

   if(!computed)
      return;

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

   trade.SetExpertMagicNumber((int)InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetAsyncMode(false);
   g_last_bar_time = 0;
   g_last_status = "initialized";
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
}

void OnTick()
{
   const datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == 0)
      return;

   if(current_bar_time != g_last_bar_time)
   {
      g_last_bar_time = current_bar_time;
      ProcessNewBar();
   }

   Comment(
      "WDO EMA Historical 1c947fe\n",
      "Symbol: ", _Symbol, "  TF: ", EnumToString(_Period), "\n",
      g_last_status
   );
}
