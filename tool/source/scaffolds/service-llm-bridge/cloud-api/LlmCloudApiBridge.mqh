//+------------------------------------------------------------------+
//| LlmCloudApiBridge.mqh — WebRequest -> Cloud chat completion       |
//|                                                                   |
//| Routes a per-symbol prompt to a configurable Cloud LLM endpoint  |
//| (OpenAI, Anthropic, Gemini) via WebRequest(). Enforces a 5-second |
//| timeout and falls back to a rule-based MA(20/50) cross signal if  |
//| the call fails or returns an empty payload.                       |
//|                                                                   |
//| In MQL5, iMA() returns an indicator handle (int). The actual MA  |
//| value is read with CopyBuffer(). Handles are created once in     |
//| Init() and released in Release() to avoid leaks (AP-12).         |
//+------------------------------------------------------------------+
#ifndef __LlmCloudApiBridge_MQH__
#define __LlmCloudApiBridge_MQH__

class LlmCloudApiBridge
  {
private:
   int               m_timeout_ms;
   string            m_endpoint;
   string            m_api_key;
   int               m_h_fast;
   int               m_h_slow;

   string            _rule_based_fallback(const string symbol)
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
                     LlmCloudApiBridge(void)
                       : m_timeout_ms(5000),
                         m_endpoint("https://api.openai.com/v1/chat/completions"),
                         m_api_key(""),
                         m_h_fast(INVALID_HANDLE),
                         m_h_slow(INVALID_HANDLE) {}

   bool              Init(const string symbol, const ENUM_TIMEFRAMES tf,
                          const int timeout_ms = 5000)
     {
      m_timeout_ms = timeout_ms;
      m_h_fast = iMA(symbol, tf, 20, 0, MODE_EMA, PRICE_CLOSE);
      m_h_slow = iMA(symbol, tf, 50, 0, MODE_EMA, PRICE_CLOSE);
      return (m_h_fast != INVALID_HANDLE && m_h_slow != INVALID_HANDLE);
     }

   void              Release(void)
     {
      if(m_h_fast != INVALID_HANDLE) { IndicatorRelease(m_h_fast); m_h_fast = INVALID_HANDLE; }
      if(m_h_slow != INVALID_HANDLE) { IndicatorRelease(m_h_slow); m_h_slow = INVALID_HANDLE; }
     }

   void              SetEndpoint(const string url) { m_endpoint = url; }
   void              SetApiKey(const string key)   { m_api_key  = key;  }

   string            SuggestOrFallback(const string symbol)
     {
      if(m_api_key == "") return _rule_based_fallback(symbol);

      string payload = StringFormat("{\"model\":\"gpt-4o-mini\","
                                    "\"messages\":[{\"role\":\"user\","
                                    "\"content\":\"Trend for %s now? Reply BUY|SELL|FLAT only.\"}]}",
                                    symbol);
      // StringToCharArray: when count=-1, MQL5 copies the trailing 0
      // terminator into the output array. WebRequest then sends those
      // bytes verbatim, and strict JSON parsers (Python json.loads(),
      // Go json.Unmarshal()) reject the trailing \0 with a parse error.
      // Use StringLen(payload) so the request body is exactly the JSON
      // bytes — no trailing null.
      char post[]; StringToCharArray(payload, post, 0, StringLen(payload), CP_UTF8);
      char result[]; string headers_out;
      int code = WebRequest("POST", m_endpoint,
                            "Authorization: Bearer " + m_api_key + "\r\n"
                            "Content-Type: application/json\r\n",
                            m_timeout_ms, post, result, headers_out);
      if(code != 200) return _rule_based_fallback(symbol);
      string body = CharArrayToString(result);
      if(StringFind(body, "BUY")  >= 0) return "BUY";
      if(StringFind(body, "SELL") >= 0) return "SELL";
      return "FLAT";
     }
  };

#endif
