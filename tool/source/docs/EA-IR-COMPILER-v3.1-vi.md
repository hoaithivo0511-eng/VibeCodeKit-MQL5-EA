# VibecodeKit MQL5 v3.1 RC2 — EA-IR Compiler

## Mục tiêu

Luồng v3.1 không còn build trực tiếp từ một nhãn `preset/stack`. Prompt hoặc tài
liệu được biên dịch thành **EA-IR 3.1**, sau đó qua capability planner, codegen
module hóa, traceability và evidence gate.

```text
PDF / DOCX / TXT / prompt
        ↓
Document loader + page provenance
        ↓
EA-IR.json (canonical SHA-256)
        ↓
Ambiguity/conflict gate
        ↓
Feature registry + operational-config gate
        ↓
Composable MQL5 codegen
        ↓
requirements-matrix.csv + evidence/ir-artifacts.json
        ↓
MetaEditor / Strategy Tester evidence bound to the same IR hash
```

CCBSN chỉ là một golden fixture phức tạp để kiểm tra ontology tiếng Việt và
khả năng phát hiện nhiều engine. Không có template, tên vendor, mã lệnh chờ hay
logic riêng của CCBSN được hard-code làm kiến trúc mặc định của tool.

## Quy trình chuẩn

### 1. Intake từ tài liệu

```bash
mql5-doc-intake-ir \
  --file strategy-manual.pdf \
  --out EA-IR.json \
  --strict
```

Định dạng hỗ trợ: PDF, DOCX, TXT, Markdown, RST, CSV, YAML và JSON. PDF giữ ranh
giới trang để mỗi requirement có `source_refs.page`.

Intake từ prompt:

```bash
mql5-ea-intake-ir \
  --text "EA named AtlasDCA account hedging EURUSD H1 ..." \
  --out EA-IR.json \
  --strict
```

`--strict` chặn khi thiếu tên, account model, symbol, timeframe, signal logic
hoặc có semantic conflict. Tool không tự đổi hedging thành netting và không tự
điền tham số giao dịch im lặng.

### 2. Build từ canonical IR

```bash
mql5-ir-build \
  --ir EA-IR.json \
  --out-dir AtlasDCA
```

Hoặc qua surface tương thích:

```bash
mql5-auto-build \
  --spec EA-IR.json \
  --out-dir AtlasDCA \
  --no-compile --no-gate
```

Capability planner chỉ build feature có generator thật. Feature chưa hỗ trợ,
beta bị cấm, account mode không tương thích, multi-symbol/multi-timeframe chưa
có runtime tương ứng, hoặc nhiều signal chưa rõ composition đều block source
generation.

Với `controls.pending_order_remote`, profile phải khai báo ownership độc lập với
giá/type dùng để chọn command:

```yaml
controls:
  pending_command_ownership:
    magic: 881234
    comment_prefix: MYEACMD
    symbol_scope: managed_symbol
```

EA chỉ claim order khi symbol, magic và prefix cùng khớp. Sau khi claim, EA xóa
pending order thành công rồi mới áp dụng action. Ledger bền vững ngăn action bị
phát lại nếu terminal dừng giữa các bước; trạng thái không chứng minh được sẽ
khóa để operator reconciliation.

### 3. Verify semantic binding

```bash
mql5-ir-verify AtlasDCA
```

Static verification kiểm:

- `EA-IR.json` và `ir_sha256`;
- `BUILD-PLAN.json` cùng hash;
- hash nằm trong main EA và `Config.mqh`;
- requirements matrix không còn trạng thái `PLANNED` sau codegen;
- mọi artifact khớp `evidence/ir-artifacts.json`.

Sửa source sau khi seal sẽ bị phát hiện.

### 4. Bind native evidence

```bash
mql5-ir-verify AtlasDCA \
  --compile-evidence evidence/compile-result.json \
  --tester-evidence evidence/tester-result.json
```

Compile/tester evidence phải có:

```json
{
  "ir_sha256": "<exact EA-IR hash>",
  "status": "PASS",
  "evidence_type": "actual_metaeditor",
  "artifacts": [{"path": "...", "sha256": "..."}]
}
```

Tester dùng `actual_mt5_strategy_tester` hoặc trusted remote-worker equivalent.
Evidence của IR khác, imported log, fixture hoặc chỉ có cờ PASS sẽ bị từ chối.

## Nguyên tắc lossless

- Nhiều symbol/timeframe được lưu đầy đủ; codegen single-runtime hiện tại block
  thay vì lấy phần tử đầu.
- `trend filter` không bị biến thành `trend-following strategy`.
- Indicator nằm sau nhãn `filter/bộ lọc` không tự trở thành entry signal.
- Nhiều entry signal phải xác định `AND`, `OR` hoặc `selectable`; codegen hiện
  hỗ trợ `selectable`, còn composition chưa có generator sẽ block.
- Manual mô tả capability không được coi là cấu hình vận hành. Lot, spread,
  position cap, DCA step, multiplier, hedge sizing, exit target… phải được xác
  nhận trong build request hoặc IR.
- Feature registry là source of truth: schema nhận biết không đồng nghĩa codegen
  đã hỗ trợ.

## Status model

Không còn một cờ `build_ok` duy nhất:

```yaml
intake_complete: true
requirements_confirmed: true
capability_satisfied: true
source_generated: true
source_complete: true
compile_verified: false
tester_verified: false
release_eligible: false
```

`source_complete=true` không đồng nghĩa EA đã compile, backtest hoặc có trading
edge.

## Extension contract

Muốn thêm feature mới, phải đồng thời đăng ký:

1. ontology / IR path;
2. schema và operational parameters;
3. `FeatureCapability` trong `feature_registry.py`;
4. generator/module MQL5;
5. model/source tests;
6. traceability implementation symbol;
7. native test scenario khi phát hành.

Không được đánh dấu `stable` nếu thiếu generator hoặc test contract.
