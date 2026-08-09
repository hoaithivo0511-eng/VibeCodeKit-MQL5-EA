EA `{spec.name}` (scaffold **stdlib / python-bridge**) là **scaffold
khởi đầu tối giản với side-input từ Python** trên `{spec.symbol}` khung
`{spec.timeframe}`. Tài khoản chế độ **netting** (1 net position per
symbol).

Cấu trúc giống `stdlib/netting` — khác ở chỗ kèm sẵn thư mục `python/`
để dev chạy script sidecar (feature engineering, model inference, REST
API consumer…) và bridge data sang EA qua **file IPC** (CSV/JSON ở
`MQL5/Files/`) hoặc **named pipe**. EA chỉ POLL file ở OnTimer, KHÔNG
gọi Python từ OnTick (the kit spec §17 — service polling).

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} lệnh max.
3. `registry.Reserve(InpMagic, "{spec.name}")` — magic number.
4. **[DEV] Setup Python bridge**:
   - `EventSetTimer(N)` (vd 5 giây) — cadence poll file Python.
   - Khởi đầu một file watcher (`MQL5/Files/{spec.name}_signal.json`).
   - Spawn Python process độc lập (script `python/signal.py` hoặc
     `python/main.py`) qua một wrapper bên ngoài (Task Scheduler /
     systemd / VPS process supervisor). EA không tự `system()` được.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTimer (mỗi N giây, KHÔNG OnTick)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate (DD/positions/margin) │
├─────────────────────────────────────────────────────────┤
│ 3. Đọc tín hiệu từ Python │
│ FileOpen("{spec.name}_signal.json", FILE_READ|...) │
│ parse: { action, confidence, sl_pips, tp_pips, ts } │
│ Nếu file mtime quá cũ (> 60s) → ignore (Python dead) │
├─────────────────────────────────────────────────────────┤
│ 4. Compute lot │
│ lot = pip.LotForRisk(InpRiskMoney, sl_pips_from_py) │
├─────────────────────────────────────────────────────────┤
│ 5. [DEV FILL] Place order theo action │
│ Scaffold cung cấp infrastructure — order code do dev │
└─────────────────────────────────────────────────────────┘
```

OnTick KHÔNG được làm I/O (AP-17). File read luôn ở OnTimer.

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()` — release timer.
2. Đóng file handle nếu còn mở.
3. Python process tự xử lý lifecycle riêng (không kill từ EA).

---

## Tính toán phối hợp các input

```
   Python script ──[file IPC]──► EA OnTimer
                                    ▼
                              Parse signal JSON
                                    ▼
                              risk.CanOpenNewPosition()
                                    ▼
                       lot = InpRiskMoney ÷ (InpSlPips × pip_value)
                                    ▼
                              order Buy / Sell
```

**Quy tắc tune**:

- Cadence OnTimer (N giây) phải > thời gian Python feed signal.
  Nếu Python chạy 1 lần/phút → set timer ≥ 60s. Đọc file rỗng/cũ
  không nguy hiểm, nhưng tốn I/O.
- `InpRiskMoney` áp dụng cho từng signal Python output. Nếu Python
  output 5 signal/giờ và mỗi signal mở 1 lệnh → risk tích lại =
  `5 × InpRiskMoney`/giờ.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Dev iterate model | `InpRiskMoney`=10, timer=10s (nhanh feedback) |
| Live (Python stable) | `InpRiskMoney`=20-50, timer=30-60s |
| Prop-firm + Python | `InpRiskMoney`=10, `InpDailyLossPct`=0.04, timer=60s |

Trước khi đẩy lên live: verify Python process auto-restart trên VPS
(systemd `Restart=on-failure` hoặc Windows Task Scheduler restart),
log Python crash → file, EA detect file stale → skip thay vì mở lệnh
sai. `mql5-canary` để test bridge end-to-end.
