# VibeCodeKit MQL5 EA — v3.3.0rc7

VibeCodeKit MQL5 EA là bộ công cụ build, audit và đóng gói Expert Advisor MQL5 theo nguyên tắc **fail-closed**. Source tích hợp hiện tại trong `main` là **v3.3.0rc7**.

> **Trạng thái hiện tại:** source/package/native-compile RC7 đã được xác minh, nhưng **chưa phải production/live release**. `release_eligible=false` cho đến khi các gate runtime bắt buộc của EA mục tiêu (Strategy Tester, stress/restart-recovery, forward/broker evidence và approval tương ứng) có bằng chứng native đáng tin cậy.
>
> **Latest published GitHub tester pre-release:** `v3.3.0rc6`. RC7 hiện là code line mới nhất đã tích hợp trong repository, chưa được promote thành GitHub Release/tag RC7.

## Bề mặt sử dụng chính

Người dùng bình thường nên bắt đầu với 5 command public:

```text
vkmql-new
vkmql-check
vkmql-ship
mql5-ea-deep-review
mql5-doctor
```

Ba umbrella command chính:

```bash
vkmql-new --help
vkmql-check --help
vkmql-ship --help
```

Các `mql5-*` command còn lại là advanced/internal/compatibility surface. Catalog hiện có **139 console entry points**, nhưng không phải 139 command mà người dùng phải ghi nhớ.

## VibecodeV5 workflow canonical

```text
SCAN
  → RRI
  → SPECIFY
  → DECIDE
  → CONTRACT
  → PLAN
  → BUILD
  → VERIFY
  → EVIDENCE
  → RETRO
```

Workflow phải scale theo risk và task size; không biến mọi bugfix nhỏ thành full ceremony. Với release/hardening/native-evidence, dùng Full mode.

## Quick start

Từ source package đã giải nén:

```bash
cd tool/source
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'

mql5-doctor --soft
mql5-selftest
```

Tạo governance artefacts cho project mới:

```bash
vkmql-new spec ./MyEA --name MyEA --symbol EURUSD --tf H1
vkmql-new contract ./MyEA --name MyEA
```

Build từ EA-IR/prompt bằng advanced primitives khi cần, sau đó kiểm tra bằng high-level gate:

```bash
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 --backend auto
vkmql-check all ./MyEA
```

`vkmql-check all --require-release` chỉ PASS khi **mọi stage bắt buộc** có evidence release-grade; `UNTESTABLE` không được đổi thành PASS.

## Native compile RC7

Canonical compile router:

```text
local Windows MetaEditor
  → GitHub Actions Windows
  → remote Windows worker
  → Wine MetaEditor (development/diagnostic only)
  → UNTESTABLE
```

House policy:

- MetaEditor compile log phải có `Result:`;
- mặc định đúng `0 errors, 0 warnings`;
- `.ex5` phải thực sự tồn tại;
- stale log/EX5 bị xóa trước run;
- MetaEditor process exit code **không** phải success authority duy nhất;
- GitHub-native evidence phải bind repository/run/job/commit/tree + artifact SHA-256/size;
- native compile **không** đồng nghĩa Strategy Tester/forward/live PASS.

Tài liệu backend: `tool/source/docs/GITHUB-NATIVE-COMPILE-vi.md`.

## Evidence và release semantics

Release-looking claim chỉ hợp lệ khi canonical policy và provenance gate đồng ý. Một file tên `PASS`, một XML parse được, hoặc một hash chain riêng lẻ không đủ chứng minh execution provenance.

Runtime level được đánh giá riêng:

```text
DRAFT
BACKTEST_ELIGIBLE
FORWARD_ELIGIBLE
LIVE_ELIGIBLE
```

RC7 hiện chứng minh repository/source/package/native-compile readiness của kit. Nó **không** tự chứng minh profitability, broker compatibility, restart safety hay live readiness của EA được build bằng kit.

## Trạng thái E2E mới nhất

Audit Full theo VibecodeV5 ngày 2026-08-12 xác nhận:

- Python regression matrix 3.10 / 3.11 / 3.12: PASS;
- 283 tests trên baseline RC7 trước docs-sync: PASS;
- selftest 13/13: PASS;
- 139 entrypoints import/callable: PASS;
- repository hygiene + duplicate-content policy: PASS;
- repository manifest: PASS;
- deterministic wheel ×2: PASS;
- installed-wheel selftest ngoài checkout: PASS;
- exact Windows MetaEditor compile trên runtime baseline: PASS, `0 errors, 0 warnings`;
- Strategy Tester / restart-recovery / broker parity / forward-live: chưa có evidence đủ để claim PASS.

Chi tiết và SHA/run IDs nằm tại:

- `docs/release/v3.3.0rc7/RC7-CANDIDATE-STATUS.md`
- `docs/release/v3.3.0rc7/FULL-E2E-AUDIT-2026-08-12.md`

## Documentation map

Bắt đầu tại:

- `tool/source/docs/QUICKSTART.md` — luồng ngắn nhất;
- `tool/source/docs/HUONG-DAN-TOAN-TAP-vi.md` — hướng dẫn tiếng Việt đầy đủ;
- `tool/source/docs/USAGE-en.md` — English operating guide;
- `tool/source/docs/USER-GUIDE-en.md` — English step-by-step guide;
- `tool/source/docs/COMMANDS.md` — command surface và advanced tooling;
- `tool/source/docs/DOC-MAP.md` — canonical docs map;
- `tool/source/docs/GITHUB-NATIVE-COMPILE-vi.md` — GitHub Windows native backend.

Các HTML audit cũ trong `tool/source/docs/` là **historical snapshots**; version/test count trong đó không phải current RC7 verdict.

## Repository layout

```text
tool/source/                         canonical executable source
.github/actions/mql5-native-compile/ reusable Windows native compile action
.github/workflows/                   CI / package / evidence gates
scripts/maintenance/                 repository/release maintenance
scripts/native/ProbeEA.mq5           canonical native toolchain probe
docs/release/v3.3.0rc7/              current RC7 status/audit ledgers
demo/                                fixtures/acceptance evidence, not strategy defaults
```

Distribution snapshot dưới `tool/source/scripts/vibecodekit_mql5/resources/distribution/` là mirror có chủ đích để regression có thể chạy từ installed wheel; không được deduplicate như build rác.

## Published release boundary

GitHub Release được publish gần nhất vẫn là **v3.3.0rc6 tester pre-release**. Các RC4/RC5/RC6 artefact lịch sử và checksum được giữ như immutable/historical evidence theo policy repository.

RC7 sẽ chỉ nên được promote khi release criteria được quyết định rõ cho target và evidence tương ứng đã đủ. Không dùng native compile PASS để thay thế Strategy Tester hoặc live validation.

## Security / governance notes

- Secrets, broker credentials và live-trading credentials không được commit vào source.
- Release evidence phải bind SHA/hash/provenance thay vì tin tên file.
- `MT5_INSTALLER_SHA256` nên được pin ở release environment; installer hash quan sát sau download không thay thế pre-known trust pin.
- GitHub branch protection là repository-admin control riêng, không phải code-level invariant của kit.

## License

Xem `LICENSE` trong repository/package tương ứng.
