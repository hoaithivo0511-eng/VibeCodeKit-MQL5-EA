EA `{spec.name}` (scaffold **library / netting**) là **scaffold
reusable library** — đây KHÔNG phải EA trading hoàn chỉnh, mà là **EA
shell tối giản** dùng để **smoke-test thư viện `.mqh`** trước khi
include vào EA thật.

Mục đích thực tế: nếu bạn viết một thư viện helper (vd
`CMyIndicators.mqh`, `CMyStrategyBox.mqh`), thư viện chỉ là code chết
không chạy được trong MetaEditor. Bạn cần 1 EA "shell" tối giản để:
1. `#include` thư viện
2. Chạy lint + compile + load lên chart demo
3. Verify thư viện không có syntax error / undefined symbol

Symbol gốc `{spec.symbol}`, khung `{spec.timeframe}` — chỉ là anchor.
Tài khoản chế độ **netting**.

---

## Giai đoạn 1 — OnInit

1. `pip.Init(_Symbol)` — chuẩn hoá pip (chỉ để smoke-test
   `CPipNormalizer` import cleanly).
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — verify
   `CRiskGuard` import OK.
3. `registry.Reserve(InpMagic, "{spec.name}")` — verify
   `CMagicRegistry` import OK.
4. **[DEV FILL]** Include thư viện riêng + smoke-test method:
   ```
   #include "CMyIndicators.mqh"
   CMyIndicators myInd;
   if(!myInd.Init(_Symbol)) return INIT_FAILED;
   ```

Fail bất kỳ → `INIT_FAILED` → biết ngay thư viện có vấn đề.

---

## Giai đoạn 2 — OnTick

```
┌─────────────────────────────────────────────────────────┐
│ // All logic lives in shared library .mqh files. │
│ // OnTick trống — scaffold KHÔNG mở lệnh. │
│ │
│ [DEV] Nếu thư viện có method tick-level (vd │
│ myInd.Update()), gọi ở đây để smoke-test: │
│ myInd.Update(); │
└─────────────────────────────────────────────────────────┘
```

Library scaffold KHÔNG TRADE — vì mục đích là test thư viện, không
phải chạy chiến lược. Khi thư viện stable, import vào EA thật (vd
`stdlib/netting`, `trend/netting`).

---

## Giai đoạn 3 — OnDeinit

Trống. Dev tự thêm release tài nguyên cho object library.

---

## Tính toán phối hợp các input

Scaffold giữ nguyên 6 input chuẩn (`InpMagic`, `InpRiskMoney`,
`InpSlPips`, `InpTpPips`, `InpDailyLossPct`, `InpMaxPositions`) để:

1. Match interface chung của kit → tester preset (`.set`) tương thích.
2. Khi promote sang EA thật, các input đã đúng tên.

KHÔNG có logic tính toán nào ở scaffold này — input chỉ là placeholder.

---

## Setup khuyến nghị

| Tình huống | Tham số đề xuất |
|---|---|
| Smoke-test thư viện mới | giữ default — quan trọng là compile pass |
| Lint + dashboard run | `mql5-auto-build` để chạy lint + Trader-17 trên library |
| Load lên demo chart | drag scaffold vào chart, kiểm Print log không lỗi |

Workflow điển hình:
1. Viết `CMyLib.mqh` mới.
2. `mql5-init <name> --preset library --stack netting` → scaffold gốc.
3. `#include "CMyLib.mqh"` vào scaffold; add smoke-test method calls.
4. `mql5-auto-build --spec ea-spec.yaml` → lint + Trader-17 + compile.
5. Nếu pass → drag scaffold lên demo chart, mở Experts log để verify
   `Print` từ library không có error.
6. Khi stable → copy `CMyLib.mqh` vào `Include/` chung, import vào EA
   thật.

**Không** dùng scaffold này để live trade — nó là test harness, không
phải EA production.
