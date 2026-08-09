//+------------------------------------------------------------------+
//| CAsyncTradeManager.mqh — OrderSendAsync helper + transaction lock|
//|                                                                   |
//| v2.0: full async trade lifecycle (open + close), auto filling     |
//|       mode, stale timeout, partial-fill tracking, retry on reject,|
//|       O(1) swap-with-last removal.                                |
//|                                                                   |
//| Wraps OrderSendAsync() with proper request_id tracking + an      |
//| OnTradeTransaction()-side reconciliation step. Designed for      |
//| HFT EAs that need sub-millisecond submission latency.            |
//|                                                                   |
//| AP-18 (async-no-handler) requires every async submitter to be    |
//| paired with OnTradeTransaction() — see the matching scaffold     |
//| template for the wired callback.                                  |
//+------------------------------------------------------------------+
#ifndef __CAsyncTradeManager_MQH__
#define __CAsyncTradeManager_MQH__

#include "CPipNormalizer.mqh"
// Note: no <Trade\Trade.mqh> required. We call OrderSendAsync() directly
// with the built-in MqlTradeRequest / MqlTradeResult structs and never
// touch the stdlib CTrade class. Keeping this file stdlib-free means the
// hft-async scaffold compiles on a fresh MetaEditor install (e.g. the
// Wine MetaEditor that ships with the kit's Phase 0 setup) without the
// MQL5/Include/ tree being bootstrapped first.

//+------------------------------------------------------------------+
//| Pending request tracking struct                                   |
//+------------------------------------------------------------------+
struct AsyncPending
  {
   ulong             request_id;
   string            symbol;
   ENUM_ORDER_TYPE   type;
   double            volume;
   double            volume_filled;
   ulong             timestamp_us;
   int               retry_count;
   bool              is_close;
   ulong             close_ticket;
  };

//+------------------------------------------------------------------+
//| Async trade stats (read-only)                                     |
//+------------------------------------------------------------------+
struct AsyncStats
  {
   int               total_sent;
   int               total_reconciled;
   int               total_rejected;
   int               total_partial;
   int               total_stale;
   int               total_retried;
   ulong             avg_latency_us;
   ulong             max_latency_us;
  };

