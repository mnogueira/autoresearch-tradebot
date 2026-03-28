//+------------------------------------------------------------------+
//|                       WDO Stalker Strategy v10.0 GPT 5.4.mq5     |
//|                                Copyright 2026, OpenAI / Clarian  |
//+------------------------------------------------------------------+

#property copyright "Copyright 2026, OpenAI / Clarian"
#property link      "https://openai.com"
#property version   "10.1"

#include <Trade\Trade.mqh>

CTrade Trade;

string EA_Name = "WDO Stalker Strategy";
string EA_Version = "10.1 Time Filters GPT 5.4";

bool IsInProductionMode = true;

const double BIG_DOUBLE_NUMBER = 9999999.0;
const string ContinuousSeriesSymbol = "WDO$N";
const string RetracementIndicatorName = "Custom\\Daily Dynamic Retracement MN 1.0";
const string ContractRangeIndicatorName = "Custom\\WDO Contract MA Range v2.0 GPT 5.4";
const string LongOrderComment = "WDOStalkerV101-L";
const string ShortOrderComment = "WDOStalkerV101-S";

double tick_size = 0.0;
string TradingSymbol = "";

int hATR = INVALID_HANDLE;
int hDynamicRetracements = INVALID_HANDLE;
int hContractRangeFilter = INVALID_HANDLE;

double ATR[];
double UpperRetracementLevel[];
double LowerRetracementLevel[];
double DayHigh[];
double DayLow[];
double ContractPercDailyAvgRange[];

double PreviousHigh = 0.0;
double PreviousLow = BIG_DOUBLE_NUMBER;
datetime PreviousTickDay = 0;

bool IsFirstTickAfterInit = true;
datetime LastProcessedBarTime = 0;
datetime TimeCurrentBrazil = 0;
string sTimeCurrentBrazil = "";

ulong OpenLongOrderTicket = 0;
ulong OpenShortOrderTicket = 0;

input group "Position Sizing";
input double ContractsPerTrade = 1;  // Contracts per Trade

input group "Filter";
input double FilterAsPercOfContractMARange = 0.30;            // Filter as % of Contract MA Range vs Daily H/L
input int NumDaysToConsiderPreviousContractMARange = 5;       // Number of days to keep considering previous contract MA Range

input group "Open Signal";
input double RetracementLevel = 0.25;                         // Retracement level

input group "Entry Filters";
input int EntryStart_Hour = 10;                               // Earliest entry hour (GMT-3)
input int EntryStart_Minute = 0;                              // Earliest entry minute
input int LastEntry_Hour = 15;                                // Latest entry hour (inclusive, GMT-3)
input int LastEntry_Minute = 0;                               // Latest entry minute (inclusive)
input bool AllowMonday = true;                                // Allow Monday entries
input bool AllowTuesday = true;                               // Allow Tuesday entries
input bool AllowWednesday = true;                             // Allow Wednesday entries
input bool AllowThursday = true;                              // Allow Thursday entries
input bool AllowFriday = true;                                // Allow Friday entries

input group "Signal Strength Filters";
input int TrendEfficiencyWindowMinutes = 15;                  // Trend efficiency lookback in minutes
input bool ApplyTrendEfficiencyFilterToLongs = false;         // Apply directional trend efficiency filter to longs
input bool ApplyTrendEfficiencyFilterToShorts = false;        // Apply directional trend efficiency filter to shorts
input double MinDirectionalTrendEfficiency15m = 0.0;          // Minimum directional trend efficiency
input int VolumeWindowMinutes = 15;                           // Rolling signal-volume lookback in minutes
input bool ApplyVolumeFilterToLongs = false;                  // Apply signal-volume filter to longs
input bool ApplyVolumeFilterToShorts = false;                 // Apply signal-volume filter to shorts
input double MinSignalVolumeWindowSum = 0.0;                  // Minimum rolling signal-volume sum
input int RelativeVolumeLookbackDays = 20;                    // Same-minute relative-volume lookback in sessions
input bool ApplyRelativeVolumeFilterToLongs = false;          // Apply relative-volume filter to longs
input bool ApplyRelativeVolumeFilterToShorts = false;         // Apply relative-volume filter to shorts
input double MinRelativeVolumeAtTime = 0.0;                   // Minimum same-minute relative volume

