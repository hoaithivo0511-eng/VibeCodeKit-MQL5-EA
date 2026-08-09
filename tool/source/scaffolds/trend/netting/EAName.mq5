//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  trend / netting                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Trend-following EA: fast/slow EMA cross with CPipNormalizer       |
//| risk-money lot sizing and same-bar guard. The signal logic ships  |
//| ready-to-run; replace IsBuySignal() / IsSellSignal() with your     |
//| own edge once you've validated the infrastructure on demo.        |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"
#include "CSafeTradeManager.mqh"
#include "CHistorySync.mqh"

input long   InpMagic        = 80100;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

// Strategy knobs use sinput so the Strategy Tester optimiser leaves them
// fixed unless the operator explicitly enables them; this also keeps the
// optimizable-input count at the AP-5 ceiling.
sinput int InpEmaFastPeriod = 50;
sinput int InpEmaSlowPeriod = 200;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;
CSafeTradeManager trade;
CHistorySync     history;

// MA handles — created once in OnInit (iMA returns a handle, not a value).
int h_fast = INVALID_HANDLE;
int h_slow = INVALID_HANDLE;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   trade.Init((ulong)InpMagic);
   h_fast = iMA(_Symbol, _Period, InpEmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
   h_slow = iMA(_Symbol, _Period, InpEmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(h_fast == INVALID_HANDLE || h_slow == INVALID_HANDLE) return INIT_FAILED;
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(h_fast != INVALID_HANDLE) IndicatorRelease(h_fast);
   if(h_slow != INVALID_HANDLE) IndicatorRelease(h_slow);
  }

// Starter signal: bullish/bearish EMA cross on the just-closed bar. Replace
// this function with your edge once the infrastructure is validated.
bool IsBuySignal(const double &fast[], const double &slow[])
  {
   return fast[1] > slow[1] && fast[0] <= slow[0];
  }

bool IsSellSignal(const double &fast[], const double &slow[])
  {
   return fast[1] < slow[1] && fast[0] >= slow[0];
  }

void OnTick(void)
  {
   risk.OnTick();

   static int last_bar = 0;
   int bars = Bars(_Symbol, _Period);
   if(bars == last_bar) return;
   last_bar = bars;

   if(!risk.CanOpenNewPosition()) return;

   double fast[2], slow[2];
   if(CopyBuffer(h_fast, 0, 0, 2, fast) != 2) return;
   if(CopyBuffer(h_slow, 0, 0, 2, slow) != 2) return;

   double lots = pip.LotForRisk(InpRiskMoney, InpSlPips);
   if(lots <= 0.0) return;

   double sl_dist = pip.Pips(InpSlPips);
   double tp_dist = pip.Pips(InpTpPips);
   double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(IsBuySignal(fast, slow))
     {
      double sl = ask - sl_dist;
      double tp = ask + tp_dist;
      trade.Buy(lots, _Symbol, sl, tp);
     }
   else if(IsSellSignal(fast, slow))
     {
      double sl = bid + sl_dist;
      double tp = bid - tp_dist;
      trade.Sell(lots, _Symbol, sl, tp);
     }
  }
