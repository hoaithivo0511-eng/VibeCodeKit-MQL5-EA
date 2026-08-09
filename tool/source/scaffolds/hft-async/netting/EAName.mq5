//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  hft-async / netting                                     |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| OrderSendAsync HFT shell with paired OnTradeTransaction reconciler|
//| (AP-18 compliant — async without handler is a critical error).    |
//|                                                                   |
//| v2: async open + close, stale cleanup, retry on reject, stats.   |
//|                                                                   |
//| Starter signal: tick-rate gate + tick-by-tick momentum filter.    |
//| Replace IsBuySignal() / IsSellSignal() with your edge once the     |
//| infrastructure is validated on demo.                              |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "2.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"
#include "CAsyncTradeManager.mqh"

input long   InpMagic        = 80050;
input double InpRiskMoney    = 50.0;
input int    InpSlPips       = 10;
input int    InpTpPips       = 15;
input double InpDailyLossPct = 0.02;
input int    InpMaxPositions = 5;

sinput int InpMinTicksPerSec   = 5;     // minimum tick rate to consider the book "hot"
sinput int InpMaxPendingAsync  = 3;     // backpressure on un-reconciled requests
sinput int InpMaxRetries       = 2;     // retry attempts on requote/reject
sinput int InpStaleTimeoutSec  = 5;     // stale pending cleanup threshold

CPipNormalizer    pip;
CRiskGuard        risk;
CMagicRegistry    registry;
CAsyncTradeManager async_tm;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   async_tm.Init((ulong)InpMagic, InpMaxRetries,
                 (ulong)InpStaleTimeoutSec * 1000000);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   Print("{{NAME}} HFT v2 initialized; magic=", InpMagic);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   async_tm.PrintStats();
  }

// Starter signal: same-tick momentum. Long if last tick lifted ask; short
// if it pushed bid lower. Replace with your edge.
bool IsBuySignal(double prev_ask, double ask)  { return ask > prev_ask; }
bool IsSellSignal(double prev_bid, double bid) { return bid < prev_bid; }

void OnTick(void)
  {
   risk.OnTick();
   async_tm.CleanupStale();

   if(!risk.CanOpenNewPosition()) return;
   if(async_tm.PendingCount() >= InpMaxPendingAsync) return;  // backpressure

   // Tick-rate gate — only act when the book is hot enough.
   static ulong  last_tick_ms = 0;
   static int    tick_count   = 0;
   static int    ticks_per_sec = 0;
   ulong now_ms = GetTickCount();
   if(last_tick_ms == 0 || now_ms - last_tick_ms >= 1000)
     {
      ticks_per_sec = tick_count;
      tick_count    = 0;
      last_tick_ms  = now_ms;
     }
   tick_count++;
   if(ticks_per_sec < InpMinTicksPerSec) return;

   static double prev_ask = 0.0;
   static double prev_bid = 0.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(prev_ask == 0.0 || prev_bid == 0.0) { prev_ask = ask; prev_bid = bid; return; }

   double lots = pip.LotForRisk(InpRiskMoney, InpSlPips);
   if(lots <= 0.0) { prev_ask = ask; prev_bid = bid; return; }

   double sl_dist = pip.Pips(InpSlPips);
   double tp_dist = pip.Pips(InpTpPips);

   if(IsBuySignal(prev_ask, ask))
     {
      double sl = ask - sl_dist;
      double tp = ask + tp_dist;
      async_tm.SendBuyAsync(_Symbol, lots, sl, tp);
     }
   else if(IsSellSignal(prev_bid, bid))
     {
      double sl = bid + sl_dist;
      double tp = bid - tp_dist;
      async_tm.SendSellAsync(_Symbol, lots, sl, tp);
     }

   prev_ask = ask;
   prev_bid = bid;
  }

//+------------------------------------------------------------------+
//| OnTradeTransaction — AP-18 mandatory pair for OrderSendAsync     |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest    &request,
                        const MqlTradeResult     &result)
  {
   async_tm.OnTransactionResult(trans, request, result);
  }
