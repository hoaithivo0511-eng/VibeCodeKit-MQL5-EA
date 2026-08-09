EA `{spec.name}` (scaffold **dca / hedging**) là **dollar-cost
averaging** (DCA) với entry theo thời gian + drawdown freeze, trên
`{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ **hedging**
(nhiều ticket nhỏ cùng chiều, mỗi ticket có giá entry riêng để average
xuống/lên).

Idea: thay vì mở 1 lệnh lớn, mở nhiều lệnh nhỏ ở các mốc thời gian cố
định (vd mỗi 24h hoặc mỗi 4h). Lợi thế: smooth drawdown qua average
price; nhược: cần `risk.FreezeOnDD` để dừng accumulate khi equity rơi.

**Lưu ý quan trọng**: scaffold dừng ở khung skeleton — dev điền:
1. Lịch entry (timer-based, bar-based, hoặc drawdown-triggered).
2. Logic chốt lời (TP cố định per lệnh HOẶC TP-on-basket).
3. Stop accumulate khi `risk.FreezeOnDD()` trigger.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, **{InpMaxPositions} lệnh tối đa
   trong basket DCA** (mỗi entry là 1 ticket).
3. `registry.Reserve(InpMagic, "{spec.name}")`.
4. **[DEV FILL]** `EventSetTimer(N)` với N = interval entry (vd
   `86400` = 24h, `14400` = 4h).

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTimer (chính, KHÔNG dùng OnTick để mở lệnh)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() (refresh equity tracker) │
├─────────────────────────────────────────────────────────┤
│ 2. Drawdown freeze check │
│ if risk.IsFrozenOnDD() → return │
│ (equity drop > InpDailyLossPct → skip entry mới) │
├─────────────────────────────────────────────────────────┤
│ 3. Max-position cap │
│ if open_positions ≥ InpMaxPositions → return │
│ (cap số leg DCA — tránh accumulate vô hạn) │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Direction logic │
│ DCA luôn 1 chiều cố định (vd LONG-only XAUUSD) │
│ HOẶC follow trend filter (vd EMA200 slope) │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot per leg │
│ lot = pip.LotForRisk(InpRiskMoney / InpMaxPositions, │
│ InpSlPips) │
│ (chia equal risk qua N leg — tổng risk = InpRiskMoney│
│ khi đủ basket) │
├─────────────────────────────────────────────────────────┤
│ 6. Mở 1 ticket DCA mới │
│ SL = entry ∓ pip.Pips(InpSlPips) │
│ TP = entry ± pip.Pips(InpTpPips) (hoặc no-TP cho │
│ basket-close) │
└─────────────────────────────────────────────────────────┘
```

OnTick có thể dùng để **check basket TP**: nếu tổng profit > target
→ đóng toàn bộ basket cùng lúc.

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()`.
2. KHÔNG đóng lệnh khi remove EA — basket có thể vẫn open, dev quyết
   định manual hoặc dùng external supervisor.

---

## Tính toán phối hợp các input

```
   Timer interval (N giây)
            │
            ▼
   Every N → check freeze + cap
            │
            ▼ pass
   lot per leg = InpRiskMoney/InpMaxPositions ÷ (SL × pip_value)
            │
            ▼
   Mở 1 leg mới — magic = InpMagic
            │
            ▼ basket grows ...
   Basket TP check (OnTick optional)
            │
            ▼ profit > target
   Close all (cùng magic)
```

**Quy tắc tune**:

- `InpRiskMoney` chia EQUAL qua `InpMaxPositions` leg → tổng risk
  basket khi full = `InpRiskMoney`. Nếu KHÔNG chia → mỗi leg risk
  `InpRiskMoney` → basket full risk `N × InpRiskMoney` (nguy hiểm).
- Interval timer quá ngắn (vd 1h) → basket fill nhanh, dễ over-expose.
  Quá dài (24h+) → ít leg, ít smooth.
- DCA hiệu quả ở market mean-reverting hoặc bull-trend dài hạn (vd
  XAUUSD multi-year). Trong downtrend kéo dài → DD lớn, freeze
  kích sớm.
- `InpMaxPositions` = số leg basket. Hedging account đếm tất cả ticket
  có magic này — cần đặt đủ lớn để chứa basket dự kiến.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo XAUUSD 24h DCA | `InpRiskMoney`=50, `InpMaxPositions`=10, timer=86400 |
| Live small DCA bull | `InpRiskMoney`=100, `InpMaxPositions`=20, timer=14400 |
| Live aggressive DCA | `InpRiskMoney`=200, `InpMaxPositions`=30, timer=3600 |
| Prop-firm DCA (rủi ro!) | KHÔNG khuyến nghị — DCA vi phạm DD rule khi market downtrend kéo dài |

Trước khi đẩy lên live: backtest qua nhiều regime (bull/bear/range
mỗi 2 năm), simulate DD worst-case, verify `risk.FreezeOnDD` kích
trước khi vi phạm prop-firm DD rule. DCA là chiến lược dễ blow account
nhất nếu không có exit kỷ luật.
