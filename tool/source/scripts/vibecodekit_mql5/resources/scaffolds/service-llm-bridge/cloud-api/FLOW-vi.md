EA `{spec.name}` (scaffold **service-llm-bridge / cloud-api**) gọi
**LLM cloud API** (OpenAI / Anthropic / Google Gemini) qua `WebRequest`
trong **OnTimer** (KHÔNG OnTick — AP-17), với rule-based fallback khi
API fail/timeout. Chạy trên `{spec.symbol}` khung `{spec.timeframe}`.

Idea: gửi market context (recent OHLC, indicators) → LLM phản hồi
`BUY`/`SELL`/`HOLD` → EA route action sang trade manager. Cloud API
có latency 1-5s nên BẮT BUỘC dùng OnTimer + timeout + fallback rule
(Trader-17 #14, #16).

Tài khoản chế độ **netting** (1 net per symbol).

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo data để build
   context cho LLM.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
4. **`llm.Init(_Symbol, _Period, InpLlmTimeoutMs)`** — khởi
   `LlmCloudApiBridge`:
   - Đọc API key từ env / config file.
   - Set timeout = `InpLlmTimeoutMs` (default 5000ms).
   - Verify endpoint reachable (1 request smoke-test).
5. `registry.Reserve(InpMagic, "{spec.name}")`.
6. **`EventSetTimer(30)`** — poll LLM mỗi 30 giây.

Fail bất kỳ → `INIT_FAILED`. Đặc biệt: nếu API key sai / endpoint
down → smoke-test fail → EA không attach.

---

## Giai đoạn 2a — OnTimer (chính, mỗi 30s)

```
┌─────────────────────────────────────────────────────────┐
│ string action = llm.SuggestOrFallback(_Symbol); │
│ │
│ Bên trong SuggestOrFallback: │
│ 1. Build prompt context: │
│ - last N bars OHLC │
│ - indicators snapshot (EMA, RSI, ATR) │
│ - account state (open positions, equity) │
│ 2. WebRequest POST tới API endpoint │
│ - timeout = InpLlmTimeoutMs │
│ - retry 0 (timeout = give up, fall back) │
│ 3. Parse response: │
│ - OK + action ∈ {BUY, SELL, HOLD} → return action │
│ - timeout/HTTP 5xx/parse error → fallback │
│ 4. Fallback rule (Trader-17 #16): │
│ - vd: EMA cross + ATR confirm → BUY/SELL/HOLD │
│ │
│ if action == "BUY" → trade.Buy(...) (qua stdlib) │
│ if action == "SELL" → trade.Sell(...) │
│ if action == "HOLD" → noop │
└─────────────────────────────────────────────────────────┘
```

**Lý do KHÔNG dùng OnTick**: WebRequest blocking — nếu API chậm 3s,
OnTick sẽ block tick mới → AP-17 critical. OnTimer chạy thread riêng,
block ở đây không ảnh hưởng tick.

---

## Giai đoạn 2b — OnTick

```
   void OnTick(void) { /* execution-only path; LLM lives in OnTimer */ }
```

OnTick có thể dùng để execute order đã được OnTimer queue, HOẶC trail
stop, HOẶC monitor SL/TP. Tuyệt đối KHÔNG WebRequest ở đây.

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()` — release timer.
2. `llm.Release()` — close HTTP session / clear cache.

---

## Tính toán phối hợp các input

```
   Market context (last N bars + indicators)
              │
              ▼
   POST {API endpoint}
   timeout = InpLlmTimeoutMs
              │
       ┌──────┴──────┐
       ▼ ▼
   API response Timeout/Error
   (BUY/SELL/...) │
       │ ▼
       │ Fallback rule (Trader-17 #16)
       │ (EMA + ATR baseline)
       │ │
       └──────┬──────┘
              ▼
       action ∈ {BUY, SELL, HOLD}
              │
              ▼
   Risk gate ─┘
              │
              ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
              │
              ▼
   Trade execute (BUY/SELL/skip)
   magic = InpMagic
```

**Quy tắc tune**:

- `InpLlmTimeoutMs` 5000 = 5 giây — đủ cho hầu hết cloud LLM. Quá
  nhỏ (< 2s) → timeout nhiều, fallback ăn hết. Quá lớn (> 10s) →
  service feel sluggish, OnTimer cadence không match.
- `EventSetTimer(30)` cadence 30 giây — phù hợp `H1`/`H4`. Cho M5/M15
  có thể giảm 10-15s, nhưng phải tăng API rate limit budget.
- `InpRiskMoney` áp cho mỗi action LLM trả về. Nếu LLM "over-confident"
  ra BUY/SELL liên tục → risk tích nhanh. Cân nhắc cooldown.
- `InpLlmTimeoutMs` khai báo `sinput` → KHÔNG sweep optimizer (AP-5).
  Đây là deployment knob, không phải tuning param.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo OpenAI GPT-4 H1 | `InpRiskMoney`=10, timeout=8000ms, timer=60s |
| Live Anthropic Claude | `InpRiskMoney`=20-50, timeout=5000ms, timer=30s |
| Live Gemini Pro M15 | `InpRiskMoney`=10-30, timeout=4000ms, timer=15s |
| Prop-firm LLM | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, timeout=5000ms |

Trước khi đẩy lên live:
1. Verify API key hợp lệ + rate limit budget cover cadence (vd OpenAI
   tier 1: 3500 req/min cho gpt-4 — thừa cho timer 30s).
2. Shadow-mode 1-2 tuần (log action nhưng không execute trade) để
   verify LLM consistency.
3. Fallback rule PHẢI test riêng (vd disable network → confirm EA
   không crash mà chuyển sang fallback).
4. Cost monitor: 1 EA × 30s timer × 24h = 2880 request/ngày × ~$0.01
   = ~$30/ngày OpenAI. the kit spec §17 yêu cầu budget alert.
