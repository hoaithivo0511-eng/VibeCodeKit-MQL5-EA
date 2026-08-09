//+------------------------------------------------------------------+
//| LlmEmbeddedOnnxLlmBridge.mqh — local ONNX classifier wrapper      |
//|                                                                   |
//| Fallback path: in MQL5, iMA() returns an indicator handle (int). |
//| The actual MA value is read with CopyBuffer(). Handles are       |
//| created once in Init() and released in Release() (AP-12).        |
//+------------------------------------------------------------------+
#ifndef __LlmEmbeddedOnnxLlmBridge_MQH__
#define __LlmEmbeddedOnnxLlmBridge_MQH__

#include "COnnxLoader.mqh"
#include "CMemorySafety.mqh"

class LlmEmbeddedOnnxLlmBridge
  {
private:
   COnnxLoader      *m_onnx;
   int               m_h_fast;
   int               m_h_slow;

   string            _fallback(const string symbol)
     {
      if(m_h_fast == INVALID_HANDLE || m_h_slow == INVALID_HANDLE)
         return "FLAT";
      double buf_fast[1], buf_slow[1];
      if(CopyBuffer(m_h_fast, 0, 0, 1, buf_fast) != 1) return "FLAT";
      if(CopyBuffer(m_h_slow, 0, 0, 1, buf_slow) != 1) return "FLAT";
      if(buf_fast[0] > buf_slow[0]) return "BUY";
      if(buf_fast[0] < buf_slow[0]) return "SELL";
      return "FLAT";
     }

public:
                     LlmEmbeddedOnnxLlmBridge(void)
                       : m_onnx(NULL),
                         m_h_fast(INVALID_HANDLE),
                         m_h_slow(INVALID_HANDLE) {}

   bool              Init(COnnxLoader *onnx, const string symbol,
                          const ENUM_TIMEFRAMES tf)
     {
      m_onnx = onnx;
      m_h_fast = iMA(symbol, tf, 20, 0, MODE_EMA, PRICE_CLOSE);
      m_h_slow = iMA(symbol, tf, 50, 0, MODE_EMA, PRICE_CLOSE);
      return (m_h_fast != INVALID_HANDLE && m_h_slow != INVALID_HANDLE);
     }

   void              Release(void)
     {
      if(m_h_fast != INVALID_HANDLE) { IndicatorRelease(m_h_fast); m_h_fast = INVALID_HANDLE; }
      if(m_h_slow != INVALID_HANDLE) { IndicatorRelease(m_h_slow); m_h_slow = INVALID_HANDLE; }
     }

   string            SuggestOrFallback(const string symbol)
     {
      if(m_onnx == NULL || !POINTER_IS_VALID(m_onnx) || m_onnx.Handle() == INVALID_HANDLE)
         return _fallback(symbol);
      // NB: 'input' and 'output' are reserved MQL5 keywords (used for
      // declaring optimizer-visible input parameters). Use 'feat' /
      // 'logits' as the local-buffer names instead.
      float feat[10]; float logits[3];
      // toy feature: last 10 close-to-close returns
      for(int i = 0; i < 10; i++)
         feat[i] = (float)(iClose(symbol, _Period, i) -
                           iClose(symbol, _Period, i + 1));
      if(!m_onnx.Run(feat, 10, logits, 3)) return _fallback(symbol);
      // argmax across 3 classes: 0=SELL, 1=FLAT, 2=BUY
      int best = 0;
      for(int i = 1; i < 3; i++) if(logits[i] > logits[best]) best = i;
      if(best == 0) return "SELL";
      if(best == 2) return "BUY";
      return "FLAT";
     }
  };

#endif
