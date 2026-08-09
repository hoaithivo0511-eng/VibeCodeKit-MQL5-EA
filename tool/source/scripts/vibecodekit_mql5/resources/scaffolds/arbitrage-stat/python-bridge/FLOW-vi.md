EA `{spec.name}` (scaffold **arbitrage-stat / python-bridge**) là
**statistical arbitrage** dựa trên **cointegration Z-score** giữa 2
symbol liên quan (vd EURUSD-GBPUSD, XAUUSD-XAGUSD), với signal compute
ở Python (statsmodels / scikit-learn) rồi feed sang EA qua file IPC.

Symbol gốc của EA này là `{spec.symbol}` (data anchor); cặp đối chiếu
do dev cấu hình trong Python script. Tài khoản chế độ **netting** (1
net per symbol; vì arb là multi-symbol nên mỗi leg ở 1 symbol khác
nhau, không conflict).

Idea: 2 symbol cointegrated thì spread (giá A - β × giá B) dao động
quanh 0 với Z-score chuẩn hoá. Long spread (Buy A + Sell B) khi
Z < -threshold; Short spread khi Z > +threshold; close khi |Z| < 0.5.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip (cho leg A).
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD
   {spec.risk.daily_loss_pct:pct} cap, {InpMaxPositions} đếm tổng
   leg A + leg B.
3. `registry.Reserve(InpMagic, "{spec.name}")`.
4. **[DEV FILL] Setup Python bridge**:
   - `EventSetTimer(60)` — poll Python signal mỗi 60 giây (Z-score
     không cần update mỗi tick).
   - Python sidecar chạy độc lập, đọc tick data 2 symbol, fit
     cointegration regression rolling, ghi `MQL5/Files/{spec.name}_zscore.json`.

Fail bất kỳ → `INIT_FAILED`.

---

## Giai đoạn 2 — OnTimer (chính, KHÔNG OnTick)

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() (refresh equity tracker) │
├─────────────────────────────────────────────────────────┤
│ 2. Risk gate (DD + position cap) │
├─────────────────────────────────────────────────────────┤
│ 3. Đọc Python output │
│ FileOpen("{spec.name}_zscore.json", FILE_READ|...) │
│ parse: { │
│ z: float, │
│ beta: float, │
│ symbol_a: "{spec.symbol}", │
│ symbol_b: "...", │
│ ts: epoch │
│ } │
│ Nếu mtime > 5 phút → ignore (Python dead) │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Compute leg sizes │
│ lot_a = pip.LotForRisk(InpRiskMoney/2, InpSlPips) │
│ lot_b = lot_a × beta (hedge ratio từ Python) │
├─────────────────────────────────────────────────────────┤
│ 5. Signal logic │
│ Mở pair khi không có position open: │
│ Z < -InpZEntry → Buy A + Sell B (long spread) │
│ Z > +InpZEntry → Sell A + Buy B (short spread) │
│ Đóng pair khi đã có position: │
│ |Z| < InpZExit → close cả 2 leg │
├─────────────────────────────────────────────────────────┤
│ 6. [DEV FILL] Mở/đóng pair qua CSafeTradeManager │
│ Lưu ý: 2 leg ở 2 symbol khác nhau → OrderSend riêng │
└─────────────────────────────────────────────────────────┘
```

---

## Giai đoạn 3 — OnDeinit

1. `EventKillTimer()`.
2. KHÔNG đóng pair khi remove EA — dev quyết định manual hoặc external
   supervisor. Python process độc lập.

---

## Tính toán phối hợp các input

```
   Python (statsmodels) ──┐
       │ │
       ▼ ▼
   rolling regression spread = A - β × B
   → β (hedge ratio) │
                           ▼
                    z = (spread - mean) / std
                           │
                  ┌────────┴────────┐
                  ▼ ▼
         z < -InpZEntry z > +InpZEntry
         Buy A + Sell B Sell A + Buy B
                  │ │
                  └────────┬────────┘
                           ▼
              EA OnTimer poll → execute
                           │
              risk.CanOpenNewPosition() pass?
                           │
                           ▼
        lot_a = (InpRiskMoney/2) ÷ (InpSlPips × pip_value_A)
        lot_b = lot_a × β
                           ▼
              OrderSend 2 leg (cùng magic)
                           │
                           ▼ later
              |Z| < InpZExit → close both
```

**Quy tắc tune**:

- Z-score entry threshold (`InpZEntry`) standard 2.0 (2σ extreme).
  Lớn hơn (2.5-3) → ít signal, chất hơn. Nhỏ hơn (1.5) → nhiều signal,
  noise nhiều.
- Z-score exit (`InpZExit`) thường 0.5 (mean revert) hoặc 0 (về
  trung bình).
- `InpRiskMoney` chia /2 cho 2 leg → tổng risk basket = `InpRiskMoney`.
- β (hedge ratio) update mỗi window rolling Python — nếu β drift mạnh
  giữa lúc position open, hedge bị unbalanced. Dev có thể re-compute
  β rồi rebalance leg.
- Cointegration FAIL khi 2 symbol decouple (vd central bank policy
  divergence) — phải có time-stop (đóng pair nếu open > N giờ vẫn
  không converge).

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Demo EURUSD-GBPUSD | `InpRiskMoney`=20, Z_entry=2.0, Z_exit=0.5, timer=60s |
| Live EUR-GBP arb | `InpRiskMoney`=50-100, Z_entry=2.0, Z_exit=0.3 |
| Live commodity pair XAU-XAG | `InpRiskMoney`=100-200, Z_entry=2.5, Z_exit=0.5 |
| Prop-firm arb | `InpRiskMoney`=20, `InpDailyLossPct`=0.04, Z_entry=2.5 |

Trước khi đẩy lên live: backtest cointegration 6-12 tháng, kiểm
half-life mean-reversion (phải < InpMaxHoldDays), monitor β stability
qua walkforward. Pair trading FAIL trong regime shift (Fed pivot,
Brexit) — phải có circuit breaker đóng pair khi P/L > threshold.
