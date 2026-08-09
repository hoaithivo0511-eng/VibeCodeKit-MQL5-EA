EA `{spec.name}` (scaffold **stdlib / netting**) là **scaffold khởi đầu tối
giản** trên `{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ
**netting** (1 chiều cùng symbol — Buy mới sẽ net với Sell cũ thành position
trừ trừ, không tồn tại 2 lệnh ngược chiều cùng lúc).

Mục đích của scaffold này là cung cấp **bộ khung an toàn**
(CPipNormalizer · CRiskGuard · CMagicRegistry) sẵn sàng; phần signal +
order placement do dev điền theo edge riêng. Mỗi lệnh khi được điền vào
PHẢI có SL/TP cố định (không trade no-stop-loss — vi phạm AP-1).

---

## Giai đoạn 1 — OnInit (chạy 1 lần khi attach EA lên chart)

1. **Khởi tạo `CPipNormalizer pip`**
   - `pip.Init(_Symbol)` đo digits + point của `{spec.symbol}` để chuẩn hoá
     "1 pip" cross-broker (5-digit vs 4-digit, JPY 3-digit vs 5-digit).
   - Nếu fail → `INIT_FAILED`, EA không attach.
2. **Khởi tạo `CRiskGuard risk`**
   - `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — ghi snapshot
     equity đầu ngày, set ngưỡng DD = {spec.risk.daily_loss_pct:pct}, cap
     tối đa {InpMaxPositions} lệnh đồng thời, dự trữ 10% margin buffer.
3. **Reserve magic number**
   - `registry.Check(InpMagic)` → nếu magic chưa có owner →
     `registry.Reserve(InpMagic, "{spec.name}")`. Magic ≠ tag tuỳ ý:
     nó là khoá để CSafeTradeManager / CMagicRegistry phân biệt lệnh
     của EA này với EA khác trong cùng terminal.

---

## Giai đoạn 2 — OnTick (chạy mỗi tick)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
│ Cập nhật equity tracker + reset daily snapshot │
│ qua 00:00 broker timezone │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
│ (DD ≥ daily_loss_pct HOẶC positions ≥ max_positions │
│ HOẶC margin level < safe threshold) │
├─────────────────────────────────────────────────────────┤
│ 3. Compute SL distance + lot size │
│ sl = pip.Pips(InpSlPips) (price units) │
│ lot = pip.LotForRisk(InpRiskMoney, InpSlPips) │
│ = InpRiskMoney ÷ (InpSlPips × pip_value) │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Signal + order placement │
│ Scaffold dừng ở đây — dev tự thêm: │
│ • compute signal (indicator buffer, price action…) │
│ • check entry condition │
│ • call CSafeTradeManager.Buy / Sell với SL/TP │
│ Nếu lot ≤ 0 → log "skipped: lot=0 reason=…" │
└─────────────────────────────────────────────────────────┘
```

**Quan trọng**: scaffold gốc KHÔNG tự đặt lệnh — đây là chủ ý để mỗi
edge tự quyết định kiểu signal. Đừng tin "EA chạy mà không có signal
code thì sẽ mở lệnh ngẫu nhiên".

---

## Giai đoạn 3 — OnDeinit

`OnDeinit(const int reason)` trống — scaffold không hold indicator
handle hoặc tài nguyên động nào ngoài 3 object trên (auto-destructed).
Khi dev thêm `iMA` / `iRSI` / `iATR` handle, phải tự thêm
`IndicatorRelease()` ở đây.

---

## Tính toán phối hợp các input

```
┌─────────────────────────────────────────────────────────┐
│ Risk gate │
│ ┌──────────────────────────────────────────────────┐ │
│ │ equity_loss ≤ InpDailyLossPct × equity_start │ │
│ │ AND open_positions < InpMaxPositions │ │
│ └──────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Position sizing │
│ ┌──────────────────────────────────────────────────┐ │
│ │ lot = InpRiskMoney ÷ (InpSlPips × pip_value) │ │
│ └──────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ [DEV] Order placement │
│ ┌──────────────────────────────────────────────────┐ │
│ │ entry ± InpSlPips, entry ± InpTpPips │ │
│ │ magic = InpMagic │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Quy tắc tune**:

- `InpRiskMoney` là **USD per trade**, không phải lot. Lot tự suy ra
  từ công thức trên — không cần override.
- Đổi `InpSlPips` mà GIỮ `InpRiskMoney` → lot tự thay đổi nghịch đảo
  (SL rộng hơn → lot nhỏ hơn, USD risk giữ nguyên).
- Trên netting account, mở Buy khi đã có Sell sẽ NET (đóng bớt Sell
  hoặc lật chiều) — KHÔNG tồn tại 2 lệnh ngược cùng lúc. Đừng dùng
  scaffold này cho strategy cần hedge song song.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo paper-trading | `InpRiskMoney`=10, `InpSlPips`=30, `InpTpPips`=60, `InpDailyLossPct`=0.05 |
| Live account < 1000 USD | `InpRiskMoney`=10 (1% equity), `InpMaxPositions`=2 |
| Live account 1000-10000 USD | `InpRiskMoney`=20-50, `InpMaxPositions`=3 |
| Prop-firm challenge (FTMO 5%) | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, `InpMaxPositions`=2 |

Trước khi đẩy lên live: hoàn thiện signal code, backtest tối thiểu
6 tháng `{spec.symbol}` `{spec.timeframe}`, MFE/MAE log, walkforward
3-fold, sau đó canary 30 phút demo realtime qua `mql5-canary`.
