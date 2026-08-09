//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  service-llm-bridge / self-hosted-ollama                |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| WebRequest -> http://localhost:11434 (Ollama API).                |
//| 5s timeout + rule-based fallback (Trader-17 #14, #16).            |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"
#include "CHistorySync.mqh"
#include "LlmSelfHostedOllamaBridge.mqh"

input long   InpMagic        = 81300;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;
// sinput = static input: deployment knobs, not optimization targets.
// Keeps AP-5 (≤6 optimizable inputs) satisfied.
sinput string InpModel        = "llama3.2";
sinput int    InpLlmTimeoutMs = 5000;

CPipNormalizer              pip;
CRiskGuard                  risk;
CMagicRegistry              registry;
CHistorySync                history;
LlmSelfHostedOllamaBridge   llm;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!llm.Init(_Symbol, _Period, InpLlmTimeoutMs)) return INIT_FAILED;
   llm.SetModel(InpModel);
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   EventSetTimer(30);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { EventKillTimer(); llm.Release(); }

void OnTimer(void)
  {
   string action = llm.SuggestOrFallback(_Symbol);
   // route action -> trader (omitted for brevity)
  }

void OnTick(void) { /* execution path only */ }
