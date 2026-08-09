EA `{spec.name}` (scaffold **grid / hedging**) là **grid trader** với
step pip-normalized + max-step cap (AP-4 aware) trên `{spec.symbol}`
khung `{spec.timeframe}`. Tài khoản chế độ **hedging** (mỗi grid level
là 1 ticket riêng).

Idea: đặt lệnh ở các mức giá cách đều (vd mỗi 20 pip) — khi giá đi
qua level → thêm leg mới. Profit từ small reversals; nhược: nếu giá
breakout mạnh 1 chiều → grid expand vô hạn (martingale spiral) → AP-4
detector flag.

**Quan trọng**: scaffold khung skeleton — dev điền:
1. Grid direction (bilateral / one-side).
2. Grid step size (sinput).
3. Max-step cap (AP-4 mandatory).
4. Basket exit (cumulative TP HOẶC time-based).

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, **{InpMaxPositions} = grid
   max-step cap** (AP-4: tránh martingale unlimited).
3. `registry.Reserve(InpMagic, "{spec.name}")`.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate (DD + position count) │
│ if open_positions ≥ InpMaxPositions → return │
│ (AP-4 mandatory cap — không cho grid expand vô hạn) │
├─────────────────────────────────────────────────────────┤
│ 3. [DEV FILL] Compute grid levels │
│ step = pip.Pips(InpGridStepPips) (sinput) │
│ last_entry = giá entry của ticket gần nhất │
│ next_buy_level = last_entry - step │
│ next_sell_level = last_entry + step │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Check trigger │
│ if bid < next_buy_level → mở BUY (long ladder) │
│ if ask > next_sell_level → mở SELL (short ladder) │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot per leg │
│ lot = pip.LotForRisk( │
│ InpRiskMoney / InpMaxPositions, │
│ InpSlPips) │
│ (chia equal risk qua N leg) │
├─────────────────────────────────────────────────────────┤
│ 6. Mở 1 leg mới │
│ SL = entry ∓ pip.Pips(InpSlPips) │
│ TP = entry ± pip.Pips(InpTpPips) │
│ HOẶC no-TP — chốt basket cộng dồn │
├─────────────────────────────────────────────────────────┤
│ 7. [DEV FILL] Basket TP check │
│ sum_profit = Σ profit(positions cùng magic) │
│ if sum_profit > InpBasketTpUsd → close all │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 3 — OnDeinit

Trống. KHÔNG đóng grid khi remove EA — dev quyết định manual hoặc
external supervisor.

---

## Tính toán phối hợp các input

```
   InpGridStepPips ──► step = pip × step_pips
                            │
                            ▼
   Khi giá vượt level → mở leg mới (cùng magic)
                            │
                            ▼ basket grows ...
   if leg_count ≥ InpMaxPositions → STOP (AP-4 hard cap)
                            │
                            ▼
   Basket exit:
     cumulative_profit > target → close all
     OR time-based exit (vd Friday close)
```

**Quy tắc tune**:

- `InpGridStepPips` quan trọng nhất. Quá nhỏ (5-10) → grid fill nhanh,
  margin cạn nhanh. Quá lớn (50-100) → ít leg, ít smooth.
- `InpMaxPositions` là **HARD CAP** AP-4 — tuyệt đối không bỏ qua.
  Default 3-10; >20 dễ blow account khi market trend mạnh.
- `InpRiskMoney` chia equal qua N leg → tổng risk khi grid full =
  `InpRiskMoney`. Nếu KHÔNG chia → risk tích lại × N.
- Grid hiệu quả ở ranging market. Trong trending market mạnh →
  one-side leg accumulate, DD lớn. Cân nhắc filter regime (ADX <
  25) hoặc giới hạn session.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo EURUSD ranging | `InpRiskMoney`=50, step=20, max_pos=5 |
| Live small grid bilateral | `InpRiskMoney`=100, step=30, max_pos=10 |
| Live one-side trend grid | `InpRiskMoney`=100, step=50, max_pos=5 (giảm cap) |
| Prop-firm grid | KHÔNG khuyến nghị — grid vi phạm DD rule khi trend |

Trước khi đẩy lên live: backtest qua nhiều regime, đặc biệt
flash-crash (vd SNB CHF 2015, COVID 2020) — grid có thể blow trong
1 ngày. Verify `InpMaxPositions` cap kích trước khi vi phạm DD rule.
Grid là chiến lược **rủi ro cao** — phải có exit kỷ luật + margin
buffer ≥ 50%.
