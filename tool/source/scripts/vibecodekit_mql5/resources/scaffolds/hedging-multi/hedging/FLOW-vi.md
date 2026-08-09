EA `{spec.name}` (scaffold **hedging-multi / hedging**) là **multi-position
hedging** với paired BUY/SELL trên cùng signal, chạy trên `{spec.symbol}`
khung `{spec.timeframe}`. Tài khoản chế độ **hedging** (bắt buộc — không
chạy trên netting).

Idea: thay vì chọn 1 chiều, mở ĐỒNG THỜI Buy + Sell với SL/TP đối
xứng. Cấu trúc thường dùng cho:
1. **Straddle pre-news**: ăn breakout chiều nào cũng được.
2. **Lock-in equity**: giữ position rồi mở leg ngược để khoá P/L
   trong khi chờ confirmation.
3. **Pair hedge multi-instrument** (nhưng vẫn cùng EA instance).

**Quan trọng**: scaffold khung skeleton — dev điền:
1. Signal trigger (vd impending news, gap detect, multi-TF align).
2. Logic close 1 chiều khi confirm (hedge unwind).
3. Risk distribution giữa 2 leg.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, **{InpMaxPositions} đếm CẢ Buy
   + Sell** (cần ≥ 2 để cho phép 1 cặp hedge).
3. `registry.Reserve(InpMagic, "{spec.name}")`.
4. **Verify account is HEDGING**: kit doctor check
   `ACCOUNT_MARGIN_MODE == HEDGING`. Nếu netting → EA fail open lệnh
   thứ 2.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
│ (cần ≥ 2 slot free — mở cả Buy + Sell) │
├─────────────────────────────────────────────────────────┤
│ 3. [DEV FILL] Hedge trigger signal │
│ Vd: news event đến gần (NFP, FOMC) → mở straddle │
│ Hoặc: gap detect (open ≠ prev_close + threshold) │
│ Hoặc: HOLD-and-hedge: giá đi ngược 1 leg → mở leg │
│ ngược lock equity │
├─────────────────────────────────────────────────────────┤
│ 4. Compute lot per leg │
│ lot = pip.LotForRisk(InpRiskMoney/2, InpSlPips) │
│ (chia equal qua 2 leg — tổng risk = InpRiskMoney) │
├─────────────────────────────────────────────────────────┤
│ 5. Mở ĐỒNG THỜI 2 lệnh │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
│ BUY: trade.Buy(lot, sym, ask-sl_dist, ask+tp_dist) │
│ SELL: trade.Sell(lot, sym, bid+sl_dist, bid-tp_dist) │
├─────────────────────────────────────────────────────────┤
│ 6. [DEV FILL] Unwind logic │
│ Khi 1 leg hit TP → close leg ngược (hedge complete) │
│ HOẶC trail stop leg thắng + giữ leg thua │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 3 — OnDeinit

Trống. KHÔNG đóng leg khi remove EA — dev quyết định manual.

---

## Tính toán phối hợp các input

```
   Signal trigger ──► mở Buy + Sell đồng thời
                           │
                           ▼
   Risk gate (≥ 2 slot free + DD ok)
                           │
                           ▼
   lot per leg = (InpRiskMoney/2) ÷ (InpSlPips × pip_value)
                           │
                           ▼
   Hedge open: 2 ticket riêng, cùng magic, SL/TP đối xứng
                           │
                           ▼
   Breakout 1 chiều → leg thắng hit TP
                           │
                           ▼
   [DEV] unwind leg thua (close manual or auto)
```

**Quy tắc tune**:

- `InpRiskMoney` PHẢI chia /2 qua 2 leg — nếu KHÔNG → mỗi leg risk
  `InpRiskMoney` → tổng risk basket 2× (lệch khỏi spec).
- `InpSlPips` đối xứng cho cả 2 leg. SL hẹp (10-20) phù hợp news
  straddle (breakout nhanh). SL rộng (50-100) phù hợp lock-in hedge.
- `InpTpPips` thường ≥ 2× SL — straddle cần leg thắng phủ leg thua
  + commission + spread × 2.
- `InpMaxPositions` ≥ 2 (1 cặp hedge) hoặc ≥ 4 (2 cặp multi-pair).

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo news straddle | `InpRiskMoney`=20, SL=15, TP=40, `InpMaxPositions`=2 |
| Live news EURUSD | `InpRiskMoney`=30-50, SL=20-25, TP=50-80, `InpMaxPositions`=2 |
| Live gap hedge XAUUSD | `InpRiskMoney`=50, SL=30, TP=80, `InpMaxPositions`=2 |
| Prop-firm hedge | `InpRiskMoney`=20, `InpDailyLossPct`=0.04, SL=20, TP=50 |

Trước khi đẩy lên live: backtest qua nhiều news event (NFP, FOMC,
CPI), kiểm spread widening tại moment news (broker có thể tăng spread
× 10 → fill 1 leg fail, hedge bị unbalanced). Verify
`mql5-broker-safety` confirm hedging mode + symbol có hỗ trợ 2 side.