input group "Risk Management";
input double SL_ATRMultiplier = 0.78;                         // Stop Loss (ATR Multiplier)
input double TP_ATRMultiplier = 0.36;                         // Take Profit (ATR Multiplier)
input ENUM_TIMEFRAMES ATRTimeFrame = PERIOD_M15;              // Timeframe to calculate the ATR
input uint ATR_Length = 20;                                   // ATR Length

input group "Market Info";
input int MarketClose_Hour = 18;                              // Market Close Hour (GMT-3)
input int MarketClose_Minute = 0;                             // Market Close Minute
input int MinutesBeforeMarketCloseToClosePositions = 5;       // Minutes before Market Close to close positions

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   IsInProductionMode = !MQLInfoInteger(MQL_TESTER);
   UpdateCurrentBrazilTime();

   if(!SymbolSelect(ContinuousSeriesSymbol, true))
   {
      Print(sTimeCurrentBrazil, " Error selecting symbol: ", ContinuousSeriesSymbol);
      return(INIT_FAILED);
   }

   ArraySetAsSeries(ATR, true);
   ArraySetAsSeries(UpperRetracementLevel, true);
   ArraySetAsSeries(LowerRetracementLevel, true);
   ArraySetAsSeries(DayHigh, true);
   ArraySetAsSeries(DayLow, true);
   ArraySetAsSeries(ContractPercDailyAvgRange, true);

   hATR = iATR(ContinuousSeriesSymbol, ATRTimeFrame, ATR_Length);

   hDynamicRetracements = iCustom(
                             ContinuousSeriesSymbol,
                             PERIOD_M1,
                             RetracementIndicatorName,
                             RetracementLevel
                          );

   hContractRangeFilter = iCustom(
                             ContinuousSeriesSymbol,
                             PERIOD_M1,
                             ContractRangeIndicatorName,
                             FilterAsPercOfContractMARange,
                             NumDaysToConsiderPreviousContractMARange
                          );

   if(hATR == INVALID_HANDLE || hDynamicRetracements == INVALID_HANDLE || hContractRangeFilter == INVALID_HANDLE)
   {
      Print(sTimeCurrentBrazil, " Error creating indicator handles. Error: ", GetLastError());
      return(INIT_FAILED);
   }

   TradingSymbol = GetSymbolToTrade(TimeCurrentBrazil);
   if(!PrepareTradingSymbol(TradingSymbol))
      return(INIT_FAILED);

   Print(EA_Name, " ", EA_Version, " initialized at: ", sTimeCurrentBrazil);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(hATR != INVALID_HANDLE)
      IndicatorRelease(hATR);
   if(hDynamicRetracements != INVALID_HANDLE)
      IndicatorRelease(hDynamicRetracements);
   if(hContractRangeFilter != INVALID_HANDLE)
      IndicatorRelease(hContractRangeFilter);

   UpdateCurrentBrazilTime();
   Print(EA_Name, " ", EA_Version, " deinitialized at: ", sTimeCurrentBrazil);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateCurrentBrazilTime();
   const datetime currentDay = DateOnly(TimeCurrentBrazil);

   if(IsFirstTickAfterInit || currentDay != PreviousTickDay)
   {
      const string nextTradingSymbol = GetSymbolToTrade(TimeCurrentBrazil);
      const bool symbolChanged = (nextTradingSymbol != TradingSymbol);

      TradingSymbol = nextTradingSymbol;
      if(symbolChanged)
      {
         if(!PrepareTradingSymbol(TradingSymbol))
            return;

         LastProcessedBarTime = 0;
         OpenLongOrderTicket = 0;
         OpenShortOrderTicket = 0;
      }

      PreviousHigh = 0.0;
      PreviousLow = BIG_DOUBLE_NUMBER;
      IsFirstTickAfterInit = false;
   }

   RefreshPendingOrderTickets(TradingSymbol);

   const datetime currentBarTime = iTime(TradingSymbol, PERIOD_M1, 0);
   if(currentBarTime <= 0)
   {
      Print(sTimeCurrentBrazil, " Error getting latest M1 bar for ", TradingSymbol, ". Error: ", GetLastError());
      return;
   }

   if(currentBarTime == LastProcessedBarTime)
      return;

   LastProcessedBarTime = currentBarTime;

   bool buy_opened = false;
   bool sell_opened = false;
   const bool HasOpenedPosition = GetPositionState(TradingSymbol, buy_opened, sell_opened);
   const bool HasReachedDayTimeLimit = HasReachedTradingCutoff(TimeCurrentBrazil);
   const bool IsAllowedEntryDay = IsAllowedTradingDay(TimeCurrentBrazil);
   const bool IsWithinEntryHours = IsWithinEntryWindow(TimeCurrentBrazil);
   const bool CanEnterNewTrades = (IsAllowedEntryDay && IsWithinEntryHours);

   if(HasReachedDayTimeLimit)
   {
      if(HasOpenedPosition)
      {
         if(Trade.PositionClose(TradingSymbol))
            Print(sTimeCurrentBrazil, " Position closed for ", TradingSymbol);
         else
            Print(sTimeCurrentBrazil, " Error closing position for ", TradingSymbol, ": ", Trade.ResultRetcodeDescription());
      }

      DeleteTrackedPendingOrders();
      PreviousTickDay = currentDay;
      return;
   }

   if(!CanEnterNewTrades)
      DeleteTrackedPendingOrders();

   if(!LoadLatestIndicatorValues())
      return;

   const double atrValue = ATR[0];
   const double contractRangeFilterValue = ContractPercDailyAvgRange[0];
   const double currentDayHigh = DayHigh[0];
   const double currentDayLow = DayLow[0];
   const double currentDayRange = currentDayHigh - currentDayLow;
   double trendEfficiencyRaw = 0.0;
   double signalVolumeSum = 0.0;
   double relativeVolumeAtTime = 0.0;
   const bool hasTrendEfficiencyRaw = TryGetDirectionalTrendEfficiencyRaw(TrendEfficiencyWindowMinutes, trendEfficiencyRaw);
   const bool hasSignalVolumeSum = TryGetSignalVolumeSum(VolumeWindowMinutes, signalVolumeSum);
   const bool hasRelativeVolumeAtTime = TryGetRelativeVolumeAtTime(
      VolumeWindowMinutes,
      RelativeVolumeLookbackDays,
      relativeVolumeAtTime
   );

   const bool IsDailyRangeBiggerThanContractRange =
      (currentDayRange > 0.0 && contractRangeFilterValue > 0.0 && currentDayRange >= contractRangeFilterValue);

   if(!HasOpenedPosition && CanEnterNewTrades && IsDailyRangeBiggerThanContractRange && atrValue > 0.0)
   {
      if(currentDayHigh > PreviousHigh)
      {
         DeletePendingOrder(OpenShortOrderTicket);
         RefreshPendingOrderTickets(TradingSymbol);

         const double basePrice = Round2Ticksize(UpperRetracementLevel[0]);
         const double stopLoss = Round2Ticksize(basePrice - (atrValue * SL_ATRMultiplier));
         const double takeProfit = Round2Ticksize(basePrice + (atrValue * TP_ATRMultiplier));

         if(PassesDirectionalTrendEfficiency(1, hasTrendEfficiencyRaw, trendEfficiencyRaw)
         && PassesSignalVolume(1, hasSignalVolumeSum, signalVolumeSum)
         && PassesRelativeVolume(1, hasRelativeVolumeAtTime, relativeVolumeAtTime))
         {
            if(OpenLongOrderTicket == 0)
               PlaceBuyLimitOrder(basePrice, stopLoss, takeProfit);
            else
               ModifyPendingOrder(OpenLongOrderTicket, basePrice, stopLoss, takeProfit);
         }
      }
      else if(currentDayLow < PreviousLow)
      {
         DeletePendingOrder(OpenLongOrderTicket);
         RefreshPendingOrderTickets(TradingSymbol);

         const double basePrice = Round2Ticksize(LowerRetracementLevel[0]);
         const double stopLoss = Round2Ticksize(basePrice + (atrValue * SL_ATRMultiplier));
         const double takeProfit = Round2Ticksize(basePrice - (atrValue * TP_ATRMultiplier));

         if(PassesDirectionalTrendEfficiency(-1, hasTrendEfficiencyRaw, trendEfficiencyRaw)
         && PassesSignalVolume(-1, hasSignalVolumeSum, signalVolumeSum)
         && PassesRelativeVolume(-1, hasRelativeVolumeAtTime, relativeVolumeAtTime))
         {
            if(OpenShortOrderTicket == 0)
               PlaceSellLimitOrder(basePrice, stopLoss, takeProfit);
            else
               ModifyPendingOrder(OpenShortOrderTicket, basePrice, stopLoss, takeProfit);
         }
      }
   }

   PreviousTickDay = currentDay;

   if(currentDayHigh > PreviousHigh)
      PreviousHigh = currentDayHigh;
   if(currentDayLow < PreviousLow)
      PreviousLow = currentDayLow;
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool IsAllowedTradingDay(const datetime current_time_brazil)
{
   MqlDateTime time_parts;
   TimeToStruct(current_time_brazil, time_parts);

   switch(time_parts.day_of_week)
   {
      case 1: return AllowMonday;
      case 2: return AllowTuesday;
      case 3: return AllowWednesday;
      case 4: return AllowThursday;
      case 5: return AllowFriday;
      default: return false;
   }
}

