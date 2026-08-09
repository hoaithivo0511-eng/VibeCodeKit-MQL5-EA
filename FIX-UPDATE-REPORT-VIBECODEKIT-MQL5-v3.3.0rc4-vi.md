# Báo cáo fix và cập nhật VibecodeKit MQL5 v3.3.0rc4

**Ngày:** 2026-08-06  
**Phạm vi:** loại semantic coupling từ fixture CCBSN, harden execution/runtime state và bổ sung invariant cho tổ hợp feature.  
**Kết luận:** các lỗi source và configuration path đã xác định trong audit v3.2.0rc3 đã được sửa và có regression test trực tiếp. CCBSN tiếp tục chỉ là một golden acceptance fixture, không phải template hoặc rule mặc định của tool.

## 1. Trạng thái xác minh cuối

| Gate | Kết quả |
|---|---:|
| Source regression | **126/126 PASS** |
| Source selftest | **13/13 PASS** |
| Wheel clean-install tests | **126/126 PASS** |
| Wheel clean-install selftest | **13/13 PASS** |
| Source ZIP độc lập tests | **126/126 PASS** |
| Source ZIP độc lập selftest | **13/13 PASS** |
| Generic cross-project acceptance | **4/4 PASS** |
| Python compileall | PASS |
| Production vendor-literal scan | **0 finding** |
| CCBSN clean-wheel rebuild | **69 capability, 0 blocker, static PASS** |
| MQL5 lint | PASS, 0 finding |
| Architecture | PASS |
| Contract | PASS, 0 error/warning |
| Canonical IR verification | PASS |
| Native MetaEditor compile | Chưa có môi trường xác minh |
| MT5 Strategy Tester | Chưa có môi trường xác minh |
| Release eligible | **false** |

Statement coverage toàn bộ package là **18,23%** do package giữ lại một bề mặt legacy rất lớn. Coverage của các module compiler/hardening trọng yếu cao hơn: `advanced_codegen` 95,43%, `build_planner` 91,67%, `feature_registry` 94,59%, `ea_ir` 93,94%, `safe_paths` 94,74%; `intake`, `feature_config` và `ir_configure` nằm trong khoảng 80–84%.

## 2. Chứng minh CCBSN không bị hard-code vào production tool

Production source và wheel đã được quét, loại trừ test resources. Không tìm thấy:

```text
CCBSN
Bo.Botfx
Can Cu Bu Sieng Nang
999999
666666
888888
555555
```

Các giá Mobile Control và command ID chỉ được lấy từ canonical EA-IR hoặc operator profile của từng project. Tool không còn command set mặc định sáu lệnh và không còn fallback price mang semantics của CCBSN.

Cross-project acceptance chạy từ wheel cài sạch đã build bốn EA độc lập:

- `NorthTrend`: trend-following/EMA cross.
- `RangePulse`: ATR breakout.
- `BandReturn`: Bollinger mean-reversion.
- `OrionRecovery`: recovery/hedging với custom command `32123.25` và `32124.75`.

Cả bốn project static-verify PASS và không chứa bất kỳ vendor literal hoặc giá command của CCBSN.

## 3. Phase 1 — Semantic isolation và command protocol tổng quát

### Đã sửa

- Xóa toàn bộ giá pending-order fallback khỏi `advanced_codegen`.
- Bỏ fixed vocabulary `stop_ea/start_ea/stop_buy/...` khỏi contract bắt buộc.
- Pending command trở thành danh sách data-driven gồm `id`, `transport`, `order_type`, `price` và structured `action`.
- Thêm cú pháp portable:

```text
COMMAND pause_alpha: buy_limit 12345 -> set_state ea.enabled=false
COMMAND flatten_magic: sell_stop 23456 -> close_scope managed_all
```

- Natural-language command không nhận dạng được action sẽ tạo ambiguity; tool không đoán.
- Profile overlay thay thế atomic toàn bộ command map và xóa requirements provenance cũ, không merge command của project trước.
- Thêm `variant` và `semantics_version` cho các feature có nhiều cách hiểu như Hedge Zone, cross-chain Sniper, lot balancing, reverse entry, lottery và remote transport.

### Gate mới

- Thiếu variant: build block.
- Variant không hỗ trợ: build block.
- Command type/price collision: build block.
- Command action chưa xác định: ambiguity block.

