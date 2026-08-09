
## Hướng dẫn tiếng Việt (đọc 1 file là đủ)

Toàn bộ hướng dẫn đã được gộp vào một tài liệu duy nhất:

```text
docs/HUONG-DAN-TOAN-TAP-vi.md
```

Mở đúng file này là nắm trọn cách build EA từ đầu đến package, deep-review,
workflow Chủ nhà–Thầu–Thợ, remote worker, MCP/IDE và catalog lệnh.


# VibeCodeKit MQL5 EA – v3.3.0 RC4 EA specification compiler

Bản v3.1 RC2 bổ sung pipeline lossless `document/prompt → EA-IR → capability
plan → composable codegen → hash-bound evidence`. Xem hướng dẫn mới tại
`docs/EA-IR-COMPILER-v3.1-vi.md`. Luồng legacy preset vẫn được giữ để tương
thích, nhưng build EA mới nên dùng `mql5-doc-intake-ir`, `mql5-ir-build` và
`mql5-ir-verify`.


Bản này giữ runtime/pipeline v2.6.x làm nền tương thích và bổ sung lớp governance
agent-native v3: Lite/Standard/Full, Decision Ledger, AI-BUILD-CONTRACT v3,
Retro A1–A14 machine-readable guards, approval bound to hashes, và policy rõ
cho Windows/Wine, ONNX, MCP, evidence store và telemetry. Không có thay đổi
semantic nào được tự động áp dụng sau khi owner đã approve.

## Mục tiêu

- Tạo/scaffold EA MQL5.
- Sinh RRI questions, workflow steps, blueprint.
- Lint/static scan và anti-pattern scan.
- Compile wrapper cho MetaEditor/MT5 khi môi trường có sẵn.
- Parse/verify backtest report với chính sách chống fake-pass.
- Permission gate và package guard.
- Tạo evidence manifest để tránh claim `PASS / READY / RELEASE` không có bằng chứng.

## Thành phần được giữ

```text
scripts/vibecodekit_mql5/
Include/
scaffolds/
mcp/
docs/rri-personas/
docs/rri-templates/
docs/HUONG-DAN-TOAN-TAP-vi.md
docs/COMMANDS.md
docs/QUICKSTART.md
docs/USAGE-en.md
docs/USER-GUIDE-en.md
docs/anti-patterns-AVOID.md
docs/MIGRATE-VPS.md
pyproject.toml
requirements.lock
tool-catalog.json
agent-contract.json
LICENSE
```

## Thành phần không thuộc luồng user-facing mặc định

```text
skill/vibecode-mql5/
docs/references/
docs/reference-ea/
examples/
tests/fixtures/
tests/gates/
.github/
Dockerfile.devin
dev-only report/render scripts
```

Các phần trên phục vụ maintainer, example, fixture hoặc reference. Chúng không
được dùng làm evidence release. Nếu package có fixture để kiểm thử nội bộ,
agent phải gắn nhãn fixture và không được claim đó là kết quả runtime thật.

## v3 governance quick path

```bash
# Tạo spec v3 + contract + Decision Ledger
vkmql-new spec <project-dir> --name MyEA --symbol EURUSD --tf H1
vkmql-new contract <project-dir>

# Kiểm tra semantic decisions và Retro Guard evidence
vkmql-check decisions <project-dir>
# Create a conservative UNTESTABLE skeleton before recording Retro proof
mql5-retro-init <project-dir>
vkmql-check retro <project-dir>

# Full gate; thiếu MetaEditor/MT5 sẽ là UNTESTABLE, không phải PASS
vkmql-check all <project-dir> --require-release
```

Lite chỉ dành cho thay đổi không đổi trading behavior. Nếu chạm entry/exit,
risk, units, order lifecycle, retry, broker behavior hoặc live scope, router
phải tự nâng lên Standard/Full.

`mql5-retro-check` now runs conservative executable checks for Retro A1–A14, including UI claim provenance and panel performance.
Missing semantic proof is reported as `UNTESTABLE`; it is never upgraded to
`PASS` merely because an evidence file exists. Text in this repository that
mentions v2.6/v2.6.1 is retained as compatibility history, not as the current
governance contract.

## Quy tắc validation quan trọng

Không có claim nào như `PASS`, `READY`, `PRODUCTION READY`, `RELEASE ELIGIBLE` được coi là hợp lệ nếu thiếu:

```text
evidence/manifest.json
release_eligible=true
compile log hash + trusted execution provenance
EX5 hash nếu đã compile và binary không phải stub/fixture
backtest/gate report hash + XML metrics nếu yêu cầu release
```

`command_ok=true` chỉ có nghĩa command chạy xong. Nó không đồng nghĩa EA đã pass release.

`check_all`, `mql5-evidence-attestation` và `mql5-ship` dùng cùng một
provenance gate. Evidence chỉ có đường dẫn hoặc hash nhưng thiếu `source`,
`command`, `tool_version`, `host`, `recorded_at_utc` sẽ là `UNTESTABLE/FAIL`;
log import, report mẫu và Wine-only compile không thể tạo release eligibility.

## Các flag nguy hiểm

Các flag sau chỉ dùng debug/dev:

