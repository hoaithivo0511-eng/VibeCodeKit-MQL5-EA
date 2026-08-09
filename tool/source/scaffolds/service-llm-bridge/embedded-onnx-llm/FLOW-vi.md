EA `{spec.name}` (scaffold **service-llm-bridge / embedded-onnx-llm**)
chạy **LLM nhỏ embedded ONNX** (vd Phi-3-mini) làm **MQL5 resource**
ngay trong process EA. Chạy trên `{spec.symbol}` khung
`{spec.timeframe}`.

Khác biệt với 2 LLM bridge khác:
- **cloud-api**: WebRequest → cloud, latency 1-5s, cost theo token.
- **self-hosted-ollama**: WebRequest → localhost:11434, latency
  ~300ms-3s, không cost.
- **embedded-onnx-llm** (file này): inference TRONG MQL5 process qua
  `COnnxLoader`, latency < 1ms-5ms, **không network**, **không
  cost**, model nhỏ (Phi-3-mini ~3.8GB INT8 → vài trăm MB) packed
  trong `.ex5`.

Vì latency < 5ms nên ĐƯỢC PHÉP chạy trong OnTick (the kit spec §17.4
exception). Tài khoản chế độ **netting**.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo data context.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap.
4. **`onnx.InitFromResource("phi3_mini.onnx")`** — load ONNX model
   từ MQL5 resource. Nếu fail (model corrupt, opset không support):
   - Print warning
   - KHÔNG fail `INIT_FAILED` — chuyển sang rule fallback
5. **`llm.Init(GetPointer(onnx), _Symbol, _Period)`** — khởi
   `LlmEmbeddedOnnxLlmBridge` với pointer tới ONNX loader.
6. `registry.Reserve(InpMagic, "{spec.name}")`.

KHÔNG dùng `EventSetTimer` — inference fast đủ chạy OnTick.

---

## Giai đoạn 2 — OnTick (chính — exception cho LLM bridge)

```
┌─────────────────────────────────────────────────────────┐
│ // Embedded ONNX model runs in <1ms-5ms → safe trong │
│ // OnTick (the kit spec §17.4 exception cho local inference).│
│ │
│ string action = llm.SuggestOrFallback(_Symbol); │
│ │
│ Bên trong: │
│ 1. Build feature vector từ OHLC + indicators │
│ (numeric encoding — không phải prompt text như │
│ cloud LLM) │
│ 2. onnx.Predict(features) → tensor output │
│ 3. Argmax → class ∈ {BUY=0, SELL=1, HOLD=2} │
│ 4. ONNX fail (lúc Init không load được) → fallback │
│ rule (Trader-17 #16: EMA/ATR baseline) │
│ │
│ if action == "BUY" → trade.Buy(...) │
│ if action == "SELL" → trade.Sell(...) │
│ if action == "HOLD" → noop │
└─────────────────────────────────────────────────────────┘
```

**Lý do KHÔNG cần OnTimer**: ONNX inference ≪ thời gian tick
processing. Không I/O, không lock, không thread sync.

---

## Giai đoạn 3 — OnDeinit

1. `llm.Release()` — release wrapper.
2. `onnx.Release()` — free ONNX session + tensor buffer.

---

## Tính toán phối hợp các input

```
   Feature vector (OHLC + indicators)
              │
              ▼
   ONNX session (Phi-3-mini hoặc model nhỏ khác)
              │
              ▼
   Output tensor → argmax
              │
              ▼
   class ∈ {BUY, SELL, HOLD}
              │
       ┌──────┴──────┐
   ONNX OK ONNX fail (Init)
       │ │
       │ ▼
       │ Fallback rule
       │ (EMA + ATR baseline)
       │ │
       └─────┬─────┘
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
   Trade — magic = InpMagic
```

**Quy tắc tune**:

- Model size tradeoff:
  - Phi-3-mini 3.8B INT4 quantized: ~500MB, latency ~3-5ms.
  - LightGBM / XGBoost ONNX: 1-10MB, latency < 1ms (recommended
    cho HFT-style).
  - LSTM/CNN time-series: 10-100MB, latency 1-3ms.
- `InpRiskMoney` áp mỗi action ONNX trả. Vì latency thấp, EA có thể
  trade liên tục — cooldown manual cần thiết để tránh churn.
- Embedded LLM cho phép OnTick mỗi tick → CHẠY TRỰC TIẾP cảnh báo:
  signal có thể trigger không-trade (HOLD) thường xuyên, nếu logic
  routing sai → over-trade.

---

## Setup khuyến nghị

| Tình huống | Model | Tham số khác |
|---|---|---|
| Dev iterate small | LightGBM ONNX | `InpRiskMoney`=5, SL=15, TP=30 |
| Live H1 EURUSD | Phi-3-mini INT4 | `InpRiskMoney`=20-50, SL=30, TP=60 |
| Live M5 scalp | LightGBM small | `InpRiskMoney`=10-20, SL=10, TP=15 |
| Prop-firm embedded LLM | LightGBM (conservative) | `InpRiskMoney`=10, DD=0.04 |

Trước khi đẩy lên live:
1. Convert model train sang ONNX: `torch.onnx.export` (PyTorch) HOẶC
   `onnxmltools.convert_lightgbm` (LightGBM). Verify opset MQL5
   support (≤ 18).
2. Compile EA với model resource → `.ex5` nặng hơn (model + binary).
3. Verify inference accuracy MATCH với Python (same input → same
   output) qua test harness.
4. Backtest in-sample + walkforward 3-fold.
5. Shadow-mode 1-2 tuần (log prediction nhưng không trade) để verify
   distribution không drift trên live data.
6. Canary 30 phút trước khi push full live.

**Lợi thế cuối cùng**: embedded ONNX EA hoàn toàn self-contained —
không cần internet, không cần Python sidecar, không cần Ollama
server. Deploy: copy `.ex5` lên VPS là chạy.