bool IsWithinEntryWindow(const datetime current_time_brazil)
{
   MqlDateTime time_parts;
   TimeToStruct(current_time_brazil, time_parts);

   const int current_minutes = (time_parts.hour * 60) + time_parts.min;
   const int start_minutes = (EntryStart_Hour * 60) + EntryStart_Minute;
   const int end_minutes = (LastEntry_Hour * 60) + LastEntry_Minute;

   return (current_minutes >= start_minutes && current_minutes <= end_minutes);
}

bool PassesDirectionalTrendEfficiency(const int direction, const bool hasValue, const double rawValue)
{
   if(direction == 1 && !ApplyTrendEfficiencyFilterToLongs)
      return(true);

   if(direction == -1 && !ApplyTrendEfficiencyFilterToShorts)
      return(true);

   if(!hasValue || !MathIsValidNumber(rawValue))
      return(false);

   const double directionalValue = (direction == 1) ? rawValue : -rawValue;
   return(directionalValue >= MinDirectionalTrendEfficiency15m);
}

bool PassesSignalVolume(const int direction, const bool hasValue, const double rawValue)
{
   if(direction == 1 && !ApplyVolumeFilterToLongs)
      return(true);

   if(direction == -1 && !ApplyVolumeFilterToShorts)
      return(true);

   if(!hasValue || !MathIsValidNumber(rawValue))
      return(false);

   return(rawValue >= MinSignalVolumeWindowSum);
}

