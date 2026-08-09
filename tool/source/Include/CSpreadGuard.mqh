//+------------------------------------------------------------------+
//| CSpreadGuard — block OrderSend when spread exceeds threshold.    |
//|                                                                  |
//| Plan v5 §8 Trader-17 #4 (spread_guarded). Threshold expressed in |
//| pips via the kit's `CPipNormalizer` so it's cross-broker stable. |
//|                                                                  |
//| Usage:                                                           |
//|   CSpreadGuard sg;                                               |
//|   sg.Init(pip, 3.0);   // 3.0 pips max                           |
//|   if(!sg.IsTradable()) return;                                   |
//+------------------------------------------------------------------+
#ifndef VCK_CSPREADGUARD_MQH
#define VCK_CSPREADGUARD_MQH

#include "CPipNormalizer.mqh"
#include "CMemorySafety.mqh"

class CSpreadGuard
  {
private:
   CPipNormalizer  *m_pip;
   double           m_max_pips;
   long             m_blocked_count;
public:
                     CSpreadGuard(void) : m_pip(NULL), m_max_pips(0.0), m_blocked_count(0) {}

   bool     Init(CPipNormalizer &pipref, const double max_pips)
     {
      m_pip          = &pipref;
      m_max_pips     = max_pips > 0 ? max_pips : 0.0;
      m_blocked_count = 0;
      return m_pip != NULL && m_max_pips > 0;
     }

   double   CurrentSpreadPips(void) const
     {
      if(m_pip == NULL || !POINTER_IS_VALID(m_pip)) return 0.0;
      MqlTick t;
      if(!SymbolInfoTick(m_pip.Symbol(), t)) return 0.0;
      double spread_price = t.ask - t.bid;
      return m_pip.PriceToPips(spread_price);
     }

   bool     IsTradable(void)
     {
      if(m_pip == NULL || !POINTER_IS_VALID(m_pip) || m_max_pips <= 0) return true;
      double cur = CurrentSpreadPips();
      if(cur > m_max_pips)
        {
         m_blocked_count++;
         return false;
        }
      return true;
     }

   long     BlockedCount(void) const { return m_blocked_count; }
  };

#endif // VCK_CSPREADGUARD_MQH
