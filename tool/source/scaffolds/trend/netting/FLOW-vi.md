EA `{spec.name}` (scaffold **trend / netting**) dùng cross của 2 đường EMA
(nhanh × chậm) để phát hiện đảo chiều xu hướng trên `{spec.symbol}` khung
`{spec.timeframe}`. Tài khoản chế độ
**netting** (1 chiều cùng symbol — không hedge cùng lúc Buy + Sell).

Trade chỉ mở khi nến vừa đóng (signal trên `bar[1]`) — tránh false trigger
giữa nến. Mỗi lệnh được set SL/TP cố định ngay khi entry; không trade
no-stop-loss (vi phạm AP-1).

---

## Giai đoạn 1 — OnInit (chạy 1 lần khi attach EA lên chart)

1. **Khởi tạo `CPipNormalizer pip`**
   - Lệnh: `pip.Init(_Symbol)` đo digits + point của `{spec.symbol}`.
   - Lý do: broker khác nhau quy ước "1 pip" khác nhau (5-digit vs 4-digit,
     JPY 3-digit vs 5-digit). Cross-broker truth-table do `pip` giữ.
2. **Ensure history bars**
   - `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo có ≥ 300 nến lịch sử
     để EMA chậm đủ data tính.
3. **Khởi tạo `CRiskGuard risk`**
   - `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — ghi snapshot equity
     đầu ngày, set ngưỡng DD = {spec.risk.daily_loss_pct:pct}, cap tối đa
     {InpMaxPositions} lệnh đồng thời.
4. **Reserve magic number**
   - `registry.Reserve(InpMagic, "{spec.name}")` — chiếm `InpMagic` trong
     CMagicRegistry. Nếu magic đã có chủ → bỏ qua reserve (giữ owner cũ).
5. **Init trade manager**
   - `trade.Init((ulong)InpMagic)` — CSafeTradeManager sẽ chỉ thao tác trên
     lệnh có magic này.
6. **Tạo MA handle**
   - `h_fast = iMA(_Symbol, _Period, InpEmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE)`
   - `h_slow = iMA(_Symbol, _Period, InpEmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE)`
   - 2 handle tồn tại suốt đời EA, release ở OnDeinit.

Nếu bất kỳ bước nào fail → trả `INIT_FAILED`, EA không attach.

---

## Giai đoạn 2 — OnTick (chạy mỗi tick)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
│ Cập nhật equity tracker + reset daily snapshot │
│ qua 00:00 broker timezone │
├─────────────────────────────────────────────────────────┤
│ 2. Same-bar guard │
│ if bars == last_bar → return │
│ (chỉ xử lý 1 lần mỗi nến mới) │
├─────────────────────────────────────────────────────────┤
│ 3. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
│ (DD ≥ daily_loss_pct HOẶC positions ≥ max_positions │
│ HOẶC margin level < safe threshold) │
├─────────────────────────────────────────────────────────┤
│ 4. Đọc indicator buffer │
│ CopyBuffer(h_fast, 0, 0, 2, fast) │
│ CopyBuffer(h_slow, 0, 0, 2, slow) │
│ (lấy 2 nến gần nhất: [0]=current, [1]=just-closed) │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot size │
│ lots = pip.LotForRisk(InpRiskMoney, InpSlPips) │
│ = InpRiskMoney ÷ (InpSlPips × pip_value) │
│ (clamp về step lot tối thiểu của broker) │
│ if lots ≤ 0 → return (broker reject quá nhỏ) │
├─────────────────────────────────────────────────────────┤
│ 6. Compute SL/TP distance │
│ sl_dist = pip.Pips(InpSlPips) (price units) │
│ tp_dist = pip.Pips(InpTpPips) │
├─────────────────────────────────────────────────────────┤
│ 7. Check signal trên bar[1] (vừa đóng) │
│ Buy: fast[1] > slow[1] AND fast[0] ≤ slow[0] │
│ (fast cross above slow tại bar đang chạy) │
│ Sell: fast[1] < slow[1] AND fast[0] ≥ slow[0] │
│ (fast cross below slow tại bar đang chạy) │
├─────────────────────────────────────────────────────────┤
│ 8. Mở lệnh │
│ Buy: trade.Buy(lots, _Symbol, ask - sl_dist, │
│ ask + tp_dist) │
│ Sell: trade.Sell(lots, _Symbol, bid + sl_dist, │
│ bid - tp_dist) │
│ CSafeTradeManager retry tối đa N lần nếu requote. │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 3 — OnDeinit (chạy khi tháo EA / restart terminal)

1. `IndicatorRelease(h_fast)` + `IndicatorRelease(h_slow)` — trả handle cho
   terminal. Không release → memory leak qua nhiều EA cycle.
2. `risk.OnDeinit()` (implicit qua destructor) — flush log nếu có.
3. CMagicRegistry KHÔNG release magic (giữ reservation để EA attach lại
   cùng magic không bị conflict).

---

## Tính toán phối hợp các input

```
┌─────────────────────────────────────────────────────────┐
│ Tín hiệu (signal) │
│ ┌──────────────────────────────────────────────────┐ │
│ │ fast EMA (period = InpEmaFastPeriod) │ │
│ │ × slow EMA (period = InpEmaSlowPeriod) │ │
│ └──────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Risk gate │
│ ┌──────────────────────────────────────────────────┐ │
│ │ DD ≤ InpDailyLossPct │ │
│ │ AND positions < InpMaxPositions │ │
│ └──────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Position sizing │
│ ┌──────────────────────────────────────────────────┐ │
│ │ lot = InpRiskMoney ÷ (InpSlPips × pip_value) │ │
│ └──────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Order placement │
│ ┌──────────────────────────────────────────────────┐ │
│ │ entry ± InpSlPips, entry ± InpTpPips │ │
│ │ magic = InpMagic │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Quy tắc tune:**

- Tăng `InpRiskMoney` (USD risk/lệnh) → lot tự tăng tỷ lệ. Để cùng % equity
  trên account khác nhau, scale theo balance.
- Đổi `InpSlPips` mà GIỮ `InpRiskMoney` → lot tự thay đổi nghịch đảo (SL
  rộng hơn → lot nhỏ hơn, USD risk giữ nguyên).
- Đổi `InpSlPips` và `InpTpPips` cùng tỷ lệ → giữ Risk:Reward ratio.
- Đổi `InpEmaFastPeriod` / `InpEmaSlowPeriod` → khai báo `sinput` nên
  Strategy Tester optimiser KHÔNG sweep. Đổi sang `input` thủ công nếu
  muốn optimize.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo paper-trading | `InpRiskMoney`=10, `InpSlPips`=30, `InpTpPips`=60, `InpDailyLossPct`=0.05 |
| Live account < 1000 USD | `InpRiskMoney`=10 (1%), `InpMaxPositions`=2 |
| Live account 1000-10000 USD | `InpRiskMoney`=20-50 (1-0.5%), `InpMaxPositions`=3 |
| Prop-firm challenge (FTMO 5%) | `InpRiskMoney`=10, `InpDailyLossPct`=0.04 (buffer 1%), `InpMaxPositions`=2 |

Trước khi đẩy lên live: backtest tối thiểu 6 tháng `{spec.symbol}` khung
`{spec.timeframe}`, MFE/MAE log, walkforward 3-fold, sau đó canary 30 phút
demo realtime qua `mql5-canary`.