bool PassesRelativeVolume(const int direction, const bool hasValue, const double rawValue)
{
   if(direction == 1 && !ApplyRelativeVolumeFilterToLongs)
      return(true);

   if(direction == -1 && !ApplyRelativeVolumeFilterToShorts)
      return(true);

   if(!hasValue || !MathIsValidNumber(rawValue))
      return(false);

   return(rawValue >= MinRelativeVolumeAtTime);
}

bool TryGetDirectionalTrendEfficiencyRaw(const int windowMinutes, double &rawValue)
{
   rawValue = 0.0;
   if(windowMinutes <= 0)
      return(false);

   const datetime currentBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, 0);
   if(currentBarTime <= 0)
      return(false);

   const datetime sessionDate = DateOnly(currentBarTime);
   const int oldestShift = windowMinutes + 1;
   const datetime oldestBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, oldestShift);
   if(oldestBarTime <= 0 || DateOnly(oldestBarTime) != sessionDate)
      return(false);

   const double previousClose = iClose(ContinuousSeriesSymbol, PERIOD_M1, 1);
   const double closeNBarsAgo = iClose(ContinuousSeriesSymbol, PERIOD_M1, oldestShift);

   double realizedAbs = 0.0;
   for(int shift = 1; shift <= windowMinutes; shift++)
   {
      const datetime newerBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, shift);
      const datetime olderBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, shift + 1);
      if(newerBarTime <= 0 || olderBarTime <= 0)
         return(false);

      if(DateOnly(newerBarTime) != sessionDate || DateOnly(olderBarTime) != sessionDate)
         return(false);

      const double newerClose = iClose(ContinuousSeriesSymbol, PERIOD_M1, shift);
      const double olderClose = iClose(ContinuousSeriesSymbol, PERIOD_M1, shift + 1);
      realizedAbs += MathAbs(newerClose - olderClose);
   }

   if(realizedAbs <= 0.0)
      return(false);

   rawValue = (previousClose - closeNBarsAgo) / realizedAbs;
   return(MathIsValidNumber(rawValue));
}

