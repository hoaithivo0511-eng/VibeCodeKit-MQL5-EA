
## Hướng dẫn tiếng Việt (đọc 1 file là đủ)

Toàn bộ hướng dẫn sử dụng tổng quát đã được gộp vào:

```text
docs/HUONG-DAN-TOAN-TAP-vi.md
```

Riêng backend native compile GitHub Actions RC7 có tài liệu vận hành và evidence tại:

```text
docs/GITHUB-NATIVE-COMPILE-vi.md
```

Mở các tài liệu này để nắm cách build EA từ đầu đến package, deep-review,
workflow Chủ nhà–Thầu–Thợ, remote worker, GitHub native compile, MCP/IDE và catalog lệnh.


# VibeCodeKit MQL5 EA – v3.3.0 RC7

RC7 giữ pipeline lossless `document/prompt → EA-IR → capability plan →
composable codegen → hash-bound evidence` và bổ sung backend compile native
Windows qua GitHub Actions. EA-IR compiler được giới thiệu từ v3.1 RC2; xem
lịch sử và hướng dẫn subsystem tại `docs/EA-IR-COMPILER-v3.1-vi.md`. Luồng
preset cũ vẫn được giữ để tương thích, nhưng build EA mới nên dùng
`mql5-doc-intake-ir`, `mql5-ir-build` và `mql5-ir-verify`.

RC7 giữ runtime/pipeline v2.6.x làm nền tương thích và dùng lớp governance
agent-native v3: Lite/Standard/Full, Decision Ledger, AI-BUILD-CONTRACT v3,
Retro A1–A14 machine-readable guards, approval bound to hashes, cùng policy rõ
cho Windows/Wine/GitHub native compile, ONNX, MCP, evidence store và telemetry.
Không có thay đổi semantic nào được tự động áp dụng sau khi owner đã approve.

## Native compile RC7

Surface compile canonical:

```bash
vkmql-check compile <path-to-ea.mq5> --backend auto
```

Thứ tự `auto`:

```text
native Windows local
→ GitHub Actions Windows đã cấu hình
→ remote Windows worker đã cấu hình
→ Wine development backend
→ UNTESTABLE
```

House policy dùng chung cho mọi backend: `0 errors`, `0 warnings`, phải có
`Result:` summary và `.ex5` thật. GitHub backend còn yêu cầu exact
repository/commit/tree/run/job binding, ProbeEA PASS và SHA-256/size của
artifact. Nhãn `github_actions_metaeditor` tự nó không tạo trust.

Nếu repo chưa cấu hình `MT5_INSTALLER_URL`, Windows native job phải
`SKIPPED/UNTESTABLE`; fast/static gate xanh không được gọi là native compile
PASS. Native compile PASS cũng không thay thế Strategy Tester, stress,
restart/recovery, forward hoặc live evidence.

## Mục tiêu

- Tạo/scaffold EA MQL5.
- Sinh RRI questions, workflow steps, blueprint.
- Lint/static scan và anti-pattern scan.
- Compile MetaEditor qua local Windows, GitHub Actions Windows, remote worker hoặc Wine development backend.
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
docs/GITHUB-NATIVE-COMPILE-vi.md
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

# Full gate; thiếu MetaEditor/MT5/native evidence sẽ là UNTESTABLE, không phải PASS
vkmql-check all <project-dir> --require-release
```

Lite chỉ dành cho thay đổi không đổi trading behavior. Nếu chạm entry/exit,
risk, units, order lifecycle, retry, broker behavior hoặc live scope, router
phải tự nâng lên Standard/Full.

`mql5-retro-check` chạy conservative executable checks cho Retro A1–A14,
bao gồm UI claim provenance và panel performance. Missing semantic proof được
báo `UNTESTABLE`; không được nâng thành `PASS` chỉ vì evidence file tồn tại.
Text trong repository có nhắc v2.6/v2.6.1 được giữ như compatibility history,
không phải governance contract hiện tại.

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
log import, report mẫu, uncorrelated GitHub artifact và Wine-only compile không
thể tạo release eligibility.

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

# 3. Compile qua backend tốt nhất có sẵn
vkmql-check compile <path-to-ea.mq5> --backend auto

# Explicit GitHub backend
vkmql-check compile MQL5/Experts/MyEA/MyEA.mq5 \
  --backend github-actions \
  --project-root . \
  --github-repo OWNER/REPO \
  --github-ref main \
  --github-commit <40-char-sha>

# 4. Backtest/verify report (gate độc lập với compile)
mql5-backtest --report <tester-report.xml>

# 5. Permission gate
mql5-permission --help

# 6. Package chỉ khi manifest release_eligible=true
mql5-package --help
```

## RRI / Blueprint pipeline

Bản slim giữ lại:

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

Với LLM/agent build EA, dùng slim distribution để giảm surface không cần thiết.

> **Đóng gói & phát hành.** Bản slim phân phối cho end-user được đóng gói bằng `mql5-dist`
> (zip tất định + `dist-manifest.json`, tự loại file dev/maintainer, evidence/test fixture,
> file `.bak` và stub model). Luồng release có ký
> (verify evidence → package build-output → `ship-manifest.json` ký HMAC qua `mql5-ship`) là
> thao tác maintainer-only; không còn gắn với git.

## Checkpoint Commands

Các command evidence-first quan trọng:

```bash
vkmql-check compile Experts/MyEA.mq5 --backend auto
mql5-compile-runner --ea Experts/MyEA.mq5 --out evidence/compile
mql5-test-runner --ea Experts/MyEA.ex5 --config tester.ini --out evidence/tester
mql5-compile-repair --ea Experts/MyEA.mq5 --max-iterations 3
mql5-evidence-matrix --init-8x8 --out evidence/matrix.json
mql5-ap-policy Experts/MyEA.mq5 --profile portfolio
mql5-ml-validate --model model.onnx --features features.yaml --oos-report oos.xml --tester-report tester.xml --fallback-defined
mql5-project-gen --name MyPortfolioEA --profile complex-portfolio --out .
```

Các runner không tạo pass giả. Nếu thiếu backend thật hoặc provenance bắt buộc,
manifest/trạng thái phải giữ `UNTESTABLE` hoặc `release_eligible=false`.

## Remote Worker · GitHub Native Compile · Contract Build · EA DOCX Docgen

- Remote worker (Windows VPS chạy MetaEditor/MT5 thật): `docs/HUONG-DAN-TOAN-TAP-vi.md` §9.
- Workflow Chủ nhà → Thầu → Thợ: `docs/HUONG-DAN-TOAN-TAP-vi.md` §8.
- Sinh DOCX: `mql5-docs-bundle` → `mql5-docs-assemble`, xem §10.
- GitHub Windows native compile RC7: `docs/GITHUB-NATIVE-COMPILE-vi.md`.

## Cổng chất lượng backtest & hygiene (tương thích v2.6.1)

Bản v2.6.1 bổ sung 3 lệnh kiểm chất lượng. **Quan trọng:** lệnh build EA
(`mql5-build` / `mql5-project-gen`) **không tự chạy** các cổng này — chúng chỉ
scaffold/dựng mã. Kiểm chất lượng là **bước riêng, gọi tường minh** qua cổng
`vkmql-check`.

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
