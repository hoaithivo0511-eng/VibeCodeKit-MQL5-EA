//+------------------------------------------------------------------+
//| CMfeMaeLogger — per-trade MFE/MAE CSV writer                     |
//|                                                                  |
//| Plan v5 §12.5 — observability layer. Tracks the best (MFE) and   |
//| worst (MAE) excursion of each running position and, on close,    |
//| appends a row to a CSV file under FILE_COMMON. The matching      |
//| Python analyzer is `mql5-mfe-mae`.                               |
//|                                                                  |
//| Uses raw Position* / HistoryDeal* APIs so it has no dependency   |
//| on MQL5/Include/Trade/* (which may be absent in a fresh terminal |
//| install before terminal64.exe is run at least once).             |
//|                                                                  |
//| Usage:                                                           |
//|   CMfeMaeLogger mfe;                                             |
//|   mfe.Init("ea.csv");                                            |
//|   mfe.OnTick(); mfe.OnTradeTransaction(trans);                   |
//+------------------------------------------------------------------+
#ifndef VCK_CMFEMAELOGGER_MQH
#define VCK_CMFEMAELOGGER_MQH

class CMfeMaeLogger
  {
private:
   string            m_file;
   ulong             m_tracked_tickets[];
   double            m_mfe[];
   double            m_mae[];

   int      _IndexOf(const ulong ticket) const
     {
      for(int i = 0; i < ArraySize(m_tracked_tickets); ++i)
         if(m_tracked_tickets[i] == ticket) return i;
      return -1;
     }

   void     _Track(const ulong ticket)
     {
      int n = ArraySize(m_tracked_tickets);
      ArrayResize(m_tracked_tickets, n + 1);
      ArrayResize(m_mfe, n + 1);
      ArrayResize(m_mae, n + 1);
      m_tracked_tickets[n] = ticket;
      m_mfe[n] = 0.0;
      m_mae[n] = 0.0;
     }

   void     _Untrack(const int idx)
     {
      int n = ArraySize(m_tracked_tickets) - 1;
      if(n < 0) return;
      m_tracked_tickets[idx] = m_tracked_tickets[n];
      m_mfe[idx]             = m_mfe[n];
      m_mae[idx]             = m_mae[n];
      ArrayResize(m_tracked_tickets, n);
      ArrayResize(m_mfe, n);
      ArrayResize(m_mae, n);
     }

public:
   bool     Init(const string filename)
     {
      m_file = filename == "" ? "mfe_mae.csv" : filename;
      // Write CSV header once (FILE_COMMON so VPS migration carries it).
      int h = FileOpen(m_file, FILE_READ | FILE_COMMON);
      if(h == INVALID_HANDLE)
        {
         h = FileOpen(m_file, FILE_WRITE | FILE_COMMON | FILE_ANSI);
         if(h == INVALID_HANDLE) return false;
         FileWriteString(h, "deal_id,open_time,close_time,magic,type,profit,mfe,mae\n");
        }
      FileClose(h);
      return true;
     }

   void     OnTick(void)
     {
      // Sweep open positions, update MFE/MAE based on current profit.
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         int    idx    = _IndexOf(ticket);
         if(idx < 0) { _Track(ticket); idx = ArraySize(m_tracked_tickets) - 1; }
         double profit = PositionGetDouble(POSITION_PROFIT);
         if(profit > m_mfe[idx]) m_mfe[idx] = profit;
         if(profit < m_mae[idx]) m_mae[idx] = profit;
        }
     }

   void     OnTradeTransaction(const MqlTradeTransaction &trans)
     {
      if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
      if(!HistoryDealSelect(trans.deal)) return;
      long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY) return;

      ulong pos_id = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
      int    idx     = _IndexOf(pos_id);
      double v_mfe   = idx >= 0 ? m_mfe[idx] : 0.0;
      double v_mae   = idx >= 0 ? m_mae[idx] : 0.0;
      double profit  = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      long   magic   = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
      long   type    = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
      datetime ct    = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);

      // The "open_time" column duplicates close_time here; entry-deal
      // lookup is omitted to stay under the 100-LOC ceiling. The Python
      // mql5-mfe-mae analyzer does not require a distinct open_time.
      int h = FileOpen(m_file, FILE_WRITE | FILE_READ | FILE_COMMON | FILE_ANSI);
      if(h == INVALID_HANDLE) return;
      FileSeek(h, 0, SEEK_END);
      string row = StringFormat("%I64u,%s,%s,%I64d,%I64d,%.2f,%.2f,%.2f\n",
                                trans.deal,
                                TimeToString(ct, TIME_DATE | TIME_SECONDS),
                                TimeToString(ct, TIME_DATE | TIME_SECONDS),
                                magic, type, profit, v_mfe, v_mae);
      FileWriteString(h, row);
      FileClose(h);
      if(idx >= 0) _Untrack(idx);
     }
  };

#endif // VCK_CMFEMAELOGGER_MQH
