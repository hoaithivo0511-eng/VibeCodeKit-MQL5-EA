EA `{spec.name}` (scaffold **breakout / netting**) dùng tín hiệu **Donchian
breakout** (giá phá highest/lowest của N nến gần nhất) trên
`{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ **netting**
(1 net position per symbol).

Idea: thị trường có xu hướng tiếp tục breakout của range gần nhất. Long
khi close của nến vừa đóng > highest của N nến trước; Short khi <
lowest. Same-bar guard ngăn re-entry trong cùng 1 nến.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo ≥ 300 nến để
   tính `iHighest` / `iLowest` cửa sổ rộng.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
4. `registry.Reserve(InpMagic, "{spec.name}")`.
5. `trade.Init((ulong)InpMagic)` — CSafeTradeManager.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Same-bar guard │
│ if bars == last_bar → return │
│ (chỉ xử lý 1 lần / nến mới — tránh re-trigger │
│ trong cùng nến) │
├─────────────────────────────────────────────────────────┤
│ 3. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 4. Lấy Donchian channel của N nến đã đóng │
│ hh_idx = iHighest(_Symbol, _Period, MODE_HIGH, │
│ InpLookbackBars, 1) │
│ ll_idx = iLowest (_Symbol, _Period, MODE_LOW, │
│ InpLookbackBars, 1) │
│ hh = iHigh(hh_idx), ll = iLow(ll_idx) │
│ close = iClose(bar=1) (nến vừa đóng) │
│ (start_index=1 → KHÔNG bao gồm nến đang chạy) │
├─────────────────────────────────────────────────────────┤
│ 5. Compute lot │
│ lots = pip.LotForRisk(InpRiskMoney, InpSlPips) │
├─────────────────────────────────────────────────────────┤
│ 6. Compute SL/TP │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
├─────────────────────────────────────────────────────────┤
│ 7. Check signal │
│ BUY: close > hh (breakout lên) │
│ SELL: close < ll (breakout xuống) │
├─────────────────────────────────────────────────────────┤
│ 8. Mở lệnh │
│ BUY: trade.Buy(lots, sym, ask - sl_dist, │
│ ask + tp_dist) │
│ SELL: trade.Sell(lots, sym, bid + sl_dist, │
│ bid - tp_dist) │
└─────────────────────────────────────────────────────────┘
```

`IsBuySignal()` / `IsSellSignal()` là hook để dev replace edge — vd
thêm volume filter, ATR confirm, multi-timeframe align.

---

## Giai đoạn 3 — OnDeinit

Trống. Không có indicator handle (iHighest/iLowest là stateless query).

---

## Tính toán phối hợp các input

```
   InpLookbackBars
        │
        ▼
   Donchian channel ──► hh, ll
        │
        ▼
   close_just_closed > hh → BUY
   close_just_closed < ll → SELL
        │
        ▼
   Risk gate ──┐
        │ │
        ▼ │
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
        │
        ▼
   SL = entry ∓ InpSlPips pip
   TP = entry ± InpTpPips pip
   magic = InpMagic
```

**Quy tắc tune**:

- `InpLookbackBars` nhỏ (10-20) → breakout sớm, nhiều fake-out. Lớn
  (50-100) → breakout chậm, ít signal nhưng chất lượng cao hơn.
- `InpTpPips` nên ≥ 1.5× `InpSlPips` để Risk:Reward ≥ 1:1.5 — breakout
  thường có momentum tail dài.
- `InpLookbackBars` khai báo `sinput` → Strategy Tester optimizer
  KHÔNG sweep. Đổi sang `input` thủ công nếu muốn optimize.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo paper-trading H1 | `InpRiskMoney`=10, `InpLookbackBars`=20, SL=30, TP=60 |
| Live H1 EURUSD | `InpRiskMoney`=20-50, `InpLookbackBars`=20-30, SL=30, TP=60-90 |
| Live H4 trend follower | `InpRiskMoney`=30-100, `InpLookbackBars`=50, SL=50, TP=150 |
| Prop-firm breakout | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, `InpLookbackBars`=30 |

Trước khi đẩy lên live: backtest min 6 tháng, kiểm fake-breakout rate
qua MFE/MAE log, walkforward 3-fold để chắc breakout edge bền qua
regime change.
