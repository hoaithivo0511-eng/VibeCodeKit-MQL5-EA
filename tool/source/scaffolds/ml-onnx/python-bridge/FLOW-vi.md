EA `{spec.name}` (scaffold **ml-onnx / python-bridge**) chạy **inference
ML qua mô hình ONNX** trên `{spec.symbol}` khung `{spec.timeframe}`. Mô
hình thường được train ở Python (PyTorch / sklearn / LightGBM), export
sang ONNX, rồi MQL5 load qua `COnnxLoader` HOẶC qua Python sidecar gửi
prediction qua file IPC.

Tài khoản chế độ **netting** (1 net position per symbol).

Scaffold này có 2 lớp:
- **EA layer (.mq5)**: framework risk + magic + signal consumer.
- **Python layer (`python/`)**: feature pipeline + model loader +
  prediction writer. Chạy độc lập, communicate qua file.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip cho `{spec.symbol}`.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD cap
   {spec.risk.daily_loss_pct:pct}, {InpMaxPositions} max.
3. `registry.Reserve(InpMagic, "{spec.name}")` — magic.
4. **[DEV FILL] Setup ML pipeline**:
   - **Option A — Embedded ONNX**: `COnnxLoader.Init(model_path)` →
     model trong MQL5 process, inference < 5ms, có thể chạy OnTick.
   - **Option B — Python sidecar**: spawn Python (systemd /
     supervisor) → Python tick-poll → ghi prediction vào
     `MQL5/Files/{spec.name}_pred.json` → EA `EventSetTimer(N)` để
     poll. KHÔNG gọi REST/Python từ OnTick (AP-17).

Fail bất kỳ → `INIT_FAILED`. Lưu ý: COnnxLoader fail (model file
corrupt, opset không support) cần fallback rule-based, không crash EA.

---

## Giai đoạn 2 — OnTick (Option A) hoặc OnTimer (Option B)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() / OnTimer prologue │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate (DD/positions/margin) │
├─────────────────────────────────────────────────────────┤
│ 3. Lấy prediction │
│ Embedded: pred = onnx.Predict(features) │
│ Bridge: pred = ReadJsonFile("{spec.name}_pred...) │
│ pred = { class: BUY|SELL|HOLD, confidence: 0..1 } │
├─────────────────────────────────────────────────────────┤
│ 4. Threshold filter │
│ if pred.confidence < threshold → skip (sinput knob) │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot │
│ lot = pip.LotForRisk(InpRiskMoney, InpSlPips) │
│ (optionally scale lot theo confidence) │
├─────────────────────────────────────────────────────────┤
│ 6. [DEV FILL] Place order theo pred.class │
│ BUY → trade.Buy(lot, sym, sl, tp) │
│ SELL → trade.Sell(lot, sym, sl, tp) │
│ HOLD → noop │
└─────────────────────────────────────────────────────────┘
```

**Quan trọng**: nếu Python sidecar dead (process crash, file stale),
EA phải SKIP signal, không mở lệnh theo prediction cũ. Check file
mtime mỗi lần đọc.

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()` (Option B).
2. `onnx.Release()` (Option A) — free model resource.
3. Python sidecar lifecycle độc lập (không kill từ EA).

---

## Tính toán phối hợp các input

```
   Feature pipeline (Python OR MQL5)
                  │
                  ▼
   ONNX model (.onnx file)
                  │
                  ▼
   prediction = { class, confidence }
                  │
                  ▼ confidence > threshold
   Risk gate ────┤
                  │
                  ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
   (optional: lot × confidence)
                  │
                  ▼
   Order — magic = InpMagic
```

**Quy tắc tune**:

- `InpRiskMoney` cố định USD/lệnh, BẤT KỂ confidence. Để scale theo
  confidence → dev nhân lot ở step 5 (cẩn thận risk thực tế chệch).
- Threshold quá thấp → over-trade (mọi noise đều mở lệnh). Quá cao
  → ít signal. Optimize threshold qua walkforward.
- Cadence OnTimer phải > thời gian Python predict 1 lần (tránh đọc
  file đang ghi).

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Dev iterate model | `InpRiskMoney`=10, threshold=0.55, timer=10s |
| Live (Embedded ONNX) | `InpRiskMoney`=20-50, threshold=0.65 |
| Live (Python bridge) | `InpRiskMoney`=20-50, threshold=0.65, timer=30-60s |
| Prop-firm ML | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, threshold=0.70 |

Trước khi đẩy lên live: backtest in-sample + walkforward 3-fold,
shadow-mode (log prediction nhưng KHÔNG mở lệnh) 1-2 tuần để verify
distribution không drift, sau đó canary 30 phút live.