bool TryGetSignalVolumeSumAtShift(const int referenceShift, const int windowMinutes, double &rawValue)
{
   rawValue = 0.0;
   if(windowMinutes <= 0)
      return(false);

   const datetime currentBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, referenceShift);
   if(currentBarTime <= 0)
      return(false);

   const datetime sessionDate = DateOnly(currentBarTime);
   for(int shiftOffset = 1; shiftOffset <= windowMinutes; shiftOffset++)
   {
      const int shift = referenceShift + shiftOffset;
      const datetime barTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, shift);
      if(barTime <= 0 || DateOnly(barTime) != sessionDate)
         return(false);

      const long barVolume = iVolume(ContinuousSeriesSymbol, PERIOD_M1, shift);
      if(barVolume < 0)
         return(false);

      rawValue += (double)barVolume;
   }

   return(MathIsValidNumber(rawValue));
}

bool TryGetSignalVolumeSum(const int windowMinutes, double &rawValue)
{
   return(TryGetSignalVolumeSumAtShift(0, windowMinutes, rawValue));
}

int MinuteOfDay(const datetime value)
{
   MqlDateTime dt;
   TimeToStruct(value, dt);
   return((dt.hour * 60) + dt.min);
}

bool TryGetRelativeVolumeAtTime(const int volumeWindowMinutes, const int lookbackDays, double &rawValue)
{
   rawValue = 0.0;
   if(lookbackDays <= 0)
      return(false);

   double currentSignalVolume = 0.0;
   if(!TryGetSignalVolumeSum(volumeWindowMinutes, currentSignalVolume))
      return(false);

   const datetime currentBarTime = iTime(ContinuousSeriesSymbol, PERIOD_M1, 0);
   if(currentBarTime <= 0)
      return(false);

   const datetime sessionDate = DateOnly(currentBarTime);
   const int minuteOfDay = MinuteOfDay(currentBarTime);
   const int minPeriods = MathMax(3, MathMin(lookbackDays, 10));
   const int maxCalendarDays = MathMax(lookbackDays * 6, minPeriods * 3);

   double sampleSum = 0.0;
   int samples = 0;
   for(int dayOffset = 1; dayOffset <= maxCalendarDays && samples < lookbackDays; dayOffset++)
   {
      const datetime candidateSession = sessionDate - (dayOffset * 86400);
      const datetime candidateTime = candidateSession + (minuteOfDay * 60);
      const int candidateShift = iBarShift(ContinuousSeriesSymbol, PERIOD_M1, candidateTime, true);
      if(candidateShift < 0)
         continue;

      if(iTime(ContinuousSeriesSymbol, PERIOD_M1, candidateShift) != candidateTime)
         continue;

      double historicalSignalVolume = 0.0;
      if(!TryGetSignalVolumeSumAtShift(candidateShift, volumeWindowMinutes, historicalSignalVolume))
         continue;

      sampleSum += historicalSignalVolume;
      samples++;
   }

   if(samples < minPeriods)
      return(false);

   const double expectedVolume = sampleSum / samples;
   if(expectedVolume <= 0.0)
      return(false);

   rawValue = currentSignalVolume / expectedVolume;
   return(MathIsValidNumber(rawValue));
}

