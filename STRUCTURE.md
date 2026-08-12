# Repository structure — v3.3.0rc7 integrated line

Tài liệu này mô tả **repository hiện hành**, không phải cấu trúc của các release lịch sử.

- Current integrated source/tool: `v3.3.0rc7`.
- Latest published GitHub tester pre-release: `v3.3.0rc6`.
- Current source/package/native-compile readiness: verified.
- Runtime/live release eligibility: fail-closed cho đến khi target EA có đủ native runtime evidence.

## Canonical source boundary

```text
tool/source/
```

Đây là nguồn thực thi canonical của VibeCodeKit MQL5 EA. Version, package metadata, command catalog, tests và bundled resources phải xuất phát từ boundary này.

Các bề mặt chính:

```text
tool/source/pyproject.toml
tool/source/scripts/vibecodekit_mql5/
tool/source/tests/
tool/source/docs/
tool/source/skill/vibecode-mql5/
```

## CI / native compile boundary

```text
.github/actions/mql5-native-compile/
.github/workflows/rc7-github-native-compile.yml
.github/workflows/rc7-package-integration.yml
.github/workflows/release-gate.yml
.github/workflows/repo-manifest-check.yml
.github/workflows/repo-manifest-refresh.yml
scripts/native/ProbeEA.mq5
```

`Prepare-VKMql5Toolchain.ps1` sở hữu việc resolve/install MetaEditor và materialize/verify standard library. `Invoke-VKMql5Compile.ps1` chỉ nhận toolchain đã chuẩn bị và thực hiện compile/evidence. Không duy trì hai implementation installer/warm song song.

## Release / evidence ledgers

Current RC7 truth:

```text
docs/release/v3.3.0rc7/
  RC7-CANDIDATE-STATUS.md
  FULL-E2E-AUDIT-2026-08-12.md
```

Versioned RC4/RC5/RC6 ledgers và published artefacts là historical evidence. Không rewrite chúng để giả vờ lịch sử đã chạy bằng RC7.

## Distribution snapshot

```text
tool/source/scripts/vibecodekit_mql5/resources/distribution/
```

Đây là **intentional mirror**, được tạo để installed wheel có thể tự verify regression contracts ngoài source checkout. Snapshot có thể chứa bản sao tests/pyproject/catalog/agent contract; byte-identical duplicate ở boundary này là expected architecture, không phải build junk.

Nguồn sync canonical:

```text
scripts/maintenance/sync_distribution_snapshot.py
```

## Repository integrity

```text
REPO-MANIFEST.sha256
scripts/maintenance/repo_manifest.py
scripts/maintenance/check_duplicate_content.py
```

Policy:

- unclassified byte-identical tracked duplicates => FAIL;
- distribution mirrors / self-contained fixtures / frozen historical evidence => allow có lý do;
- `.ex5`, logs, caches, virtualenv, build/dist temp output không được track trừ khi một release artefact policy riêng cố ý version hoá chúng;
- manifest phải được regenerate sau thay đổi tracked tree liên quan release.

## Demo / fixture boundary

```text
demo/
  CCBSN-build-plan.json
  CCBSN-configured-ir.json
  CCBSN-extracted-ir.json
  CCBSN_GoldenFixture/
  generic-acceptance/
```

`demo/` là fixture/evidence để test tool. Nó **không** định nghĩa default trading logic cho kit và không được hardcode CCBSN/BlackDragon assumptions vào generic builder.

Các smoke workflow/project tạm từng dùng để kiểm RC7 native compile (`demo/rc7`, `demo/final`, workflow smoke tương ứng) đã được loại khỏi production tree trong PR #12.

## Documentation boundary

```text
tool/source/docs/HUONG-DAN-TOAN-TAP-vi.md   Vietnamese master guide
tool/source/docs/QUICKSTART.md              shortest operator path
tool/source/docs/USAGE-en.md                English operating guide
tool/source/docs/USER-GUIDE-en.md           English step-by-step guide
tool/source/docs/COMMANDS.md                command surface guide
tool/source/docs/DOC-MAP.md                 canonical topic map
tool/source/docs/GITHUB-NATIVE-COMPILE-vi.md GitHub native backend
```

Historical HTML reports trong `tool/source/docs/` giữ nguyên point-in-time metrics và được label historical. Current release verdict không được đọc từ chúng.

## VibecodeV5 lifecycle

Canonical delivery loop:

```text
SCAN → RRI → SPECIFY → DECIDE → CONTRACT → PLAN → BUILD → VERIFY → EVIDENCE → RETRO
```

BUILD/VERIFY implementation có thể dùng nhiều advanced `mql5-*` tools, nhưng operator surface ưu tiên `vkmql-new`, `vkmql-check`, `vkmql-ship`.

## Native compile vs runtime evidence

RC7 đã chứng minh Windows MetaEditor native compile trên exact runtime baseline. Điều này **không nâng** các stage sau thành PASS:

```text
Strategy Tester
quality / stress
restart / recovery
walk-forward
multi-broker / broker parity
forward / live
```

Các stage thiếu môi trường/evidence phải được ghi `UNTESTABLE` hoặc `INCOMPLETE`, không được suy diễn từ compile success.

## Historical release artefacts

Repository hiện vẫn giữ versioned RC4/RC5/RC6 artefacts theo policy lịch sử. Chúng có thể làm tree lớn nhưng không được coi là rác chỉ vì có `.zip`/wheel. Muốn giảm bloat cần một migration policy riêng (release assets/LFS/archive), không xóa trong hygiene cleanup thông thường.

## Governance outside the tree

Branch protection, required checks, repository roles và secret configuration là GitHub repository-admin state. Audit source phải report chúng riêng; không coi việc code tree sạch là bằng chứng các admin controls đã bật.
