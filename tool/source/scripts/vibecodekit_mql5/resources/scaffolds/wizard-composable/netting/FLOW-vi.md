EA `{spec.name}` (scaffold **wizard-composable / netting**) là **scaffold
modular tổng hợp**: dev compose strategy bằng cách lắp ghép 3 lớp riêng
biệt — **Signal × Filter × Money** — chạy độc lập trên `{spec.symbol}`
khung `{spec.timeframe}`. Tài khoản chế độ **netting**.

Triết lý: thay vì viết EA monolithic (mọi logic trộn lẫn trong OnTick),
chia 3 thành phần có hợp đồng rõ ràng:

1. **Signal modules** — phát hiện setup (vd MACD cross + SAR confirm).
2. **Filter modules** — kiểm news / spread / session / regime.
3. **Money modules** — sizing (fixed risk, Kelly, volatility-adjusted)
   + exit (fixed SL/TP, trailing, time-based).

Mỗi module là 1 class trong file `.mqh` riêng, EA chỉ orchestrate.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
3. `registry.Reserve(InpMagic, "{spec.name}")` — magic number.
4. **[DEV FILL] Compose modules**:
   - Instantiate `CMyMacdSignal`, `CMyRsiFilter`, `CFixedRiskMoney` ...
   - Inject into orchestrator: `expert.AddSignal(...)`,
     `expert.AddFilter(...)`, `expert.SetMoneyMgr(...)`.
   - Mỗi module có `Init()` riêng — gọi tuần tự, fail bất kỳ →
     `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate (DD/positions/margin) │
├─────────────────────────────────────────────────────────┤
│ 3. Pipeline: Signal → Filter → Money │
│ │
│ a. signal.Compute() → direction ∈ {BUY, SELL, NONE} │
│ (orchestrator chạy tất cả Signal modules; OR │
│ hoặc AND theo composition spec) │
│ │
│ b. for each filter: if !filter.Allow(direction) │
│ → direction = NONE (1 filter veto đủ block) │
│ │
│ c. money.ComputeLot(direction) │
│ → lot, sl_pips, tp_pips │
│ Default: lot = InpRiskMoney ÷ (sl × pip_value) │
├─────────────────────────────────────────────────────────┤
│ 4. Compute SL/TP price │
│ sl = pip.Pips(sl_pips), tp = pip.Pips(tp_pips) │
├─────────────────────────────────────────────────────────┤
│ 5. [DEV FILL] Place order qua CSafeTradeManager │
│ if direction == BUY → trade.Buy(lot, sym, sl, tp) │
│ if direction == SELL → trade.Sell(lot, sym, sl, tp) │
└─────────────────────────────────────────────────────────┘
```

OnTick GỌI tuần tự từng module; tổng thời gian phải < 100ms để không
trễ tick. Nếu module nào cần Python/REST → đẩy sang OnTimer (AP-17).

---

## Giai đoạn 3 — OnDeinit

Mỗi module tự release tài nguyên (indicator handle, file handle...).
Orchestrator gọi `module.Deinit()` tuần tự ngược thứ tự `Init`.

---

## Tính toán phối hợp các input

```
   Signal(s) ──┐
               │ (compose AND/OR theo spec)
               ▼
        direction ∈ {BUY, SELL, NONE}
               │
               ▼
   Filter(s) ──┤ if any Allow=false → NONE
               │
               ▼
   Money mgr ──┤ lot, sl_pips, tp_pips
               │ (default: fixed-risk theo InpRiskMoney)
               ▼
   Risk gate ──┤ DD/positions/margin
               │
               ▼
   Order qua CSafeTradeManager
   magic = InpMagic
```

**Quy tắc tune**:

- Mỗi module dùng `InpRiskMoney` / `InpSlPips` / `InpTpPips` làm default,
  nhưng có thể override per-module. Vd dev tạo `CKellyMoney` ignore
  `InpRiskMoney` mà tính lại theo win-rate.
- Wizard scaffold tránh AP-5 (≤6 optimizable input) bằng cách push
  module params sang `sinput`. Chỉ `InpRiskMoney`, `InpSlPips`,
  `InpTpPips` còn lại để optimizer sweep.
- Add/remove module = 1 dòng code trong OnInit; không sửa OnTick.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo wizard test | `InpRiskMoney`=10, 1 signal + 1 filter + fixed money |
| Live multi-strategy | `InpRiskMoney`=20-50, 2-3 signal compose AND, 1-2 filter |
| Prop-firm composite | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, AND-compose conservative |

Trước khi đẩy lên live: test mỗi module ĐỘC LẬP trong scaffold riêng
trước (vd `mql5-build stdlib/netting --signal-only`), backtest tổ hợp
trong wizard sau, walkforward 3-fold để chắc không over-fit vào combo.