```text
--draft
--no-compile
--no-gate
--unsafe-allow-skips
```

Nếu dùng một trong các flag này, artifact không được xem là release eligible.

`--allow-skips` là alias cũ/deprecated. Dùng `--unsafe-allow-skips` để thể hiện rõ đây là chế độ không an toàn.

## Flow khuyến nghị

```bash
# 1. Tạo spec hoặc scaffold EA
mql5-build --help

# 2. Chạy lint/static scan
mql5-lint <path-to-ea-or-project>

# 3. Compile bằng MetaEditor/MT5 nếu môi trường hỗ trợ
mql5-compile <path-to-ea.mq5>

# 4. Backtest/verify report
mql5-backtest --report <tester-report.xml>

# 5. Permission gate
mql5-permission --help

# 6. Package chỉ khi manifest release_eligible=true
mql5-package --help
```

## RRI / Blueprint pipeline

Bản slim v2 giữ lại:

```text
docs/rri-personas/
docs/rri-templates/
```

Đây là input/template cho RRI và blueprint workflow. Chúng không phải test result và không phải evidence pass.

## Khi cần bản full

Dùng bản full hardened nếu bạn là maintainer và cần:

- unit/regression tests nội bộ,
- fixtures/golden dataset,
- examples/sample reports,
- reference docs,
- CI/dev container,
- plan/spec phát triển tool.

Với LLM/agent build EA, dùng bản slim v2 này an toàn hơn.

> **Đóng gói & phát hành.** Bản slim phân phối cho end-user được đóng gói bằng `mql5-dist`
> (zip tất định + `dist-manifest.json`, tự loại file dev/maintainer, evidence/test fixture,
> file `.bak` và stub model). Luồng release có ký
> (verify evidence → package build-output → `ship-manifest.json` ký HMAC qua `mql5-ship`) là
> thao tác maintainer-only; không còn gắn với git.


## Checkpoint Commands

Các command mới đã thêm để nâng tool từ heuristic sang evidence-first:

```bash
mql5-compile-runner --ea Experts/MyEA.mq5 --out evidence/compile
mql5-test-runner --ea Experts/MyEA.ex5 --config tester.ini --out evidence/tester
mql5-compile-repair --ea Experts/MyEA.mq5 --max-iterations 3
mql5-evidence-matrix --init-8x8 --out evidence/matrix.json
mql5-ap-policy Experts/MyEA.mq5 --profile portfolio
mql5-ml-validate --model model.onnx --features features.yaml --oos-report oos.xml --tester-report tester.xml --fallback-defined
mql5-project-gen --name MyPortfolioEA --profile complex-portfolio --out .
```

Các runner không tạo pass giả. Nếu thiếu MetaEditor/MT5 backend thật, manifest sẽ là `release_eligible=false`.


## Remote Worker · Contract Build · EA DOCX Docgen

Tất cả các chủ đề này đã được gộp vào `docs/HUONG-DAN-TOAN-TAP-vi.md`:

- Remote worker (Windows VPS chạy MetaEditor/MT5 thật) — §9
- Workflow Chủ nhà → Thầu → Thợ — §8
- Sinh tài liệu DOCX cho EA qua **docgen LLM structure-driven** (`mql5-docs-bundle` → `mql5-docs-assemble`) — §10


## Cổng chất lượng backtest & hygiene (tương thích v2.6.1)

Bản v2.6.1 bổ sung 3 lệnh kiểm chất lượng. **Quan trọng:** lệnh build EA (`mql5-build` / `mql5-project-gen`) **không tự chạy** các cổng này — chúng chỉ scaffold/dựng mã. Kiểm chất lượng là **bước riêng, gọi tường minh** qua cổng `vkmql-check`.

| Lệnh | Tự chạy trong `vkmql-check all`? | Ghi chú |
| --- | --- | --- |
| `mql5-backtest-quality` | ✅ Có — stage `quality` | Chấm tester XML theo PF/RF/Sharpe/R²/MaxDD → PASS/WARN/FAIL/INSUFFICIENT. Advisory; chỉ chặn release khi `--require-release`. |
| stage `forward` (dùng `mql5-walkforward`) | ✅ Có — stage `forward` | Cần `evidence/walkforward/{is,oos}_report.xml`; thiếu → UNTESTABLE (không FAIL). |
| `mql5-trade-hygiene` | ❌ Không — chạy riêng (`vkmql-check hygiene`) | Quét tĩnh trade-call hygiene; chỉ advisory (warn/info), không chặn gate. |
| `mql5-mt5-python` | ❌ Không — lệnh độc lập | Worker MetaTrader5 (cần MT5 thật); offline → UNTESTABLE (exit 3). |

```bash
# Cổng đầy đủ: quality + forward TỰ CHẠY ở đây (advisory)
vkmql-check all <project-dir>
vkmql-check all <project-dir> --require-release   # siết: quality/forward chặn release

# Chạy RIÊNG (không nằm trong build/gate mặc định)
vkmql-check quality tester.xml        # = mql5-backtest-quality
vkmql-check hygiene Experts/MyEA.mq5  # = mql5-trade-hygiene
mql5-mt5-python probe --json          # cần MT5 thật
```
