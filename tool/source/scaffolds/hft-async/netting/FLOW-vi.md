EA `{spec.name}` (scaffold **hft-async / netting**) là **HFT shell**
sử dụng `OrderSendAsync` + reconciler `OnTradeTransaction` (AP-18
compliant — async không có handler là LỖI NGHIÊM TRỌNG). Chạy trên
`{spec.symbol}` khung `{spec.timeframe}`. Tài khoản chế độ **netting**.

Idea: order async không block OnTick → latency tick→order thấp hơn
nhiều so với `OrderSend` đồng bộ. Tradeoff: dev phải tự handle
**reconciliation** (request có thể reject, requote, partial fill,
hoặc never-reply) qua `OnTradeTransaction`.

Có 4 input sinput phụ điều phối backpressure + retry + stale cleanup.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} max.
3. **`async_tm.Init(InpMagic, InpMaxRetries, InpStaleTimeoutSec×10⁶)`**
   — khởi tạo `CAsyncTradeManager`:
   - retry buffer cho từng request bị reject/requote (max
     `InpMaxRetries` lần)
   - stale cleanup timeout (request không có reply trong N giây →
     xoá khỏi pending queue, log warning)
4. `registry.Reserve(InpMagic, "{spec.name}")`.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. async_tm.CleanupStale() │
│ Xoá pending request quá InpStaleTimeoutSec không │
│ có reply (broker im lặng → request lost) │
├─────────────────────────────────────────────────────────┤
│ 3. Risk gate │
│ if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 4. Backpressure check │
│ if async_tm.PendingCount() ≥ InpMaxPendingAsync │
│ → return │
│ (chờ broker confirm bớt trước khi gửi tiếp — tránh │
│ spam request) │
├─────────────────────────────────────────────────────────┤
│ 5. Tick-rate gate │
│ Đếm tick/giây. Nếu ticks_per_sec < InpMinTicksPerSec │
│ → return (book "lạnh", không trade) │
├─────────────────────────────────────────────────────────┤
│ 6. Compute lot │
│ lots = pip.LotForRisk(InpRiskMoney, InpSlPips) │
├─────────────────────────────────────────────────────────┤
│ 7. Signal: tick-by-tick momentum │
│ BUY: ask > prev_ask (lifted) │
│ SELL: bid < prev_bid (pushed) │
├─────────────────────────────────────────────────────────┤
│ 8. Mở lệnh ASYNC │
│ sl_dist = pip.Pips(InpSlPips) │
│ tp_dist = pip.Pips(InpTpPips) │
│ BUY: async_tm.SendBuyAsync(sym, lots, ask-sl, ask+tp│
│ SELL: async_tm.SendSellAsync(sym, lots, bid+sl, ...) │
│ (KHÔNG block — return ngay; broker reply async) │
├─────────────────────────────────────────────────────────┤
│ 9. Update prev_ask / prev_bid cho tick sau │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 2b — OnTradeTransaction (AP-18 MANDATORY)

```
┌─────────────────────────────────────────────────────────┐
│ Broker reply → MqlTradeTransaction event │
│ │ │
│ ▼ │
│ async_tm.OnTransactionResult(trans, request, result) │
│ │ │
│ ▼ │
│ Match request_id → pending queue │
│ ├─ DONE → xoá khỏi pending, log success │
│ ├─ REQUOTE → retry (nếu retry_count < InpMaxRetries) │
│ ├─ REJECT → xoá, log reason │
│ └─ TIMEOUT → đã handle ở CleanupStale() │
└─────────────────────────────────────────────────────────┘
```

KHÔNG có function này → mọi request mất phản hồi sẽ leak forever →
AP-18 fail. Đây là khác biệt CỐT LÕI giữa async EA và sync EA.

---

## Giai đoạn 3 — OnDeinit

1. `async_tm.PrintStats()` — log stats: total sent, success, retry,
   reject, stale. Để dev đánh giá broker quality post-run.

---

## Tính toán phối hợp các input

```
   Tick-rate gate (≥ InpMinTicksPerSec)
              │
              ▼
   Risk gate ─┘
              │
              ▼
   Backpressure (PendingCount < InpMaxPendingAsync)
              │
              ▼
   Signal (tick momentum)
              │
              ▼
   lot = InpRiskMoney ÷ (InpSlPips × pip_value)
              │
              ▼
   OrderSendAsync — magic = InpMagic
              │
              ▼
   OnTradeTransaction reconciler:
     ├─ DONE → done
     ├─ REQUOTE → retry (≤ InpMaxRetries)
     ├─ REJECT → drop + log
     └─ stale (>InpStaleTimeoutSec) → cleanup
```

**Quy tắc tune**:

- `InpRiskMoney` thường nhỏ cho HFT (5-50 USD/lệnh — high frequency,
  small per-trade).
- `InpSlPips` rất hẹp (5-15) — HFT scalp tick-level.
- `InpMinTicksPerSec` filter — broker quiet hours (Asian session,
  Friday close): set 3-5. Liquid hours: 5-10.
- `InpMaxPendingAsync` — backpressure. Quá lớn → broker queue full,
  reject loạt. Quá nhỏ → throttle entry. Default 3-5.
- `InpMaxRetries` — broker requote rate. ECN tốt: 1-2 retry. STP/MM
  thấp: 0 retry (chấp nhận reject).
- `InpStaleTimeoutSec` — timeout request. 5s đủ cho hầu hết broker
  retail; HFT broker thực thụ < 1s.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo M1 EURUSD ECN | `InpRiskMoney`=10, SL=10, TP=15, min_ticks=5, pending=3 |
| Live ECN HFT-grade | `InpRiskMoney`=20-50, SL=8-12, TP=10-15, retries=1, stale=3 |
| Live STP broker | KHÔNG khuyến nghị async — fill rate kém, retry waste |
| Prop-firm HFT | `InpRiskMoney`=10, `InpDailyLossPct`=0.03, retries=0 |

Trước khi đẩy lên live: chạy `mql5-broker-safety` confirm broker
hỗ trợ async (one-trade-per-session check + Equinix latency probe).
Backtest tester KHÔNG mô phỏng async đúng — cần forward-test demo
real time tối thiểu 1 tuần. `async_tm.PrintStats()` để verify
success rate > 95%.
