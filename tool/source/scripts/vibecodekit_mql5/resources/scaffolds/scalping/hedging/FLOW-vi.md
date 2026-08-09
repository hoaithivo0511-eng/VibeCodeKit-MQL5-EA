EA `{spec.name}` (scaffold **scalping / hedging**) là **M1/M5 scalper**
với 3 lớp filter: **spread guard** + **ATR momentum** + **same-bar
guard** trên `{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế
độ **hedging**.

Idea: scalping cần edge mỏng → mọi cost (spread, slippage, requote)
ăn vào win-rate. EA bypass entry khi spread cao bất thường HOẶC ATR
quá nhỏ (no momentum → SL gần ăn liền).

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `history.EnsureBars(_Symbol, _Period, 300)` — đảm bảo data ATR.
3. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
4. `registry.Reserve(InpMagic, "{spec.name}")`.
5. `trade.Init((ulong)InpMagic)`.
6. **`h_atr = iATR(_Symbol, _Period, InpAtrPeriod)`** — ATR handle để
   đo momentum.

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
│ 3. Spread guard │
│ spread_points = SymbolInfoInteger(SYMBOL_SPREAD) │
│ if spread > InpMaxSpreadPoints → return │
│ (broker widening spread quanh news/rollover → skip) │
├─────────────────────────────────────────────────────────┤
│ 4. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 5. ATR momentum filter │
│ CopyBuffer(h_atr, 0, 0, 1, atr) │
│ if atr / point < InpAtrMinPoints → return │
│ (range nhỏ → SL gần dễ ăn, skip) │
├─────────────────────────────────────────────────────────┤
│ 6. Compute lot │
│ lots = pip.LotForRisk(InpRiskMoney, InpSlPips) │
├─────────────────────────────────────────────────────────┤
│ 7. Check signal (bar vừa đóng) │
│ open1 = iOpen(_Symbol, _Period, 1) │
│ close1 = iClose(_Symbol, _Period, 1) │
│ BUY: close1 > open1 (nến xanh) │
│ SELL: close1 < open1 (nến đỏ) │
├─────────────────────────────────────────────────────────┤
│ 8. Mở lệnh │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
│ BUY: trade.Buy(lots, sym, ask - sl_dist, ask + tp) │
│ SELL: trade.Sell(lots, sym, bid + sl_dist, bid - tp) │
└─────────────────────────────────────────────────────────┘
```

Signal đơn giản (nến vừa đóng = green/red) chỉ là placeholder — dev
nên replace bằng edge có expectancy positive sau khi trừ
spread+commission (xem `mql5-mfe-mae` để đo cost reality).

---

## Giai đoạn 3 — OnDeinit

1. `IndicatorRelease(h_atr)` — trả handle.

---

## Tính toán phối hợp các input

```
   InpMaxSpreadPoints ──► spread guard
                              │
   InpAtrPeriod ──► ATR ──► momentum filter
                              │
                              ▼
                       Signal (open vs close)
                              │
                              ▼
                       Risk gate
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

- `InpMaxSpreadPoints` rất broker-specific. EURUSD ECN: 5-10 points.
  EURUSD STP: 15-25. XAUUSD: 30-50. Kiểm thực tế qua
  `mql5-broker-safety` trước khi set.
- `InpSlPips` cho scalp thường 5-15 (ngắn). `InpTpPips` 5-20. RR ratio
  scalp thường 1:1 hoặc 1:1.5 (không cần 1:2 như swing).
- `InpAtrMinPoints` filter no-momentum: 20-50 EURUSD M1, 50-150 XAUUSD
  M1. Quá nhỏ → trade trong range chết. Quá lớn → bỏ lỡ setup.
- Scalping HFT-style → cân nhắc move sang `hft-async/netting` để
  dùng OrderSendAsync (latency thấp hơn).

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo M1 EURUSD scalp | `InpRiskMoney`=5, SL=10, TP=15, spread=20, ATR(14)>30 |
| Live M1 ECN broker | `InpRiskMoney`=10-20, SL=8-12, TP=10-18, spread=10 |
| Live M5 swing-scalp | `InpRiskMoney`=15-30, SL=15-25, TP=20-40, spread=20 |
| Prop-firm scalp | `InpRiskMoney`=5-10, `InpDailyLossPct`=0.03, SL=10, spread=12 |

Trước khi đẩy lên live: backtest với spread mô phỏng thực
(`mql5-mfe-mae` log slippage), kiểm session đặc thù (Asian session
thường spread cao + range nhỏ → scalper FAIL), walkforward 3-fold.
Scalp thường có expectancy mỏng → 1 lỗi setup có thể ăn nhiều ngày
profit.