void UpdateCurrentBrazilTime()
{
   if(IsInProductionMode)
      TimeCurrentBrazil = GetCurrentDatetimeWithGMTOffset(-3);
   else
      TimeCurrentBrazil = TimeCurrent();

   sTimeCurrentBrazil = (string)TimeCurrentBrazil;
}

bool PrepareTradingSymbol(const string symbol)
{
   if(symbol == "")
      return(false);

   if(!SymbolSelect(symbol, true))
   {
      Print(sTimeCurrentBrazil, " Error selecting trading symbol: ", symbol);
      return(false);
   }

   const double symbol_tick_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   if(symbol_tick_size <= 0.0)
   {
      Print(sTimeCurrentBrazil, " Invalid tick size for ", symbol);
      return(false);
   }

   tick_size = symbol_tick_size;
   Trade.SetTypeFillingBySymbol(symbol);
   return(true);
}

bool LoadLatestIndicatorValues()
{
   if(CopyBuffer(hATR, 0, 0, 1, ATR) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer ATR error: ", GetLastError());
      return(false);
   }

   if(CopyBuffer(hContractRangeFilter, 0, 0, 1, ContractPercDailyAvgRange) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer Contract Range error: ", GetLastError());
      return(false);
   }

   if(CopyBuffer(hDynamicRetracements, 0, 0, 1, DayHigh) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer Dynamic Retracements High error: ", GetLastError());
      return(false);
   }

   if(CopyBuffer(hDynamicRetracements, 1, 0, 1, UpperRetracementLevel) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer Dynamic Retracements Upper error: ", GetLastError());
      return(false);
   }

   if(CopyBuffer(hDynamicRetracements, 3, 0, 1, LowerRetracementLevel) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer Dynamic Retracements Lower error: ", GetLastError());
      return(false);
   }

   if(CopyBuffer(hDynamicRetracements, 4, 0, 1, DayLow) != 1)
   {
      Print(sTimeCurrentBrazil, " CopyBuffer Dynamic Retracements Low error: ", GetLastError());
      return(false);
   }

   return(true);
}

bool GetPositionState(const string symbol, bool &buy_opened, bool &sell_opened)
{
   buy_opened = false;
   sell_opened = false;

   if(!PositionSelect(symbol))
      return(false);

   const ENUM_POSITION_TYPE positionType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   if(positionType == POSITION_TYPE_BUY)
      buy_opened = true;
   else if(positionType == POSITION_TYPE_SELL)
      sell_opened = true;

   return(buy_opened || sell_opened);
}

bool HasReachedTradingCutoff(const datetime currentTime)
{
   const datetime dayStart = DateOnly(currentTime);
   const datetime timeLimit = dayStart
                            + (MarketClose_Hour * 3600)
                            + (MarketClose_Minute * 60)
                            - (MinutesBeforeMarketCloseToClosePositions * 60);

   return(currentTime >= timeLimit);
}

