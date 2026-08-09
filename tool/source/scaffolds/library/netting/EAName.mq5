//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  library / netting                                       |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Reusable library scaffold (Include-only). EA shell delegates to includes.
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"

input long   InpMagic        = 80800;
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
   // All logic lives in shared library .mqh files.
  }
