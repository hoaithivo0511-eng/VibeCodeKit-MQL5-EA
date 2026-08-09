//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  mean-reversion / hedging                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Mean-reversion EA: RSI band fade with CPipNormalizer risk-money    |
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

input long   InpMagic        = 80200;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

sinput int    InpRsiPeriod     = 14;
sinput double InpRsiOversold   = 30.0;
sinput double InpRsiOverbought = 70.0;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;
CSafeTradeManager trade;
CHistorySync     history;

int h_rsi = INVALID_HANDLE;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   trade.Init((ulong)InpMagic);
   h_rsi = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);
   if(h_rsi == INVALID_HANDLE) return INIT_FAILED;
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(h_rsi != INVALID_HANDLE) IndicatorRelease(h_rsi);
  }

// Starter signal: RSI bands. Long when RSI dips below oversold, short
// when it pops above overbought. Replace with your edge.
bool IsBuySignal(const double &rsi[])  { return rsi[0] < InpRsiOversold; }
bool IsSellSignal(const double &rsi[]) { return rsi[0] > InpRsiOverbought; }

void OnTick(void)
  {
   risk.OnTick();

   static int last_bar = 0;
   int bars = Bars(_Symbol, _Period);
   if(bars == last_bar) return;
   last_bar = bars;

   if(!risk.CanOpenNewPosition()) return;

   double rsi[1];
   if(CopyBuffer(h_rsi, 0, 0, 1, rsi) != 1) return;

   double lots = pip.LotForRisk(InpRiskMoney, InpSlPips);
   if(lots <= 0.0) return;

   double sl_dist = pip.Pips(InpSlPips);
   double tp_dist = pip.Pips(InpTpPips);
   double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(IsBuySignal(rsi))
     {
      double sl = ask - sl_dist;
      double tp = ask + tp_dist;
      trade.Buy(lots, _Symbol, sl, tp);
     }
   else if(IsSellSignal(rsi))
     {
      double sl = bid + sl_dist;
      double tp = bid - tp_dist;
      trade.Sell(lots, _Symbol, sl, tp);
     }
  }