ulong FindPendingOrderTicket(const string symbol, const ENUM_ORDER_TYPE orderType, const string orderComment)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;

      if(OrderGetString(ORDER_SYMBOL) != symbol)
         continue;

      if(OrderGetString(ORDER_COMMENT) != orderComment)
         continue;

      const ENUM_ORDER_TYPE currentOrderType = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      const ENUM_ORDER_STATE currentOrderState = (ENUM_ORDER_STATE)OrderGetInteger(ORDER_STATE);
      if(currentOrderType != orderType)
         continue;

      if(currentOrderState == ORDER_STATE_PLACED || currentOrderState == ORDER_STATE_PARTIAL)
         return(ticket);
   }

   return(0);
}

void RefreshPendingOrderTickets(const string symbol)
{
   OpenLongOrderTicket = FindPendingOrderTicket(symbol, ORDER_TYPE_BUY_LIMIT, LongOrderComment);
   OpenShortOrderTicket = FindPendingOrderTicket(symbol, ORDER_TYPE_SELL_LIMIT, ShortOrderComment);
}

bool DeletePendingOrder(ulong &ticket)
{
   if(ticket == 0)
      return(true);

   if(!OrderSelect(ticket))
   {
      ticket = 0;
      return(true);
   }

   const ENUM_ORDER_STATE state = (ENUM_ORDER_STATE)OrderGetInteger(ORDER_STATE);
   if(state != ORDER_STATE_PLACED && state != ORDER_STATE_PARTIAL)
   {
      ticket = 0;
      return(true);
   }

   const ulong orderTicket = ticket;
   if(!Trade.OrderDelete(orderTicket))
   {
      Print(sTimeCurrentBrazil, " Error deleting pending order #", orderTicket, ": ", Trade.ResultRetcodeDescription());
      return(false);
   }

   ticket = 0;
   return(true);
}

void DeleteTrackedPendingOrders()
{
   RefreshPendingOrderTickets(TradingSymbol);
   DeletePendingOrder(OpenLongOrderTicket);
   DeletePendingOrder(OpenShortOrderTicket);
}

bool IsSuccessfulTradeRetcode()
{
   const uint retcode = Trade.ResultRetcode();
   return(retcode == TRADE_RETCODE_PLACED || retcode == TRADE_RETCODE_DONE || retcode == TRADE_RETCODE_DONE_PARTIAL);
}

bool PlaceBuyLimitOrder(const double basePrice, const double stopLoss, const double takeProfit)
{
   if(!Trade.BuyLimit(ContractsPerTrade, basePrice, TradingSymbol, stopLoss, takeProfit, ORDER_TIME_DAY, 0, LongOrderComment))
   {
      Print(sTimeCurrentBrazil, " Error placing buy limit order: ", Trade.ResultRetcodeDescription());
      return(false);
   }

   if(!IsSuccessfulTradeRetcode())
   {
      Print(sTimeCurrentBrazil, " Buy limit rejected: ", Trade.ResultRetcodeDescription());
      return(false);
   }

   OpenLongOrderTicket = Trade.ResultOrder();
   return(true);
}

bool PlaceSellLimitOrder(const double basePrice, const double stopLoss, const double takeProfit)
{
   if(!Trade.SellLimit(ContractsPerTrade, basePrice, TradingSymbol, stopLoss, takeProfit, ORDER_TIME_DAY, 0, ShortOrderComment))
   {
      Print(sTimeCurrentBrazil, " Error placing sell limit order: ", Trade.ResultRetcodeDescription());
      return(false);
   }

   if(!IsSuccessfulTradeRetcode())
   {
      Print(sTimeCurrentBrazil, " Sell limit rejected: ", Trade.ResultRetcodeDescription());
      return(false);
   }

   OpenShortOrderTicket = Trade.ResultOrder();
   return(true);
}

