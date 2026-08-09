# service-llm-bridge / self-hosted-ollama

WebRequest → http://localhost:11434 (Ollama API). Trade decisions are
sourced from a locally-running open-weights model (Llama 3.x, Qwen 2.5,
DeepSeek-Coder, etc.). The fallback path is an RSI(14) reversion signal.

Run Ollama on the VPS hosting the EA:

```bash
ollama pull llama3.2
ollama serve # listens on 127.0.0.1:11434
```

Whitelist `http://127.0.0.1:11434` in MetaTrader Expert Advisor options.
LLM calls happen in `OnTimer()` every 30 seconds — never `OnTick()`.
