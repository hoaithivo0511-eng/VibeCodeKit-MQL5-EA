EA `{spec.name}` (scaffold **indicator-only / netting**) là **EA
shell phát signal nhưng KHÔNG mở lệnh** — dùng để **smoke-test custom
indicator** trước khi tích hợp vào EA thật.

Symbol gốc `{spec.symbol}`, khung `{spec.timeframe}`. Tài khoản chế độ
**netting** (không quan trọng vì scaffold không trade).

Mục đích: phát triển indicator custom (`.mq5` custom indicator HOẶC
`iCustom` wrapper) cần verify:
1. Buffer phát đúng giá trị (không NaN, không 0 quanh đó-zone).
2. Smoothing / signal line khớp logic spec.
3. Performance OK (không lag terminal).

Scaffold cung cấp `Print` log + visual chart để dev đối chiếu indicator
output với expectation.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip (smoke-test import).
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD cap (vô
   nghĩa với scaffold này vì không trade, nhưng giữ interface chuẩn).
3. `registry.Reserve(InpMagic, "{spec.name}")` — magic chỉ để identify
   EA trong log.
4. **[DEV FILL]** Tạo indicator handle:
   ```
   h_custom = iCustom(_Symbol, _Period, "MyIndicator",
                      InpParam1, InpParam2, ...);
   if(h_custom == INVALID_HANDLE) return INIT_FAILED;
   ```

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() (token; không thực sự dùng) │
├─────────────────────────────────────────────────────────┤
│ 2. [DEV FILL] Đọc buffer indicator │
│ double buf[3]; │
│ if(CopyBuffer(h_custom, 0, 0, 3, buf) != 3) return; │
├─────────────────────────────────────────────────────────┤
│ 3. [DEV FILL] Log signal (KHÔNG mở lệnh) │
│ Print("Tick: ind[0]=", buf[0], │
│ " ind[1]=", buf[1], │
│ " ind[2]=", buf[2]); │
│ // Hoặc: nếu indicator phát signal (cross / band │
│ // trigger), log "SIGNAL_BUY" / "SIGNAL_SELL". │
└─────────────────────────────────────────────────────────┘
```

**KHÔNG TRADE**. EA này chỉ Print log để dev xem qua Experts tab. Đây
là khác biệt cốt lõi với `stdlib/netting`.

---

## Giai đoạn 3 — OnDeinit

1. `IndicatorRelease(h_custom)` — trả handle.

---

## Tính toán phối hợp các input

Scaffold giữ 6 input chuẩn nhưng KHÔNG dùng cho trading logic. Khi
indicator stable, dev có thể:
1. Thêm `InpParam*` riêng cho indicator (vd `InpEmaPeriod`,
   `InpRsiThreshold`).
2. Promote sang EA thật (vd `trend/netting`) — import indicator như
   `iCustom`, thêm signal logic + order placement.

Tại scaffold này, công thức duy nhất là:
```
buffer[i] = indicator_output(t-i, params)
```

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Smoke-test indicator mới | giữ default; quan trọng là buffer log đúng |
| Compare với MetaTrader native | mở indicator native cạnh EA; verify số khớp |
| Backtest indicator visual | Strategy Tester visual mode để xem indicator vẽ |

Workflow điển hình:
1. Viết `MyIndicator.mq5` (custom indicator) HOẶC iCustom wrapper.
2. Compile indicator → `MyIndicator.ex5` vào `MQL5/Indicators/`.
3. `mql5-init <name> --preset indicator-only --stack netting` →
   scaffold.
4. Add `iCustom(...)` trong OnInit + `CopyBuffer + Print` trong OnTick.
5. Drag scaffold lên demo chart, mở Experts tab xem log.
6. Compare với expected output (vd EMA values vs MT5 native EMA).
7. Khi indicator pass → promote sang EA thật.

**Không** dùng scaffold này để trade — order placement bị disable
intentionally. Đây là indicator harness, không phải EA.
