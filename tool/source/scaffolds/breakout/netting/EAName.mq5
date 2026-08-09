//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  breakout / netting                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Breakout EA: Donchian highest/lowest with CPipNormalizer risk-money|
//| lot sizing and same-bar guard. The signal logic ships ready-to-run;|
//| replace IsBuySignal() / IsSellSignal() with your edge once the     |
//| infrastructure is validated on demo.                              |
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

input long   InpMagic        = 80300;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

sinput int InpLookbackBars = 20;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;
CSafeTradeManager trade;
CHistorySync     history;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   trade.Init((ulong)InpMagic);
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) {}

// Starter signal: Donchian breakout. Long if last close > highest of the
// prior N closed bars; short if < lowest. Replace with your edge.
bool IsBuySignal(double close, double hh)  { return close > hh; }
bool IsSellSignal(double close, double ll) { return close < ll; }

void OnTick(void)
  {
   risk.OnTick();

   static int last_bar = 0;
   int bars = Bars(_Symbol, _Period);
   if(bars == last_bar) return;
   last_bar = bars;

   if(!risk.CanOpenNewPosition()) return;

   int hh_idx = iHighest(_Symbol, _Period, MODE_HIGH, InpLookbackBars, 1);
   int ll_idx = iLowest (_Symbol, _Period, MODE_LOW,  InpLookbackBars, 1);
   if(hh_idx < 0 || ll_idx < 0) return;

   double hh    = iHigh (_Symbol, _Period, hh_idx);
   double ll    = iLow  (_Symbol, _Period, ll_idx);
   double close = iClose(_Symbol, _Period, 1);
   if(hh <= 0.0 || ll <= 0.0 || close <= 0.0) return;

   double lots = pip.LotForRisk(InpRiskMoney, InpSlPips);
   if(lots <= 0.0) return;

   double sl_dist = pip.Pips(InpSlPips);
   double tp_dist = pip.Pips(InpTpPips);
   double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(IsBuySignal(close, hh))
     {
      double sl = ask - sl_dist;
      double tp = ask + tp_dist;
      trade.Buy(lots, _Symbol, sl, tp);
     }
   else if(IsSellSignal(close, ll))
     {
      double sl = bid + sl_dist;
      double tp = bid - tp_dist;
      trade.Sell(lots, _Symbol, sl, tp);
     }
  }
