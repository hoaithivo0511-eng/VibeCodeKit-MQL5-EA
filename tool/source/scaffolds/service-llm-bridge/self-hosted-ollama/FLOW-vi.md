EA `{spec.name}` (scaffold **service-llm-bridge / self-hosted-ollama**)
gọi **LLM self-hosted qua Ollama API** (`http://localhost:11434`) trong
**OnTimer** (KHÔNG OnTick — AP-17), với rule-based fallback. Chạy trên
`{spec.symbol}` khung `{spec.timeframe}`.

Idea: tương tự `cloud-api` nhưng LLM chạy local (Ollama server trên
cùng VPS / host). Lợi thế:
1. **Không cost theo token** — chỉ tốn GPU/CPU.
2. **Latency thấp hơn** (localhost ~200-500ms vs cloud 1-3s).
3. **Privacy** — context không gửi ra third-party.

Tradeoff: model nhỏ hơn (llama3.2 8B vs GPT-4) → quality thấp hơn,
cần test cẩn thận.

Tài khoản chế độ **netting**.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo data context.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap.
4. **`llm.Init(_Symbol, _Period, InpLlmTimeoutMs)`** — khởi
   `LlmSelfHostedOllamaBridge`:
   - Endpoint cố định `http://localhost:11434/api/generate`.
   - Smoke-test: GET `/api/tags` để verify Ollama process running.
5. **`llm.SetModel(InpModel)`** — chọn model (vd `llama3.2`,
   `mistral`, `qwen2.5`). Model PHẢI đã `ollama pull` trước.
6. `registry.Reserve(InpMagic, "{spec.name}")`.
7. **`EventSetTimer(30)`** — poll mỗi 30 giây.

Fail bất kỳ → `INIT_FAILED`. Đặc biệt: Ollama server down → smoke
test fail → EA không attach.

---

## Giai đoạn 2 — OnTimer (chính)

```
┌─────────────────────────────────────────────────────────┐
│ string action = llm.SuggestOrFallback(_Symbol); │
│ │
│ Bên trong: │
│ 1. Build prompt context (OHLC + indicators) │
│ 2. POST http://localhost:11434/api/generate │
│ body: { │
│ "model": InpModel, │
│ "prompt": "...", │
│ "stream": false, │
│ "options": {"temperature": 0.0} │
│ } │
│ timeout = InpLlmTimeoutMs │
│ 3. Parse Ollama response (.response field) │
│ - extract action ∈ {BUY, SELL, HOLD} │
│ - OK → return action │
│ - timeout/parse error → fallback │
│ 4. Fallback rule (Trader-17 #16) │
│ │
│ route action → trade manager (BUY/SELL/skip) │
└─────────────────────────────────────────────────────────┘
```

OnTick reserved for execution-only (không LLM).

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()`.
2. `llm.Release()` — close HTTP session.

---

## Tính toán phối hợp các input

```
   Market context
        │
        ▼
   POST localhost:11434/api/generate
   model=InpModel, timeout=InpLlmTimeoutMs
        │
   ┌────┴─────┐
   ▼ ▼
   200 OK timeout/error
   action │
        │ ▼
        │ Fallback rule
        │ │
        └──┬───┘
           ▼
   action ∈ {BUY, SELL, HOLD}
           │
           ▼
   Risk gate ─┐
              │
              ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
              │
              ▼
   Trade execute — magic = InpMagic
```

**Quy tắc tune**:

- `InpModel` quyết định quality vs latency:
  - `llama3.2` (3B): latency ~300ms, quality cơ bản — fast inference.
  - `llama3.1:8b`: latency ~1s, quality khá — balanced.
  - `qwen2.5:14b`: latency ~3s, quality cao — chỉ phù hợp khi có GPU.
  - `mistral:7b`: latency ~1s, mạnh phân tích — alt cho llama.
- `InpLlmTimeoutMs` 5000 — nếu Ollama overload (queue request khác
  của hệ thống), có thể vượt. Tăng nếu thường timeout, nhưng OnTimer
  cadence cũng phải tăng theo.
- Local LLM → có thể chạy timer ngắn hơn cloud (15s vs 30s) vì không
  bị rate limit.
- `InpRiskMoney` áp mỗi action; local model dễ over-confident (thiếu
  RLHF tinh chỉnh) — cân nhắc threshold post-process.

---

## Setup khuyến nghị

| Tình huống | Model | Tham số khác |
|---|---|---|
| Dev iterate cheap | `llama3.2` (3B) | timer=10s, RiskMoney=10 |
| Live VPS có GPU | `llama3.1:8b` | timer=15s, RiskMoney=20-50 |
| Live VPS CPU-only | `llama3.2` (3B) | timer=30s, RiskMoney=10-20 |
| Prop-firm local LLM | `llama3.1:8b` | RiskMoney=10, DD=0.04, timer=30s |

Trước khi đẩy lên live:
1. `ollama pull <model>` + verify `ollama run <model>` interactive
   trả về kết quả hợp lý cho prompt mẫu.
2. Benchmark latency: `time curl -X POST localhost:11434/api/generate
   -d '{"model":"...", "prompt":"..."}'`. Set `InpLlmTimeoutMs` ≥
   2× latency thực.
3. Verify Ollama auto-restart trên VPS reboot (systemd service).
4. Monitor RAM: model 8B cần ~6GB RAM, model 14B cần ~10GB RAM.
   VPS quá yếu → swap → latency crash.
5. Shadow-mode 1-2 tuần để verify local model không drift.
