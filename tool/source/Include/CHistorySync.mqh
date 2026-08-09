//+------------------------------------------------------------------+
//| CHistorySync — symbol/timeframe history readiness guard           |
//|                                                                  |
//| Forces terminal timeseries construction and verifies              |
//| SERIES_SYNCHRONIZED before indicators or signal code read bars.   |
//+------------------------------------------------------------------+
#ifndef VCK_CHISTORYSYNC_MQH
#define VCK_CHISTORYSYNC_MQH

class CHistorySync
  {
private:
   int               m_max_attempts;
   int               m_delay_ms;
   string            m_last_reason;

   bool              _HasFirstDate(const string symbol,
                                   const ENUM_TIMEFRAMES timeframe,
                                   const datetime start_date)
     {
      datetime first_date = 0;
      if(!SeriesInfoInteger(symbol, timeframe, SERIES_FIRSTDATE, first_date))
         return false;
      return first_date > 0 && first_date <= start_date;
     }

   bool              _IsSynchronized(const string symbol,
                                     const ENUM_TIMEFRAMES timeframe)
     {
      long synchronized = 0;
      if(!SeriesInfoInteger(symbol, timeframe, SERIES_SYNCHRONIZED, synchronized))
         return false;
      return synchronized != 0;
     }

public:
                     CHistorySync(void) : m_max_attempts(15), m_delay_ms(500),
                                          m_last_reason("") {}

   void              Configure(const int maxAttempts, const int delayMs)
     {
      m_max_attempts = maxAttempts;
      m_delay_ms     = delayMs;
     }

   bool              Ensure(const string symbol,
                            const ENUM_TIMEFRAMES timeframe,
                            const datetime start_date)
     {
      string trade_symbol = symbol == "" ? _Symbol : symbol;
      if(!SymbolInfoInteger(trade_symbol, SYMBOL_SELECT))
         SymbolSelect(trade_symbol, true);

      datetime times[1];
      for(int attempt = 1; attempt <= m_max_attempts; ++attempt)
        {
         ResetLastError();
         CopyTime(trade_symbol, timeframe, start_date, 1, times);
         if(_HasFirstDate(trade_symbol, timeframe, start_date) &&
            _IsSynchronized(trade_symbol, timeframe))
           {
            m_last_reason = StringFormat("%s/%s synchronized after %d attempt(s)",
                                         trade_symbol, EnumToString(timeframe),
                                         attempt);
            return true;
           }
         Sleep(m_delay_ms);
        }

      m_last_reason = StringFormat("%s/%s history not synchronized, error=%d",
                                   trade_symbol, EnumToString(timeframe),
                                   GetLastError());
      return false;
     }

   bool              EnsureBars(const string symbol,
                                const ENUM_TIMEFRAMES timeframe,
                                const int bars_needed)
     {
      datetime start_date = TimeCurrent() - PeriodSeconds(timeframe) * bars_needed;
      return Ensure(symbol, timeframe, start_date);
     }

   string            LastReason(void) const { return m_last_reason; }
  };

#endif // VCK_CHISTORYSYNC_MQH
