//+------------------------------------------------------------------+
//| LlmSelfHostedOllamaBridge.mqh — WebRequest -> Ollama localhost   |
//|                                                                   |
//| In MQL5, iRSI() returns an indicator handle (int). The actual RSI |
//| value is read with CopyBuffer(). The handle is created once in   |
//| Init() and released in Release() to avoid leaks (AP-12).         |
//+------------------------------------------------------------------+
#ifndef __LlmSelfHostedOllamaBridge_MQH__
#define __LlmSelfHostedOllamaBridge_MQH__

class LlmSelfHostedOllamaBridge
  {
private:
   int               m_timeout_ms;
   string            m_endpoint;
   string            m_model;
   int               m_h_rsi;

   string            _fallback(const string symbol)
     {
      if(m_h_rsi == INVALID_HANDLE) return "FLAT";
      double buf[1];
      if(CopyBuffer(m_h_rsi, 0, 0, 1, buf) != 1) return "FLAT";
      if(buf[0] > 70.0) return "SELL";
      if(buf[0] < 30.0) return "BUY";
      return "FLAT";
     }

public:
                     LlmSelfHostedOllamaBridge(void)
                       : m_timeout_ms(5000),
                         m_endpoint("http://127.0.0.1:11434/api/generate"),
                         m_model("llama3.2"),
                         m_h_rsi(INVALID_HANDLE) {}

   bool              Init(const string symbol, const ENUM_TIMEFRAMES tf,
                          const int timeout_ms = 5000)
     {
      m_timeout_ms = timeout_ms;
      m_h_rsi = iRSI(symbol, tf, 14, PRICE_CLOSE);
      return (m_h_rsi != INVALID_HANDLE);
     }

   void              Release(void)
     {
      if(m_h_rsi != INVALID_HANDLE)
        { IndicatorRelease(m_h_rsi); m_h_rsi = INVALID_HANDLE; }
     }

   void              SetEndpoint(const string url) { m_endpoint = url; }
   void              SetModel(const string m)      { m_model    = m;   }

   string            SuggestOrFallback(const string symbol)
     {
      string payload = StringFormat("{\"model\":\"%s\",\"prompt\":"
                                    "\"Trend for %s now? Reply BUY|SELL|FLAT only.\","
                                    "\"stream\":false}", m_model, symbol);
      // StringToCharArray with count=-1 copies the trailing 0 into
      // the array; Ollama's Go HTTP server then sees JSON followed by
      // a null byte and json.Unmarshal() rejects it. Use StringLen()
      // so the request body is exactly the JSON bytes.
      char post[]; StringToCharArray(payload, post, 0, StringLen(payload), CP_UTF8);
      char result[]; string headers_out;
      int code = WebRequest("POST", m_endpoint,
                            "Content-Type: application/json\r\n",
                            m_timeout_ms, post, result, headers_out);
      if(code != 200) return _fallback(symbol);
      string body = CharArrayToString(result);
      if(StringFind(body, "BUY")  >= 0) return "BUY";
      if(StringFind(body, "SELL") >= 0) return "SELL";
      return "FLAT";
     }
  };

#endif
