//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  portfolio-basket / netting                                        |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"

input long   InpMagic       = {{MAGIC}};
input double InpRiskMoney   = 100.0;
input int    InpSlPips      = 30;
input int    InpTpPips      = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

CPipNormalizer pip;
CRiskGuard     risk;
CMagicRegistry registry;

int OnInit(void)
  {
   if(!pip.Init(_Symbol))
      return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   Print("{{NAME}} initialized: symbol=", _Symbol, " pip=", pip.Pip());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) {}

void OnTick(void)
  {
   risk.OnTick();
   if(!risk.CanOpenNewPosition()) return;
   double sl = pip.Pips(InpSlPips);
   double lot = pip.LotForRisk(InpRiskMoney, InpSlPips);
   // Order placement intentionally omitted from scaffold — fill in per
   // strategy. The stdlib/netting variant assumes one net position
   // managed via CTrade in your strategy module.
   if(lot <= 0.0)
      Print("{{NAME}} skipped: lot=0 reason=", risk.LastBlockReason());
  }
