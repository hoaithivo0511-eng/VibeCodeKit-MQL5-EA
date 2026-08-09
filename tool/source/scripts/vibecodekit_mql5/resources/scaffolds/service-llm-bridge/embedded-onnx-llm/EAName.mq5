//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  service-llm-bridge / embedded-onnx-llm                 |
//| Symbol:    {{SYMBOL}}                                              |
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| Phi-3-mini (or any small ONNX classifier) embedded as MQL5        |
//| resource. No network. Fallback is a fixed-rule baseline.          |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

#resource "phi3_mini.onnx"

#include "CPipNormalizer.mqh"
#include "CRiskGuard.mqh"
#include "CMagicRegistry.mqh"
#include "CHistorySync.mqh"
#include "COnnxLoader.mqh"
#include "LlmEmbeddedOnnxLlmBridge.mqh"

input long   InpMagic        = 81400;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;

CPipNormalizer            pip;
CRiskGuard                risk;
CMagicRegistry            registry;
CHistorySync              history;
COnnxLoader               onnx;
LlmEmbeddedOnnxLlmBridge  llm;

int OnInit(void)
  {
   if(!pip.Init(_Symbol)) return INIT_FAILED;
   if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;
   risk.Init(InpDailyLossPct, InpMaxPositions, 0.10);
   if(!onnx.InitFromResource("phi3_mini.onnx"))
      Print("[LlmOnnx] resource load failed; will use rule fallback");
   if(!llm.Init(GetPointer(onnx), _Symbol, _Period)) return INIT_FAILED;
   if(!registry.Check(InpMagic))
      registry.Reserve(InpMagic, "{{NAME}}");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { llm.Release(); onnx.Release(); }

void OnTick(void)
  {
   // The embedded model runs in <1ms so it is safe in OnTick().
   string action = llm.SuggestOrFallback(_Symbol);
   // route action -> trader (omitted)
  }
