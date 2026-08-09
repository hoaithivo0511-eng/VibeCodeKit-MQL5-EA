EA `{spec.name}` (scaffold **service / standalone**) là **MQL5 Service
program** (`#property service`, MT5 build ≥ 5320) — long-running
background task có thread riêng, KHÔNG chart, KHÔNG OnTick. Đây
**không phải Expert Advisor** truyền thống mà là **service binary**
độc lập.

Symbol `{spec.symbol}` chỉ là **data anchor** (cho REST request / data
poll khi cần); service không chạy theo tick của 1 chart cụ thể.
Timeframe `{spec.timeframe}` cũng chỉ là anchor.

Khi nào dùng Service thay vì EA:
- **Data collection across multi-symbol** — polling chartless.
- **LLM/REST polling** mà KHÔNG được block OnTick chart nào (AP-17).
- **Telegram / Slack notification daemon**.
- **VPS canary / health-check beacon**.

---

## Giai đoạn 1 — OnStart (chạy 1 lần khi service kích hoạt)

```
┌─────────────────────────────────────────────────────────┐
│ PrintFormat("[%s] service starting, poll=%d ms", │
│ InpServiceTag, InpPollIntervalMs); │
│ │
│ while(!IsStopped()) │
│ { │
│ DoOneCycle(); │
│ Sleep(InpPollIntervalMs); │
│ } │
│ │
│ PrintFormat("[%s] service stopping cleanly", tag); │
└─────────────────────────────────────────────────────────┘
```

`IsStopped()` flip về `true` khi user gọi `ServiceShutdown()` hoặc
khi terminal close — mỗi iteration loop PHẢI check trước
`Sleep`. Đây là khác biệt cốt lõi vs EA (EA dùng OnTick callback,
không có infinite loop của riêng).

Service KHÔNG có OnInit/OnDeinit theo nghĩa EA — toàn bộ lifecycle
nằm trong OnStart.

---

## Giai đoạn 2 — DoOneCycle (work unit, mỗi `InpPollIntervalMs` ms)

```
┌─────────────────────────────────────────────────────────┐
│ PrintFormat("[%s] heartbeat @ %s", tag, │
│ TimeToString(TimeCurrent(), │
│ TIME_DATE | TIME_SECONDS)); │
│ │
│ // [DEV FILL] — replace stub with real work: │
│ // 1. WebRequest tới REST API │
│ // 2. Đọc/ghi file ở MQL5/Files/ │
│ // 3. Notify Telegram / Slack │
│ // 4. Multi-symbol data poll │
│ // │
│ // Yêu cầu: idempotent — restart không duplicate side │
│ // effect (POSTs, file writes, queue pushes). │
└─────────────────────────────────────────────────────────┘
```

**Heartbeat Print là bắt buộc** (the kit spec §17) — VPS-side canary
detect wedged thread bằng cách monitor Experts log freshness. Nếu
service hang (REST timeout không return, WebRequest lock), heartbeat
ngưng → canary alert.

---

## Giai đoạn 3 — Service shutdown

Khi `ServiceShutdown()` trigger:
1. `IsStopped()` → `true`.
2. Loop break sau khi finish `DoOneCycle` hiện tại.
3. Print "stopping cleanly" trước khi return từ OnStart.
4. Terminal release resources auto.

KHÔNG có OnDeinit. Nếu cần cleanup phức tạp (close file handle,
finalize HTTP session), đặt SAU vòng `while` trong OnStart.

---

## Tính toán phối hợp các input

Service chỉ có **2 input**:

```
   InpPollIntervalMs ──► Sleep() giữa các cycle
                              │
                              ▼
   Mỗi cycle:
     - heartbeat Print
     - [DEV] work unit

   InpServiceTag ──► identifier trong log
                       (để filter Experts tab khi
                        chạy nhiều service)
```

**Quy tắc tune**:

- `InpPollIntervalMs` quyết định cadence. Quá nhỏ (< 100ms) → CPU
  spike + REST rate limit. Quá lớn (> 60000ms) → service mất tính
  realtime.
- REST endpoint chậm (timeout 5-30s) → set `InpPollIntervalMs` ≥
  timeout + 500ms để không overlap.
- `InpServiceTag` unique mỗi instance — nếu chạy 2 service cùng lúc
  (vd 1 cho telegram, 1 cho VPS heartbeat), tag khác nhau để log
  không trộn.
- Service KHÔNG dùng `InpRiskMoney` / `InpSlPips` (không trade).

---

## Setup khuyến nghị

| Tình huống | InpPollIntervalMs | InpServiceTag |
|---|---|---|
| VPS heartbeat | 60000 (1 phút) | "vps-heartbeat" |
| Telegram notify daemon | 5000-10000 | "telegram-bot" |
| Multi-symbol data poller | 30000-60000 | "data-poller" |
| LLM signal feeder (cloud) | 30000-60000 | "llm-feeder" |

Quan trọng:
- Service KHÔNG mở lệnh trực tiếp. Nếu cần trade theo signal service
  produced, dev tạo EA riêng (vd `stdlib/netting`) đọc signal từ file
  `MQL5/Files/` mà service ghi.
- Test service trên Linux Wine: `mql5-doctor --soft` (service không
  cần chart attach).
- Verify auto-restart: service crash → MT5 KHÔNG tự restart. Dùng
  Task Scheduler (Windows) / systemd (Linux Wine) để watch process.
