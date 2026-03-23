//+------------------------------------------------------------------+
//|                  WDO History Exporter GPT 5.4.mq5                |
//|                               Copyright 2026, OpenAI / Clarian   |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, OpenAI / Clarian"
#property link      "https://openai.com"
#property version   "1.1"

input string   InpSymbolName      = "";
input datetime InpFromDate        = D'2021.03.22 00:00:00';
input datetime InpToDate          = D'2026.03.20 23:59:59';
input bool     InpExportM1Bars    = true;
input bool     InpExportTicks     = false;
input int      InpTickChunkDays   = 1;
input string   InpOutputPrefix    = "wdo_history_export";
input bool     InpUseCommonFiles  = true;

string g_symbol = "";
int g_digits = 0;
bool g_is_ready = false;
bool g_had_error = false;

int g_m1_handle = INVALID_HANDLE;
string g_m1_file_name = "";
datetime g_last_chart_bar_time = 0;
datetime g_last_written_m1_time = 0;
long g_m1_rows = 0;

int g_tick_handle = INVALID_HANDLE;
string g_tick_file_name = "";
ulong g_last_written_tick_msc = 0;
long g_tick_rows = 0;

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

int CommonFlag()
{
   return InpUseCommonFiles ? FILE_COMMON : 0;
}

void DeleteExistingFile(const string file_name)
{
   ResetLastError();
   FileDelete(file_name, CommonFlag());
}

int OpenCsvForAppend(const string file_name)
{
   int flags = FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;

   return FileOpen(file_name, flags, ',');
}

bool OpenM1File()
{
   g_m1_file_name = StringFormat(
      "%s_%s_m1.csv",
      SanitizeToken(InpOutputPrefix),
      SanitizeToken(g_symbol)
   );
   DeleteExistingFile(g_m1_file_name);

   g_m1_handle = OpenCsvForAppend(g_m1_file_name);
   if(g_m1_handle == INVALID_HANDLE)
   {
      PrintFormat("FileOpen failed for %s. Error=%d", g_m1_file_name, GetLastError());
      return false;
   }

   if(FileSize(g_m1_handle) == 0)
      FileWrite(g_m1_handle, "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume");

   FileSeek(g_m1_handle, 0, SEEK_END);
   return true;
}

bool OpenTickFile()
{
   g_tick_file_name = StringFormat(
      "%s_%s_ticks.csv",
      SanitizeToken(InpOutputPrefix),
      SanitizeToken(g_symbol)
   );
   DeleteExistingFile(g_tick_file_name);

   g_tick_handle = OpenCsvForAppend(g_tick_file_name);
   if(g_tick_handle == INVALID_HANDLE)
   {
      PrintFormat("FileOpen failed for %s. Error=%d", g_tick_file_name, GetLastError());
      return false;
   }

   if(FileSize(g_tick_handle) == 0)
      FileWrite(g_tick_handle, "time_msc", "time", "bid", "ask", "last", "volume", "volume_real", "flags");

   FileSeek(g_tick_handle, 0, SEEK_END);
   return true;
}

bool EnsureReady()
{
   if(g_is_ready)
      return true;

   g_symbol = ActiveSymbol();
   if(!SymbolSelect(g_symbol, true))
   {
      PrintFormat("SymbolSelect failed for %s. Error=%d", g_symbol, GetLastError());
      return false;
   }

   g_digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);

   PrintFormat(
      "Starting streaming export for %s from %s to %s. CommonPath=%s",
      g_symbol,
      TimeToString(InpFromDate, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      TimeToString(InpToDate, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      TerminalInfoString(TERMINAL_COMMONDATA_PATH)
   );

   if(InpExportM1Bars && !OpenM1File())
      return false;

   if(InpExportTicks && !OpenTickFile())
      return false;

   g_is_ready = true;
   return true;
}

bool WriteM1BarShift(const int shift)
{
   if(g_m1_handle == INVALID_HANDLE)
      return true;

   MqlRates rates[1];
   ResetLastError();
   const int copied = CopyRates(g_symbol, PERIOD_M1, shift, 1, rates);
   if(copied != 1)
   {
      PrintFormat("CopyRates failed for %s shift=%d. Error=%d", g_symbol, shift, GetLastError());
      return false;
   }

   const datetime bar_time = rates[0].time;
   if(bar_time < InpFromDate || bar_time > InpToDate)
      return true;

   if(bar_time <= g_last_written_m1_time)
      return true;

   FileWrite(
      g_m1_handle,
      TimeToString(bar_time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(rates[0].open, g_digits),
      DoubleToString(rates[0].high, g_digits),
      DoubleToString(rates[0].low, g_digits),
      DoubleToString(rates[0].close, g_digits),
      (long)rates[0].tick_volume,
      rates[0].spread,
      (long)rates[0].real_volume
   );

   g_last_written_m1_time = bar_time;
   ++g_m1_rows;

   if((g_m1_rows % 10000) == 0)
      FileFlush(g_m1_handle);

   return true;
}

bool WriteCurrentTick()
{
   if(g_tick_handle == INVALID_HANDLE)
      return true;

   MqlTick tick;
   if(!SymbolInfoTick(g_symbol, tick))
      return false;

   if(tick.time_msc <= g_last_written_tick_msc)
      return true;

   const datetime tick_time = (datetime)(tick.time_msc / (ulong)1000);
   if(tick_time < InpFromDate || tick_time > InpToDate)
      return true;

   FileWrite(
      g_tick_handle,
      (long)tick.time_msc,
      TimeToString(tick_time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(tick.bid, g_digits),
      DoubleToString(tick.ask, g_digits),
      DoubleToString(tick.last, g_digits),
      (long)tick.volume,
      DoubleToString(tick.volume_real, 2),
      tick.flags
   );

   g_last_written_tick_msc = tick.time_msc;
   ++g_tick_rows;

   if((g_tick_rows % 10000) == 0)
      FileFlush(g_tick_handle);

   return true;
}

void CloseFiles()
{
   if(g_m1_handle != INVALID_HANDLE)
   {
      FileFlush(g_m1_handle);
      FileClose(g_m1_handle);
      g_m1_handle = INVALID_HANDLE;
   }

   if(g_tick_handle != INVALID_HANDLE)
   {
      FileFlush(g_tick_handle);
      FileClose(g_tick_handle);
      g_tick_handle = INVALID_HANDLE;
   }
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
   if(!EnsureReady())
   {
      g_had_error = true;
      return;
   }

   if(!WriteCurrentTick())
      g_had_error = true;

   const datetime chart_bar_time = iTime(g_symbol, PERIOD_M1, 0);
   if(chart_bar_time <= 0)
      return;

   if(g_last_chart_bar_time == 0)
   {
      g_last_chart_bar_time = chart_bar_time;
      return;
   }

   if(chart_bar_time != g_last_chart_bar_time)
   {
      if(!WriteM1BarShift(1))
         g_had_error = true;
      g_last_chart_bar_time = chart_bar_time;
   }
}

void OnDeinit(const int reason)
{
   if(g_is_ready && InpExportM1Bars)
   {
      if(!WriteM1BarShift(0))
         g_had_error = true;
   }

   CloseFiles();

   PrintFormat(
      "Export finished. Success=%s M1Bars=%I64d Ticks=%I64d Reason=%d",
      g_had_error ? "false" : "true",
      g_m1_rows,
      g_tick_rows,
      reason
   );
}
