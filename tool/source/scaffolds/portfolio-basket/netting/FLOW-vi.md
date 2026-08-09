EA `{spec.name}` (scaffold **portfolio-basket / netting**) là **starter scaffold** cho chiến lược portfolio-basket trên tài
khoản **netting** (1 chiều cùng symbol). Khác với `trend/netting`, scaffold
này **CỐ Ý CHƯA** chứa code mở lệnh — phần signal compute + OrderSend
được dev fill in theo strategy cụ thể (basket arbitrage, statistical arb,
factor portfolio, ...).

Vai trò của scaffold là cung cấp:

- Risk infrastructure (CRiskGuard + daily-loss + max-positions cap)
- Pip-math cross-broker (CPipNormalizer)
- Magic registry chuẩn (CMagicRegistry)
- Lot sizing helper (LotForRisk)

Dev viết `OnTick` body để: (a) compute basket signal, (b) đặt entry/exit
cho mỗi leg.

---

## Giai đoạn 1 — OnInit (chạy 1 lần khi attach EA lên chart)

1. **Init pip normalizer**
   - `pip.Init(_Symbol)` — symbol gốc gắn EA (vd `{spec.symbol}`).
   - Lưu ý: portfolio-basket thường trade nhiều symbol, dev có thể cần khởi
     tạo thêm `CPipNormalizer` riêng cho mỗi symbol trong basket.
2. **Init risk guard**
   - `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)`
   - Cap {InpMaxPositions} lệnh đồng thời (đếm tổng basket, không phải
     từng symbol).
   - DD threshold {spec.risk.daily_loss_pct:pct} áp dụng cho TỔNG account
     equity (không phải mỗi leg).
3. **Reserve magic number**
   - `registry.Reserve(InpMagic, "{spec.name}")` — `InpMagic` là magic CHUNG
     cho toàn bộ basket. Một số dev tách `InpMagic`, `InpMagic+1`, ...
     cho từng leg để dễ filter trong history.

---

## Giai đoạn 2 — OnTick (chạy mỗi tick)

Skeleton mặc định của scaffold:

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
│ Cập nhật equity tracker │
├─────────────────────────────────────────────────────────┤
│ 2. Gate check │
│ if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 3. Compute lot │
│ sl = pip.Pips(InpSlPips) │
│ lot = pip.LotForRisk(InpRiskMoney, InpSlPips) │
│ if lot ≤ 0 → log + return │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Compute basket signal │
│ - basket score (factor / spread / correlation) │
│ - per-leg direction (Buy / Sell / Flat) │
├─────────────────────────────────────────────────────────┤
│ 5. [DEV FILL] Place orders │
│ For each leg: │
│ trade.Buy(lot_leg, leg_symbol, sl_leg, tp_leg) │
│ hoặc trade.Sell(...) │
│ Dùng cùng InpMagic để tracking nhất quán. │
└─────────────────────────────────────────────────────────┘
```

**Bước 4 + 5 dev tự viết** — scaffold không impose strategy.

---

## Patterns thường gặp khi dev fill in

### Pattern A — Equal-weight basket

```
for symbol in basket_list:
    lot = pip.LotForRisk(InpRiskMoney / N, InpSlPips)
    if signal[symbol] == BUY:
        trade.Buy(lot, symbol, ...)
```

- Chia `InpRiskMoney` đều cho N leg → tổng USD risk vẫn = `InpRiskMoney`.
- Phù hợp khi basket có correlation thấp.

### Pattern B — Spread trade (2-leg long/short)

```
spread = price_A - hedge_ratio × price_B
if spread > +threshold: trade.Sell(A); trade.Buy(B × hedge_ratio)
if spread < -threshold: trade.Buy(A); trade.Sell(B × hedge_ratio)
```

- 2 leg ngược chiều, lot theo hedge ratio.
- `InpMaxPositions` cần ≥ 2 cho mỗi entry.

### Pattern C — Factor portfolio (rank-based)

```
ranked = sort_by_factor(basket_list)
go_long(top_k); go_short(bottom_k); flat(middle)
```

- Tổng số lệnh = 2k cùng lúc → đặt `InpMaxPositions` ≥ 2k.

---

## Tính toán phối hợp các input

```
┌──────────────────────────────────────────────────────────┐
│ Risk budget │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Tổng USD risk = InpRiskMoney │ │
│ │ Chia cho N leg: per_leg = InpRiskMoney / N │ │
│ └────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Position count gate │
│ ┌────────────────────────────────────────────────────┐ │
│ │ N_active_legs ≤ InpMaxPositions │ │
│ │ (đặt = N_legs cho basket cố định) │ │
│ └────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Per-leg sizing │
│ ┌────────────────────────────────────────────────────┐ │
│ │ lot_leg = per_leg ÷ (InpSlPips × pip_value_leg) │ │
│ └────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ Drawdown circuit-breaker │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Tổng PnL basket / equity ≤ -InpDailyLossPct │ │
│ │ → CRiskGuard chặn mở leg mới │ │
│ └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Quy tắc tune cho basket:**

- `InpMaxPositions` PHẢI ≥ số leg cố định của basket; nếu basket size động,
  đặt ≥ peak expected.
- `InpRiskMoney` là TỔNG, không per-leg. Đừng nhân với N leg ở đây.
- Khi đổi `InpSlPips`, mỗi leg đều dùng cùng giá trị (trừ khi dev override
  per-leg).

---

## Setup khuyến nghị

| Loại basket | Tham số đề xuất |
|---|---|
| Currency pairs G10 (8 leg) | `InpRiskMoney`=80 USD, `InpMaxPositions`=8, `InpSlPips`=40 |
| Spread 2-leg (EURUSD/GBPUSD) | `InpRiskMoney`=20, `InpMaxPositions`=2, `InpSlPips`=30 |
| Factor top 3 / bottom 3 | `InpRiskMoney`=60, `InpMaxPositions`=6, `InpSlPips`=50 |

Lưu ý: scaffold này chưa có order placement → backtest sẽ KHÔNG có lệnh
nào (chỉ thấy "lot=0 reason=..." trong log). Hoàn thiện bước 4 + 5 trước
khi backtest.

Sau khi dev fill in code: chạy `mql5-lint {spec.name}.mq5` (clear AP-1/2/3/5/17)
+ `mql5-compile` + canary 30 phút.