## 4. Phase 2 — Centralized exposure admission

Trước đây `Stop Buy/Stop Sell` được kiểm ở entry/DCA nhưng có thể bị bypass bởi hedge, reverse entry, lot balance hoặc Hedge Zone.

Mọi exposure engine hiện tạo một `ExposureIntent` và đi qua cùng một gate:

```text
EA enabled
→ daily halt
→ direction stop/permission
→ session/recovery timing policy
→ symbol/position capacity
→ ownership scope
→ Hedge Zone concurrency policy
→ intent/idempotency admission
```

Không engine nào được gọi executor trực tiếp ngoài gate này. Regression test xác nhận toàn bộ source tag `ENTRY`, `DCA`, `HEDGE`, `HEDGE_ZONE`, `REVERSE` và `BALANCE` đều đi qua `ExposureAllowed`.

## 5. Phase 3 — Broker outcome và idempotency

### Đã sửa

- Thêm persistent trade-intent ledger.
- Mỗi intent có stable identity và lifecycle.
- Timeout hoặc response không xác định chuyển intent sang `OUTCOME_UNKNOWN`.
- `OUTCOME_UNKNOWN` không được retry chỉ vì hết timeout.
- Trước khi retry, tool bắt buộc reconcile terminal truth từ orders, positions và history.
- Async execution chỉ được phép khi `execution_idempotency_policy=reconcile_before_retry`.
- Policy retry theo timeout bị planner từ chối.

### Tác dụng

Ngăn đường lỗi:

```text
broker đã nhận lệnh
→ terminal mất response
→ EA coi là fail
→ retry
→ mở trùng position
```

Đây là fix kiến trúc generic cho mọi EA, không phụ thuộc CCBSN.

## 6. Phase 4 — Event reducer cho OnTradeTransaction

Rủi ro được phân loại lại đúng là event-ordering/state-reconciliation, không phải thread race đơn giản.

### Đã sửa

- Raw `OnTradeTransaction` không trực tiếp thay đổi nhiều strategy state.
- Transaction được chuẩn hóa thành event và đưa vào reducer/queue.
- Deal/order/position identifiers giữ nguyên 64-bit, không ép qua `double`.
- Event trùng được deduplicate.
- Deal chưa xuất hiện trong history được giữ pending để reconcile ở lượt sau, không đánh dấu processed quá sớm.
- Final-close side effect dùng `POSITION_IDENTIFIER`, không dùng ticket dễ thay đổi.
- Partial fills/deal fragments được aggregate; lottery/reset chỉ chạy một lần khi position thực sự đóng hoàn toàn.

### Gate/test

- Duplicate deal không nhân lottery nhiều lần.
- Missing-history event không bị mất.
- Final-close grouping không nhầm ticket với position identity.

## 7. Phase 5 — Time policy, daily target và history accounting

### Đã sửa

- Daily guard và session filter không còn dùng clock domain ngầm khác nhau.
- Khi project dùng daily/session feature, `runtime.time_policy` phải được khai báo rõ.
- Time contract hỗ trợ daily basis, session basis, DST policy và explicit mixed-clock approval.
- Session-only EA cũng phải chọn clock policy; không còn default im lặng.
- Recovery engine hoạt động ngoài session phải có `recovery_session_policy` rõ ràng.
- History phải sẵn sàng qua hai lần sync liên tiếp trước khi daily accounting được tin cậy.
- Deposit/withdrawal/credit được tách khỏi trading P/L.
- Start-balance có recovery policy khi terminal offline qua day rollover.

### Invariant

`DCA outside session` không bao giờ được vượt qua daily halt. Daily halt có precedence cao hơn recovery/session override.

## 8. Phase 6 — Hedge Zone reconciliation

### Đã sửa

- Persistent zone state có schema version và migration path.
- Zone state sử dụng `POSITION_IDENTIFIER` làm anchor.
- `OnInit`, event reducer và exposure stage reconcile persisted state với live position book.
- Nếu position bị đóng thủ công hoặc không còn live leg phù hợp, stale zone được reset/rebuilt thay vì block DCA bằng state cũ.
- Exclusive mode chặn mọi recovery engine cạnh tranh.
- Cooperative mode chỉ cho engine nằm trong explicit whitelist.
- Lot balance/reverse/standard hedge không còn tự hoạt động trong zone nếu concurrency contract không cho phép.