class CAsyncTradeManager
  {
private:
   ulong             m_magic;
   AsyncPending      m_pending[];
   int               m_max_retries;
   ulong             m_stale_timeout_us;
   int               m_deviation;

   // Stats
   int               m_total_sent;
   int               m_total_reconciled;
   int               m_total_rejected;
   int               m_total_partial;
   int               m_total_stale;
   int               m_total_retried;
   ulong             m_sum_latency_us;
   ulong             m_max_latency_us;

   //--- Detect best filling mode for symbol
   ENUM_ORDER_TYPE_FILLING _detectFilling(const string symbol) const
     {
      long modes = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
      if((modes & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
      if((modes & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
      return ORDER_FILLING_RETURN;
     }

   //--- Core send with full request setup
   bool              _send(const ENUM_TRADE_REQUEST_ACTIONS action,
                           const ENUM_ORDER_TYPE type, const string symbol,
                           const double lots, const double price,
                           const double sl, const double tp,
                           const bool isClose, const ulong closeTicket)
     {
      MqlTradeRequest req={};
      MqlTradeResult  res={};
      req.action       = action;
      req.symbol       = symbol;
      req.volume       = lots;
      req.type         = type;
      req.price        = price;
      req.sl           = sl;
      req.tp           = tp;
      req.magic        = m_magic;
      req.deviation    = m_deviation;
      req.type_filling = _detectFilling(symbol);
      if(isClose)
         req.position  = closeTicket;
      if(!OrderSendAsync(req, res))
        {
         Print("[AsyncTM] OrderSendAsync err=", GetLastError(),
               " action=", EnumToString(action));
         return false;
        }
      AsyncPending p;
      p.request_id    = res.request_id;
      p.symbol        = symbol;
      p.type          = type;
      p.volume        = lots;
      p.volume_filled = 0.0;
      p.timestamp_us  = GetMicrosecondCount();
      p.retry_count   = 0;
      p.is_close      = isClose;
      p.close_ticket  = closeTicket;
      const int sz = ArraySize(m_pending);
      ArrayResize(m_pending, sz + 1);
      m_pending[sz] = p;
      m_total_sent++;
      return true;
     }

   //--- O(1) removal: swap with last element
   void              _removePending(int idx)
     {
      const int last = ArraySize(m_pending) - 1;
      if(idx < last)
         m_pending[idx] = m_pending[last];
      ArrayResize(m_pending, last);
     }

   //--- Retry a rejected request
   bool              _retry(const AsyncPending &p)
     {
      if(p.retry_count >= m_max_retries)
        {
         Print("[AsyncTM] max retries reached for req=", p.request_id);
         m_total_rejected++;
         return false;
        }
      double price;
      if(p.type == ORDER_TYPE_BUY)
         price = SymbolInfoDouble(p.symbol, SYMBOL_ASK);
      else
         price = SymbolInfoDouble(p.symbol, SYMBOL_BID);

      MqlTradeRequest req={};
      MqlTradeResult  res={};
      req.action       = TRADE_ACTION_DEAL;
      req.symbol       = p.symbol;
      req.volume       = p.volume - p.volume_filled;
      req.type         = p.type;
      req.price        = price;
      req.magic        = m_magic;
      req.deviation    = m_deviation;
      req.type_filling = _detectFilling(p.symbol);
      if(p.is_close)
         req.position  = p.close_ticket;
      if(!OrderSendAsync(req, res))
        {
         Print("[AsyncTM] retry OrderSendAsync err=", GetLastError());
         m_total_rejected++;
         return false;
        }
      // Append new entry (old was already removed by caller)
      AsyncPending updated = p;
      updated.request_id   = res.request_id;
      updated.timestamp_us = GetMicrosecondCount();
      updated.retry_count  = p.retry_count + 1;
      const int sz = ArraySize(m_pending);
      ArrayResize(m_pending, sz + 1);
      m_pending[sz] = updated;
      m_total_retried++;
      Print("[AsyncTM] retrying req=", p.request_id, " → new req=", res.request_id,
            " attempt=", updated.retry_count);
      return true;
     }

public:
                     CAsyncTradeManager(void) : m_magic(0), m_max_retries(2),
                        m_stale_timeout_us(5000000), m_deviation(10),
                        m_total_sent(0), m_total_reconciled(0),
                        m_total_rejected(0), m_total_partial(0),
                        m_total_stale(0), m_total_retried(0),
                        m_sum_latency_us(0), m_max_latency_us(0)
     {
      ArrayResize(m_pending, 0);
     }

   //--- Init with magic; optional config
   void              Init(const ulong magic,
                          const int maxRetries = 2,
                          const ulong staleTimeoutUs = 5000000,
                          const int deviation = 10)
     {
      m_magic            = magic;
      m_max_retries      = maxRetries;
      m_stale_timeout_us = staleTimeoutUs;
      m_deviation        = deviation;
     }

   //+----------------------------------------------------------------+
   //| ENTRY: async open positions                                     |
   //+----------------------------------------------------------------+
   bool              SendBuyAsync(const string symbol, const double lots,
                                  const double sl, const double tp)
     {
      const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      return _send(TRADE_ACTION_DEAL, ORDER_TYPE_BUY, symbol, lots, ask, sl, tp,
                   false, 0);
     }

   bool              SendSellAsync(const string symbol, const double lots,
                                   const double sl, const double tp)
     {
      const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      return _send(TRADE_ACTION_DEAL, ORDER_TYPE_SELL, symbol, lots, bid, sl, tp,
                   false, 0);
     }

   //+----------------------------------------------------------------+
   //| EXIT: async close positions                                     |
   //+----------------------------------------------------------------+
   bool              SendCloseAsync(const ulong ticket)
     {
      if(!PositionSelectByTicket(ticket))
        {
         Print("[AsyncTM] SendCloseAsync: ticket ", ticket, " not found");
         return false;
        }
      string symbol  = PositionGetString(POSITION_SYMBOL);
      double lots    = PositionGetDouble(POSITION_VOLUME);
      long   posType = PositionGetInteger(POSITION_TYPE);
      ENUM_ORDER_TYPE closeType = (posType == POSITION_TYPE_BUY)
                                  ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      double price   = (closeType == ORDER_TYPE_SELL)
                       ? SymbolInfoDouble(symbol, SYMBOL_BID)
                       : SymbolInfoDouble(symbol, SYMBOL_ASK);
      return _send(TRADE_ACTION_DEAL, closeType, symbol, lots, price, 0, 0,
                   true, ticket);
     }

   //--- Close all positions matching magic + symbol (async batch)
   int               CloseAllAsync(const string symbol = "")
     {
      int sent = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetInteger(POSITION_MAGIC) != (long)m_magic)
            continue;
         if(symbol != "" && PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if(SendCloseAsync(ticket))
            sent++;
        }
      if(sent > 0)
         Print("[AsyncTM] CloseAllAsync sent ", sent, " close requests",
               symbol != "" ? " for " + symbol : "");
      return sent;
     }

   //+----------------------------------------------------------------+
   //| RECONCILIATION: called from OnTradeTransaction()                |
   //+----------------------------------------------------------------+
   void              OnTransactionResult(const MqlTradeTransaction &trans,
                                         const MqlTradeRequest &request,
                                         const MqlTradeResult &result)
     {
      const int sz = ArraySize(m_pending);
      for(int i = 0; i < sz; i++)
        {
         if(m_pending[i].request_id != result.request_id)
            continue;

         uint retcode = (trans.deal == 0) ? result.retcode : 10009;

         // Reject → retry if allowed
         if(retcode == 10004 || retcode == 10006 || retcode == 10007 ||
            retcode == 10021)
           {
            Print("[AsyncTM] rejected req=", result.request_id,
                  " retcode=", retcode, " — attempting retry");
            AsyncPending copy = m_pending[i];
            _removePending(i);
            _retry(copy);
            return;
           }

         // Partial fill check
         double filled = result.volume;
         double remaining = m_pending[i].volume - m_pending[i].volume_filled;
         if(filled > 0 && filled < remaining)
           {
            m_total_partial++;
            Print("[AsyncTM] partial fill req=", result.request_id,
                  " filled=", filled, "/", remaining);
            m_pending[i].volume_filled += filled;
            // Retry remaining volume
            AsyncPending copy = m_pending[i];
            _removePending(i);
            _retry(copy);
            return;
           }

         // Full fill — record latency only for completed orders
         const ulong dt = GetMicrosecondCount() - m_pending[i].timestamp_us;
         m_sum_latency_us += dt;
         if(dt > m_max_latency_us)
            m_max_latency_us = dt;
         m_total_reconciled++;
         Print("[AsyncTM] reconciled req=", result.request_id,
               " retcode=", retcode,
               m_pending[i].is_close ? " CLOSE" : " OPEN",
               " latency_us=", dt);
         _removePending(i);
         return;
        }
     }

   //+----------------------------------------------------------------+
   //| STALE CLEANUP: call periodically (e.g. from OnTick)             |
   //+----------------------------------------------------------------+
   int               CleanupStale(void)
     {
      int cleaned = 0;
      ulong now = GetMicrosecondCount();
      for(int i = ArraySize(m_pending) - 1; i >= 0; i--)
        {
         if(now - m_pending[i].timestamp_us > m_stale_timeout_us)
           {
            Print("[AsyncTM] stale req=", m_pending[i].request_id,
                  " age_us=", now - m_pending[i].timestamp_us, " — removing");
            _removePending(i);
            m_total_stale++;
            cleaned++;
           }
        }
      return cleaned;
     }

   //+----------------------------------------------------------------+
   //| ACCESSORS                                                       |
   //+----------------------------------------------------------------+
   int               PendingCount(void) const { return ArraySize(m_pending); }

   AsyncStats        GetStats(void) const
     {
      AsyncStats s;
      s.total_sent       = m_total_sent;
      s.total_reconciled = m_total_reconciled;
      s.total_rejected   = m_total_rejected;
      s.total_partial    = m_total_partial;
      s.total_stale      = m_total_stale;
      s.total_retried    = m_total_retried;
      s.avg_latency_us   = m_total_reconciled > 0
                           ? m_sum_latency_us / (ulong)m_total_reconciled : 0;
      s.max_latency_us   = m_max_latency_us;
      return s;
     }

   void              PrintStats(void) const
     {
      AsyncStats s = GetStats();
      Print("[AsyncTM] Stats: sent=", s.total_sent,
            " reconciled=", s.total_reconciled,
            " rejected=", s.total_rejected,
            " partial=", s.total_partial,
            " stale=", s.total_stale,
            " retried=", s.total_retried,
            " avg_lat=", s.avg_latency_us, "us",
            " max_lat=", s.max_latency_us, "us");
     }
  };

#endif // __CAsyncTradeManager_MQH__
