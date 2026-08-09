EA `{spec.name}` (scaffold **mean-reversion / hedging**) dùng tín hiệu
**RSI band fade** (giá quay đầu khi RSI chạm overbought/oversold) trên
`{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ **hedging**
(cho phép tồn tại Buy + Sell cùng symbol — phù hợp cho ranging market
fade 2 chiều).

Idea: thị trường sideways, giá có xu hướng quay về trung bình sau khi
chạm extreme. Long khi RSI dip < oversold; Short khi RSI pop > overbought.
Same-bar guard ngăn re-entry trong cùng nến.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo data tính RSI.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
4. `registry.Reserve(InpMagic, "{spec.name}")`.
5. `trade.Init((ulong)InpMagic)`.
6. **`h_rsi = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE)`** —
   RSI handle, tồn tại suốt đời EA, release ở OnDeinit.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Same-bar guard │
│ if bars == last_bar → return │
├─────────────────────────────────────────────────────────┤
│ 3. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 4. Lấy RSI nến vừa đóng │
│ CopyBuffer(h_rsi, 0, 0, 1, rsi) │
│ rsi[0] ∈ [0, 100] │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot │
│ lots = pip.LotForRisk(InpRiskMoney, InpSlPips) │
├─────────────────────────────────────────────────────────┤
│ 6. Compute SL/TP │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
├─────────────────────────────────────────────────────────┤
│ 7. Check signal │
│ BUY: rsi[0] < InpRsiOversold (vd < 30) │
│ SELL: rsi[0] > InpRsiOverbought (vd > 70) │
├─────────────────────────────────────────────────────────┤
│ 8. Mở lệnh │
│ BUY: trade.Buy(lots, sym, ask - sl_dist, │
│ ask + tp_dist) │
│ SELL: trade.Sell(lots, sym, bid + sl_dist, │
│ bid - tp_dist) │
│ Hedging: Buy + Sell cùng lúc OK (mỗi ticket riêng) │
└─────────────────────────────────────────────────────────┘
```

`IsBuySignal()` / `IsSellSignal()` chỉ check threshold đơn giản — dev
có thể nâng cấp thành "divergence + threshold" hoặc "RSI cross 50 từ
extreme" để giảm fake-out.

---

## Giai đoạn 3 — OnDeinit

1. `IndicatorRelease(h_rsi)` — trả handle. Bắt buộc, không release →
   memory leak.

---

## Tính toán phối hợp các input

```
   InpRsiPeriod ──► RSI(period)
                       │
                       ▼
   rsi[0] < InpRsiOversold → BUY
   rsi[0] > InpRsiOverbought → SELL
                       │
                       ▼
   Risk gate ──┐
                │
                ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
                │
                ▼
   SL = entry ∓ InpSlPips pip
   TP = entry ± InpTpPips pip
   magic = InpMagic
```

**Quy tắc tune**:

- `InpRsiPeriod` chuẩn 14. Nhỏ hơn (7-10) → RSI nhạy, nhiều signal
  nhưng nhiễu. Lớn hơn (20-30) → ít signal, chất lượng cao hơn.
- `InpRsiOversold` / `InpRsiOverbought` đối xứng quanh 50 (30/70 là
  default). Hẹp hơn (40/60) → nhiều signal; rộng hơn (20/80) → ít.
- Mean-reversion FAIL khi market trending mạnh — short ở RSI=80 lúc
  bull run sẽ lỗ to. Cân nhắc thêm filter trend (EMA200, ADX) →
  switch sang `wizard-composable` để compose nhiều module.
- Hedging account cho phép HOLD cả Buy + Sell cùng lúc — phù hợp
  ranging market 2 chiều, nhưng `InpMaxPositions` đếm CẢ HAI chiều.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo ranging market H1 | `InpRiskMoney`=10, RSI(14), 30/70, SL=30, TP=60 |
| Live H1 EURUSD ranging | `InpRiskMoney`=20-50, RSI(14), 30/70 |
| Live M15 scalp fade | `InpRiskMoney`=10-30, RSI(7), 25/75, SL=15, TP=20 |
| Prop-firm mean-rev | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, RSI(14), 25/75 |

Trước khi đẩy lên live: kiểm regime (ADX < 25 ranging tốt cho
mean-rev, ADX > 25 trending sẽ lỗ). Walkforward 3-fold xác nhận edge
bền qua nhiều giai đoạn. Quan trọng: mean-reversion thường có win-rate
cao nhưng loss tail dài — phải có SL kỷ luật.