bool ModifyPendingOrder(const ulong ticket, const double basePrice, const double stopLoss, const double takeProfit)
{
   if(ticket == 0)
      return(false);

   if(!Trade.OrderModify(ticket, basePrice, stopLoss, takeProfit, ORDER_TIME_DAY, 0, 0))
   {
      Print(sTimeCurrentBrazil, " Error modifying pending order #", ticket, ": ", Trade.ResultRetcodeDescription());
      return(false);
   }

   if(!IsSuccessfulTradeRetcode())
   {
      Print(sTimeCurrentBrazil, " Pending order modification rejected for #", ticket, ": ", Trade.ResultRetcodeDescription());
      return(false);
   }

   return(true);
}

string GetSymbolToTrade(datetime BaseDate)
{
   if(!IsInProductionMode)
      return(ContinuousSeriesSymbol);

   MqlDateTime cdtBaseDate;
   TimeToStruct(BaseDate, cdtBaseDate);
   const datetime baseDay = DateOnly(BaseDate);
   const datetime lastWorkingDayOfBaseMonth = GetLastWorkingDay(BaseDate);

   if(baseDay == lastWorkingDayOfBaseMonth)
   {
      cdtBaseDate.mon++;
      if(cdtBaseDate.mon > 12)
      {
         cdtBaseDate.mon = 1;
         cdtBaseDate.year++;
      }
   }

   string monthLetter;

   switch(cdtBaseDate.mon)
   {
      case 12: monthLetter = "F"; break;
      case 1:  monthLetter = "G"; break;
      case 2:  monthLetter = "H"; break;
      case 3:  monthLetter = "J"; break;
      case 4:  monthLetter = "K"; break;
      case 5:  monthLetter = "M"; break;
      case 6:  monthLetter = "N"; break;
      case 7:  monthLetter = "Q"; break;
      case 8:  monthLetter = "U"; break;
      case 9:  monthLetter = "V"; break;
      case 10: monthLetter = "X"; break;
      case 11: monthLetter = "Z"; break;
      default: return("");
   }

   int contractYear = cdtBaseDate.year;
   if(cdtBaseDate.mon == 12)
      contractYear++;

   const string yearSuffix = StringSubstr((string)contractYear, 2, 2);
   return("WDO" + monthLetter + yearSuffix);
}

datetime GetLastWorkingDay(datetime BaseDate)
{
   MqlDateTime dt;
   TimeToStruct(BaseDate, dt);

   dt.day = DaysInMonth(dt.year, dt.mon);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;

   datetime lastDay = StructToTime(dt);

   while(true)
   {
      MqlDateTime check;
      TimeToStruct(lastDay, check);
      if(check.day_of_week != 0 && check.day_of_week != 6)
         break;

      lastDay -= 86400;
   }

   return(DateOnly(lastDay));
}

double Round2Ticksize(const double price)
{
   const string symbol = (TradingSymbol == "") ? ContinuousSeriesSymbol : TradingSymbol;
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return(NormalizeDouble(round(price / tick_size) * tick_size, digits));
}

datetime GetCurrentDatetimeWithGMTOffset(int GMTOffset)
{
   if(GMTOffset == 0)
      return(TimeGMT());

   return(TimeGMT() + (GMTOffset * 3600));
}

int DaysInMonth(const int year, const int month)
{
   switch(month)
   {
      case 1:
      case 3:
      case 5:
      case 7:
      case 8:
      case 10:
      case 12:
         return(31);

      case 4:
      case 6:
      case 9:
      case 11:
         return(30);

      case 2:
      {
         const bool isLeapYear = ((year % 4 == 0 && year % 100 != 0) || (year % 400 == 0));
         return(isLeapYear ? 29 : 28);
      }
   }

   return(30);
}

datetime DateOnly(const datetime value)
{
   MqlDateTime dt;
   TimeToStruct(value, dt);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;
   return(StructToTime(dt));
}

double OnTester()
{
   if(TesterStatistics(STAT_EQUITYDD_PERCENT) != 0)
      return(TesterStatistics(STAT_PROFIT) / TesterStatistics(STAT_EQUITYDD_PERCENT));

   return(0);
}
