//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  scalping / hedging                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| M1 scalper: tight spread guard + ATR momentum filter +             |
//| CPipNormalizer risk-money lot sizing. The signal logic ships       |
//| ready-to-run; replace IsBuySignal() / IsSellSignal() with your     |
//| edge once the infrastructure is validated on demo.                |
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

input long   InpMagic        = 80700;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

sinput int InpMaxSpreadPoints = 20;
sinput int InpAtrPeriod       = 14;
sinput int InpAtrMinPoints    = 30;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;
CSafeTradeManager trade;
CHistorySync     history;

int h_atr = INVALID_HANDLE;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   trade.Init((ulong)InpMagic);
   h_atr = iATR(_Symbol, _Period, InpAtrPeriod);
   if(h_atr == INVALID_HANDLE) return INIT_FAILED;
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(h_atr != INVALID_HANDLE) IndicatorRelease(h_atr);
  }

// Starter signal: long when last bar closed above its open and ATR
// confirms range; short on the reverse. Replace with your edge.
bool IsBuySignal(double open1, double close1)  { return close1 > open1; }
bool IsSellSignal(double open1, double close1) { return close1 < open1; }

void OnTick(void)
  {
   risk.OnTick();

   static int last_bar = 0;
   int bars = Bars(_Symbol, _Period);
   if(bars == last_bar) return;
   last_bar = bars;

   long spread_points = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread_points > InpMaxSpreadPoints) return;
   if(!risk.CanOpenNewPosition()) return;

   double atr[1];
   if(CopyBuffer(h_atr, 0, 0, 1, atr) != 1) return;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0.0) return;
   if(atr[0] / point < (double)InpAtrMinPoints) return;

   double open1  = iOpen (_Symbol, _Period, 1);
   double close1 = iClose(_Symbol, _Period, 1);

   double lots = pip.LotForRisk(InpRiskMoney, InpSlPips);
   if(lots <= 0.0) return;

   double sl_dist = pip.Pips(InpSlPips);
   double tp_dist = pip.Pips(InpTpPips);
   double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(IsBuySignal(open1, close1))
     {
      double sl = ask - sl_dist;
      double tp = ask + tp_dist;
      trade.Buy(lots, _Symbol, sl, tp);
     }
   else if(IsSellSignal(open1, close1))
     {
      double sl = bid + sl_dist;
      double tp = bid - tp_dist;
      trade.Sell(lots, _Symbol, sl, tp);
     }
  }
