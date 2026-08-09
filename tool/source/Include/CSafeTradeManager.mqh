//+------------------------------------------------------------------+
//| CSafeTradeManager — checked CTrade wrapper with bounded retry     |
//|                                                                  |
//| Synchronous trade helper for non-HFT EAs. It checks CTrade's      |
//| boolean return plus ResultRetcode(), retries transient broker     |
//| errors with fresh Bid/Ask, and exposes the last diagnostic string.|
//+------------------------------------------------------------------+
#ifndef VCK_CSAFETRADEMANAGER_MQH
#define VCK_CSAFETRADEMANAGER_MQH

#include <Trade/Trade.mqh>

class CSafeTradeManager
  {
private:
   CTrade            m_trade;
   ulong             m_magic;
   int               m_max_retries;
   int               m_retry_delay_ms;
   int               m_deviation_points;
   uint              m_last_retcode;
   int               m_last_error;
   string            m_last_reason;

   ENUM_ORDER_TYPE_FILLING _DetectFilling(const string symbol) const
     {
      long modes = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
      if((modes & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
      if((modes & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
      return ORDER_FILLING_RETURN;
     }

   bool              _IsSuccessRetcode(const uint retcode) const
     {
      return retcode == TRADE_RETCODE_DONE ||
             retcode == TRADE_RETCODE_PLACED ||
             retcode == TRADE_RETCODE_DONE_PARTIAL;
     }

   bool              _IsRetryableRetcode(const uint retcode) const
     {
      return retcode == TRADE_RETCODE_REQUOTE ||
             retcode == TRADE_RETCODE_REJECT ||
             retcode == TRADE_RETCODE_PRICE_OFF ||
             retcode == TRADE_RETCODE_TIMEOUT;
     }

   void              _Remember(const uint retcode, const int err,
                               const string action, const int attempt)
     {
      m_last_retcode = retcode;
      m_last_error   = err;
      m_last_reason  = StringFormat("%s attempt=%d retcode=%u error=%d",
                                    action, attempt, retcode, err);
     }

   bool              _ValidateStops(const bool is_buy, const string symbol,
                                    const double sl, const double tp)
     {
      long stops_points = (long)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      if(stops_points <= 0)
         return true;                       // broker imposes no minimum distance
      int    digits   = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);
      double min_dist = stops_points * point;
      double ref      = is_buy ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                               : SymbolInfoDouble(symbol, SYMBOL_BID);
      const string side = is_buy ? "BUY" : "SELL";
      if(sl > 0.0)
        {
         double dist = is_buy ? (ref - sl) : (sl - ref);
         if(dist < min_dist)
           {
            m_last_reason = side + " rejected: SL too close ("
                            + DoubleToString(dist, digits) + " < stops_level "
                            + DoubleToString(min_dist, digits) + ")";
            return false;
           }
        }
      if(tp > 0.0)
        {
         double dist = is_buy ? (tp - ref) : (ref - tp);
         if(dist < min_dist)
           {
            m_last_reason = side + " rejected: TP too close ("
                            + DoubleToString(dist, digits) + " < stops_level "
                            + DoubleToString(min_dist, digits) + ")";
            return false;
           }
        }
      return true;
     }

   bool              _Send(const bool is_buy, const double lots,
                           const string symbol, const double sl,
                           const double tp, const string comment)
     {
      const string action = is_buy ? "BUY" : "SELL";
      string trade_symbol = symbol == "" ? _Symbol : symbol;
      // Pre-trade guards: a non-positive volume or a SL/TP inside the broker's
      // minimum stop distance is rejected up-front instead of burning retries
      // on a guaranteed-invalid OrderSend.
      if(lots <= 0.0)
        {
         m_last_retcode = 0;
         m_last_error   = 0;
         m_last_reason  = StringFormat("%s rejected: lots=%.2f must be > 0", action, lots);
         Print("[SafeTrade] ", m_last_reason);
         return false;
        }
      if(!_ValidateStops(is_buy, trade_symbol, sl, tp))
        {
         m_last_retcode = 0;
         m_last_error   = 0;
         Print("[SafeTrade] ", m_last_reason);
         return false;
        }
      m_trade.SetExpertMagicNumber(m_magic);
      m_trade.SetMarginMode();
      m_trade.SetDeviationInPoints(m_deviation_points);
      m_trade.SetTypeFilling(_DetectFilling(trade_symbol));

      for(int attempt = 1; attempt <= m_max_retries + 1; ++attempt)
        {
         ResetLastError();
         bool sent = false;
         if(is_buy)
            sent = m_trade.Buy(lots, trade_symbol, 0.0, sl, tp, comment);
         else
            sent = m_trade.Sell(lots, trade_symbol, 0.0, sl, tp, comment);

         uint retcode = m_trade.ResultRetcode();
         int err = GetLastError();
         _Remember(retcode, err, action, attempt);

         if(sent && _IsSuccessRetcode(retcode))
            return true;

         Print("[SafeTrade] ", m_last_reason);
         if(!_IsRetryableRetcode(retcode) || attempt > m_max_retries)
            break;

         Sleep(m_retry_delay_ms);
        }

      return false;
     }

public:
                     CSafeTradeManager(void) : m_magic(0), m_max_retries(3),
                        m_retry_delay_ms(250), m_deviation_points(50),
                        m_last_retcode(0), m_last_error(0), m_last_reason("") {}

   void              Init(const ulong magic, const int maxRetries = 3,
                          const int retryDelayMs = 250,
                          const int deviationPoints = 50)
     {
      m_magic            = magic;
      m_max_retries      = maxRetries;
      m_retry_delay_ms   = retryDelayMs;
      m_deviation_points = deviationPoints;
      m_trade.SetExpertMagicNumber(m_magic);
      m_trade.SetMarginMode();
      m_trade.SetDeviationInPoints(m_deviation_points);
     }

   bool              Buy(const double lots, const string symbol,
                         const double sl, const double tp,
                         const string comment = "")
     {
      return _Send(true, lots, symbol, sl, tp, comment);
     }

   bool              Sell(const double lots, const string symbol,
                          const double sl, const double tp,
                          const string comment = "")
     {
      return _Send(false, lots, symbol, sl, tp, comment);
     }

   uint              LastRetcode(void) const { return m_last_retcode; }
   int               LastError(void)   const { return m_last_error; }
   string            LastReason(void)  const { return m_last_reason; }
  };

#endif // VCK_CSAFETRADEMANAGER_MQH
