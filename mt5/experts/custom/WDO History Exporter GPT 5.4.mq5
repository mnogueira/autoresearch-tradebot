//+------------------------------------------------------------------+
//|                   WDO History Exporter GPT 5.4.mq5               |
//|                                Copyright 2026, OpenAI / Clarian  |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, OpenAI / Clarian"
#property link      "https://openai.com"
#property version   "1.0"

input string   InpSymbolName      = "";
input datetime InpFromDate        = D'2021.03.22 00:00:00';
input datetime InpToDate          = D'2026.03.20 23:59:59';
input bool     InpExportM1Bars    = true;
input bool     InpExportTicks     = false;
input int      InpTickChunkDays   = 1;
input string   InpOutputPrefix    = "wdo_history_export";
input bool     InpUseCommonFiles  = true;

bool g_has_exported = false;

string ActiveSymbol()
{
   if(StringLen(InpSymbolName) > 0)
      return InpSymbolName;

   return _Symbol;
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

void ReverseRates(MqlRates &rates[])
{
   const int total = ArraySize(rates);
   for(int i = 0; i < total / 2; ++i)
   {
      MqlRates tmp = rates[i];
      rates[i] = rates[total - 1 - i];
      rates[total - 1 - i] = tmp;
   }
}

void ReverseTicks(MqlTick &ticks[])
{
   const int total = ArraySize(ticks);
   for(int i = 0; i < total / 2; ++i)
   {
      MqlTick tmp = ticks[i];
      ticks[i] = ticks[total - 1 - i];
      ticks[total - 1 - i] = tmp;
   }
}

int OpenCsv(string file_name)
{
   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;

   return FileOpen(file_name, flags, ',');
}

bool ExportM1Bars(const string symbol)
{
   MqlRates rates[];
   ResetLastError();
   const int copied = CopyRates(symbol, PERIOD_M1, InpFromDate, InpToDate, rates);
   if(copied <= 0)
   {
      PrintFormat("CopyRates failed for %s M1. Error=%d", symbol, GetLastError());
      return false;
   }

   if(rates[0].time > rates[copied - 1].time)
      ReverseRates(rates);

   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const string file_name = StringFormat(
      "%s_%s_m1.csv",
      SanitizeToken(InpOutputPrefix),
      SanitizeToken(symbol)
   );

   const int handle = OpenCsv(file_name);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("FileOpen failed for %s. Error=%d", file_name, GetLastError());
      return false;
   }

   FileWrite(handle, "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume");
   for(int i = 0; i < copied; ++i)
   {
      FileWrite(
         handle,
         TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         (long)rates[i].tick_volume,
         rates[i].spread,
         (long)rates[i].real_volume
      );

      if((i + 1) % 10000 == 0)
         FileFlush(handle);
   }

   FileFlush(handle);
   FileClose(handle);

   PrintFormat(
      "Exported %d M1 bars for %s to %s",
      copied,
      symbol,
      file_name
   );
   return true;
}

bool ExportTicks(const string symbol)
{
   const string file_name = StringFormat(
      "%s_%s_ticks.csv",
      SanitizeToken(InpOutputPrefix),
      SanitizeToken(symbol)
   );

   const int handle = OpenCsv(file_name);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("FileOpen failed for %s. Error=%d", file_name, GetLastError());
      return false;
   }

   FileWrite(handle, "time_msc", "time", "bid", "ask", "last", "volume", "volume_real", "flags");

   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const ulong chunk_millis = (ulong)MathMax(1, InpTickChunkDays) * (ulong)86400000;
   ulong cursor = (ulong)InpFromDate * (ulong)1000;
   const ulong stop = (ulong)InpToDate * (ulong)1000 + (ulong)999;
   long total_ticks = 0;

   while(cursor <= stop)
   {
      ulong chunk_stop = cursor + chunk_millis - (ulong)1;
      if(chunk_stop > stop)
         chunk_stop = stop;

      MqlTick ticks[];
      ResetLastError();
      const int copied = CopyTicksRange(symbol, ticks, COPY_TICKS_ALL, cursor, chunk_stop);
      if(copied < 0)
      {
         FileClose(handle);
         PrintFormat(
            "CopyTicksRange failed for %s. Cursor=%I64u Stop=%I64u Error=%d",
            symbol,
            cursor,
            chunk_stop,
            GetLastError()
         );
         return false;
      }

      if(copied > 0)
      {
         if(ticks[0].time_msc > ticks[copied - 1].time_msc)
            ReverseTicks(ticks);

         for(int i = 0; i < copied; ++i)
         {
            FileWrite(
               handle,
               (long)ticks[i].time_msc,
               TimeToString((datetime)(ticks[i].time_msc / (ulong)1000), TIME_DATE | TIME_MINUTES | TIME_SECONDS),
               DoubleToString(ticks[i].bid, digits),
               DoubleToString(ticks[i].ask, digits),
               DoubleToString(ticks[i].last, digits),
               (long)ticks[i].volume,
               DoubleToString(ticks[i].volume_real, 2),
               ticks[i].flags
            );
         }

         total_ticks += copied;
         FileFlush(handle);
      }

      cursor = chunk_stop + (ulong)1;
   }

   FileClose(handle);

   PrintFormat(
      "Exported %I64d ticks for %s to %s",
      total_ticks,
      symbol,
      file_name
   );
   return true;
}

bool ExportAll()
{
   const string symbol = ActiveSymbol();

   if(!SymbolSelect(symbol, true))
   {
      PrintFormat("SymbolSelect failed for %s. Error=%d", symbol, GetLastError());
      return false;
   }

   PrintFormat(
      "Starting export for %s from %s to %s. CommonPath=%s",
      symbol,
      TimeToString(InpFromDate, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      TimeToString(InpToDate, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      TerminalInfoString(TERMINAL_COMMONDATA_PATH)
   );

   bool ok = true;

   if(InpExportM1Bars)
      ok = ExportM1Bars(symbol) && ok;

   if(InpExportTicks)
      ok = ExportTicks(symbol) && ok;

   return ok;
}

int OnInit()
{
   if(InpToDate < InpFromDate)
   {
      Print("InpToDate must be >= InpFromDate.");
      return INIT_PARAMETERS_INCORRECT;
   }

   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(g_has_exported)
      return;

   g_has_exported = true;
   const bool ok = ExportAll();
   PrintFormat("Export finished. Success=%s", ok ? "true" : "false");
   ExpertRemove();
}
