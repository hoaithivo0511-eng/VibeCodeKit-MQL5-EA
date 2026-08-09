EA `{spec.name}` (scaffold **stdlib / hedging**) là **scaffold khởi đầu
tối giản** trên `{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế
độ **hedging** (cho phép tồn tại đồng thời Buy + Sell cùng symbol —
mỗi position là 1 ticket riêng, KHÔNG net).

Cấu trúc giống `stdlib/netting` — khác duy nhất: dev được phép mở Buy
+ Sell song song (vd hedging multi-leg, news straddle, basket riêng
chiều). Mỗi lệnh PHẢI có SL/TP cố định (không trade no-stop-loss).

---

## Giai đoạn 1 — OnInit

1. **`pip.Init(_Symbol)`** — chuẩn hoá pip cho `{spec.symbol}` (digits,
   point, JPY/non-JPY).
2. **`risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)`** — DD cap
   {spec.risk.daily_loss_pct:pct}, tối đa {InpMaxPositions} lệnh đồng
   thời, 10% margin buffer. Trên hedging account `max_positions` đếm
   TỔNG ticket (cả Buy lẫn Sell).
3. **`registry.Reserve(InpMagic, "{spec.name}")`** — chiếm magic
   number; nếu đã có owner → giữ owner cũ.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() — equity tracker + daily reset │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
│ (DD/positions/margin gate) │
├─────────────────────────────────────────────────────────┤
│ 3. Compute lot + SL │
│ sl = pip.Pips(InpSlPips) │
│ lot = pip.LotForRisk(InpRiskMoney, InpSlPips) │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Signal + order placement │
│ Scaffold dừng ở đây. Đặc thù hedging: │
│ • dev có thể mở Buy + Sell cùng lúc │
│ • mỗi ticket có magic = InpMagic, SL/TP riêng │
│ • InpMaxPositions count CẢ HAI chiều │
└─────────────────────────────────────────────────────────┘
```

**Hedging vs netting**: trên hedging, mỗi `OrderSend` ra 1 ticket mới.
Trên netting, `OrderSend` ngược chiều với position hiện có sẽ NET (đóng
trừ bớt). Code logic của bạn phải match account_type — `mql5-doctor`
sẽ cảnh báo nếu lệch.

---

## Giai đoạn 3 — OnDeinit

Trống. Khi dev thêm indicator handle → tự `IndicatorRelease()` ở đây.

---

## Tính toán phối hợp các input

```
   Risk gate ──┐
               ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
               ▼
   [DEV] order Buy / Sell / both
               ▼
   SL = entry ∓ InpSlPips × pip
   TP = entry ± InpTpPips × pip
   magic = InpMagic
```

**Quy tắc tune**:

- Trên hedging account, lot tổng = lot per leg × số leg. Nếu dev mở
  2 leg (1 Buy + 1 Sell), risk thực tế ≈ 2× `InpRiskMoney`.
- `InpMaxPositions` đếm TẤT CẢ ticket có magic này, không phân biệt
  chiều. Đặt = 2 nếu chỉ muốn 1 Buy + 1 Sell.
- Đổi `InpSlPips` mà giữ `InpRiskMoney` → lot tự nghịch đảo.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo hedging test | `InpRiskMoney`=10, `InpMaxPositions`=4 (cho 2 leg × 2 pair) |
| Live hedging < 1000 USD | `InpRiskMoney`=10 (1%), `InpMaxPositions`=2 |
| Live hedging 1000-10000 USD | `InpRiskMoney`=20-50, `InpMaxPositions`=4 |
| Prop-firm hedging (FTMO) | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, `InpMaxPositions`=2 |

Quan trọng: kiểm tra broker có hỗ trợ hedging chưa
(`mql5-broker-safety <ea>.mq5` → kiểm `ACCOUNT_MARGIN_MODE`). Một số
prop-firm chỉ cho phép netting — chạy scaffold này sẽ fail open lệnh
thứ 2.