### Giới hạn còn lại

Exact proprietary sequencing của một tài liệu cụ thể vẫn phải được khai báo bằng semantic variant. Tool không suy diễn rằng mọi feature có tên “Hedge Zone” đều dùng một thuật toán.

## 9. Phase 7 — Cross-feature invariant engine

Các tổ hợp sau giờ được validation trước codegen:

- account-wide exit thiếu ownership scope/approval;
- account-wide cross-chain Sniper thiếu approval;
- pending commands trùng `order_type + price`;
- async execution thiếu idempotency policy;
- Hedge Zone thiếu concurrency contract;
- Sniper pause chưa xác định hedge scope;
- recovery ngoài session thiếu policy;
- DCA outside session cố override daily halt;
- semantic variant không được registry hỗ trợ.

Điều này chuyển lỗi từ runtime sang planner blocker có thông báo cụ thể.

## 10. Phase 8 — Test-quality và distribution hardening

- External fixture bắt buộc bị thiếu giờ fail; fixture tùy chọn phải dùng explicit skip. Không còn `return` rồi bị tính PASS giả.
- Thêm test theo hành vi và source contract cho intent ledger, reducer, reconciliation, clock policy và feature interaction.
- Thêm four-archetype acceptance để phát hiện semantic pollution.
- Sửa lint false positive đối với tick ask–bid spread, entry delay/new-bar policy, utility `CTrade` wrapper và non-color hex mask.
- `.coverage`, `coverage.json`, build metadata và egg-info là never-ship artifacts.
- Wheel và source ZIP được test lại sau khi giải nén/cài độc lập.

## 11. CCBSN golden fixture sau cập nhật

CCBSN chỉ được dùng làm tài liệu acceptance có nhiều subsystem. Operator profile của demo nằm ngoài production defaults.

Kết quả rebuild từ wheel cài sạch:

- Canonical IR: `940e5167d1b0b65655caefe1e2644896da6c2e67b6a4ed02bd3c25dce2dd2a5b`.
- Planned capability: **69**.
- Blocker/warning: **0/0**.
- Source: **12 file MQL5/MQH**, 821 dòng vật lý, 81.868 bytes.
- Static IR verify: PASS.
- Lint: 0 finding.
- Architecture: PASS.
- Contract: 0 error, 0 warning.
- Release status: `release_eligible=false` do chưa có MetaEditor/Strategy Tester evidence.

Project này chứng minh tool có thể build một fixture phức tạp; nó không chứng minh parity với source gốc, profitability hoặc broker safety.

## 12. Các vấn đề còn mở, không thuộc nhóm lỗi vừa fix

### Native validation

Môi trường Linux hiện tại không có MetaEditor và MT5 Strategy Tester. Vì vậy chưa xác minh:

- MQL5 compiler compatibility;
- broker fill/requote/stop-level thực;
- transaction ordering thực trên terminal;
- tester scenarios và runtime performance;
- `.ex5` release artifact.

### Maintainability

Deep review còn 22 warning code-quality, chủ yếu cyclomatic complexity và số tham số lớn. Không có code error/anti-pattern lint finding, nhưng các hàm DCA, Hedge Zone, trailing, Sniper, event/command handler nên tiếp tục tách thành policy/state classes.

### Test breadth

Coverage toàn package 18,23% vẫn thấp vì 139 CLI và nhiều module legacy chưa được exercise. Compiler core mới có coverage cao; orchestration và CLI legacy vẫn cần tăng coverage trước khi coi toàn tool production-mature.

## 13. Verdict

Các lỗi đã phát hiện trong audit hard-coding/runtime đã được sửa bằng cả code, planner gate và regression test. Tool hiện không mang literal hoặc command defaults của CCBSN vào project khác, và feature recovery không còn tự chọn semantics chỉ dựa trên tên tổng quát.

Trạng thái đúng của tool và demo:

```text
TOOL: 3.3.0rc4 — semantic-isolated, runtime-safety hardened
CCBSN: SOURCE-COMPLETE, STATIC-VERIFIED
compile_verified = false
tester_verified = false
release_eligible = false
```
