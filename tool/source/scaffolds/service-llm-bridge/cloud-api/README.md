# service-llm-bridge / cloud-api

WebRequest → OpenAI / Anthropic / Gemini cloud LLM. Implements:

- 5-second timeout (configurable via `InpLlmTimeoutMs`)
- Rule-based MA(20)/MA(50) trend fallback when the cloud call fails or
  the API key is missing (Trader-17 #14 + #16)
- LLM call lives in `OnTimer()`, NOT `OnTick()` — AP-17 compliant

**Setup:**

1. Whitelist the endpoint in MetaTrader: Tools → Options → Expert
   Advisors → "Allow WebRequest for listed URL" → add
   `https://api.openai.com` (or the relevant host).
2. Set the API key via `llm.SetApiKey("sk-...")` from your `OnInit()`
   or a custom input. Do **not** commit the key to the .mq5 source.
3. Optionally swap the endpoint via `llm.SetEndpoint(...)`.

Render via:

```bash
python -m vibecodekit_mql5.build service-llm-bridge \
    --name MyLlmEA --symbol EURUSD --tf M15 --stack cloud-api
```
