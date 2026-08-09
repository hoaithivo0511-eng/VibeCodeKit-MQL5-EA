//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  arbitrage-stat / python-bridge                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Statistical arbitrage with cointegration signal from Python bridge.
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"

input long   InpMagic        = 80600;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) {}

void OnTick(void)
  {
   // Pair Z-score arbitrage.
   /* signal logic */
  }
