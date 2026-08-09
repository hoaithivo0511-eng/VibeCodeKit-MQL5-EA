EA `{spec.name}` (scaffold **news-trading / netting**) là **news-driven
straddle**: đặt **pending stop orders** (buy stop trên + sell stop
dưới) trước khi release tin kinh tế quan trọng (NFP, FOMC, CPI…). Chạy
trên `{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ
**netting**.

Idea: tin quan trọng làm giá nhảy mạnh 1 chiều → buy stop / sell stop
sẽ trigger chiều breakout, chiều ngược bị cancel hoặc hit SL ngắn.

**Lưu ý**: scaffold khung skeleton — dev điền:
1. Hook Calendar API (`CalendarValueLast`, `CalendarValueHistory`)
   trong **OnTimer** (the kit spec §17 — KHÔNG OnTick).
2. Filter event theo importance + currency.
3. Logic place/cancel pending order quanh release time.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} = 2
   (1 buy stop + 1 sell stop pending).
3. `registry.Reserve(InpMagic, "{spec.name}")`.
4. **[DEV FILL]** `EventSetTimer(60)` — poll Calendar mỗi 60 giây.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTimer (chính, mỗi 60s)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() (token refresh equity tracker) │
├─────────────────────────────────────────────────────────┤
│ 2. [DEV FILL] Calendar API query │
│ MqlCalendarValue values[]; │
│ int n = CalendarValueHistory(values, │
│ TimeCurrent(), │
│ TimeCurrent() + 3600, // next 1h │
│ NULL, NULL); │
├─────────────────────────────────────────────────────────┤
│ 3. [DEV FILL] Filter event │
│ For each value: │
│ - importance == HIGH │
│ - country in ["USD", "EUR", ...] (match symbol) │
│ - time_until_release < InpPreReleaseSec (vd 60s) │
│ → trigger straddle setup │
├─────────────────────────────────────────────────────────┤
│ 4. Place pending straddle │
│ ask = SymbolInfoDouble(SYMBOL_ASK) │
│ bid = SymbolInfoDouble(SYMBOL_BID) │
│ stop_dist = pip.Pips(InpStopOffsetPips) (vd 10 pip) │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
│ lot = pip.LotForRisk(InpRiskMoney/2,InpSlPips) │
│ │
│ PlaceBuyStop( ask + stop_dist, sl=…-sl_dist, │
│ tp=…+tp_dist, lot) │
│ PlaceSellStop(bid - stop_dist, sl=…+sl_dist, │
│ tp=…-tp_dist, lot) │
├─────────────────────────────────────────────────────────┤
│ 5. [DEV FILL] Cancel logic │
│ Sau release (time_after_release > InpPostReleaseSec):│
│ - Pending nào còn untriggered → DELETE │
│ - Pending nào đã trigger → giữ + monitor SL/TP │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 2b — OnTick

OnTick chỉ dùng để **monitor position đã trigger** (vd trail stop,
break-even move). KHÔNG đặt pending order ở OnTick (AP-17 — Calendar
API nhanh nhưng đặt ở OnTimer để consistent).

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()`.
2. KHÔNG cancel pending khi remove EA — dev manual hoặc external.

---

## Tính toán phối hợp các input

```
   Calendar event filter (importance + currency)
              │
              ▼
   time_until_release < InpPreReleaseSec
              │
              ▼
   Risk gate (≥ 2 slot free)
              │
              ▼
   lot per leg = (InpRiskMoney/2) ÷ (InpSlPips × pip_value)
              │
              ▼
   PlaceBuyStop @ ask + InpStopOffsetPips
   PlaceSellStop @ bid - InpStopOffsetPips
   SL: ±InpSlPips, TP: ±InpTpPips, magic = InpMagic
              │
              ▼ news release
   1 leg trigger → giữ + chạy SL/TP
   1 leg untriggered → cancel sau InpPostReleaseSec
```

**Quy tắc tune**:

- `InpStopOffsetPips` (10-20 pip thông thường) — khoảng cách stop từ
  giá hiện tại. Quá gần (< 5) → trigger sớm bởi noise. Quá xa
  (> 50) → news không jump đủ để trigger.
- `InpSlPips` thường = `InpStopOffsetPips × 0.5-1` — SL ngắn vì
  breakout phải nhanh, nếu lùi về thì là fake-out.
- `InpTpPips` ≥ 2× SL — straddle cần leg thắng phủ leg thua + spread
  widen during news.
- `InpRiskMoney` chia /2 qua 2 leg → tổng = InpRiskMoney khi cả 2
  trigger (hiếm — thường 1 leg cancel).
- Spread widening trong news có thể × 10 → broker ECN khuyến nghị.
  MM broker thường widen + reject → straddle FAIL.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo NFP/FOMC | `InpRiskMoney`=20, offset=15, SL=10, TP=30, pre=60s |
| Live ECN news EURUSD | `InpRiskMoney`=30-50, offset=10-15, SL=10, TP=25-40 |
| Live XAUUSD CPI | `InpRiskMoney`=50-100, offset=30-50, SL=20, TP=80-150 |
| Prop-firm news | `InpRiskMoney`=10, DD=0.03, offset=15, SL=10, TP=30 |

Trước khi đẩy lên live:
1. **Kiểm broker policy news trading** — nhiều prop-firm + MM broker
   CẤM trade trong window N phút quanh tin (rule violation → close
   challenge). Đọc Terms of Service.
2. Backtest qua nhiều event lịch sử (Calendar history reliable từ
   ~2017). Verify entry slippage không quá lớn.
3. **Spread protection**: trước khi place pending, check
   `SymbolInfoInteger(SYMBOL_SPREAD)` — nếu spread bất thường →
   skip event này.
4. Canary trên live demo cho 1-2 event nhỏ trước khi tham gia NFP/CPI.
