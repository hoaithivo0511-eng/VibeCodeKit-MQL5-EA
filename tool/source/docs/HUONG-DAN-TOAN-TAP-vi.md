---
id: huong-dan-toan-tap-vi
title: VibeCodeKit MQL5 EA — Hướng dẫn toàn tập (tiếng Việt)
audience: end-user
kit_version: 2.4.3
---

# VibeCodeKit MQL5 EA — Hướng dẫn toàn tập

> **Đây là tài liệu DUY NHẤT bạn cần.** Toàn bộ hướng dẫn tiếng Việt (cài đặt,
> quickstart, build EA từng bước, deep-review code, workflow Chủ nhà–Thầu–Thợ,
> remote worker, MCP/IDE, catalog lệnh, troubleshooting) đã được gộp vào đây cho
> bản tool mới nhất. Các file hướng dẫn cũ đã được rút gọn để tránh gây rối.

> **Tuyên bố trung thực.** `Trader-17`, ma trận chất lượng `8×8` / `64 ô`, các mã
> `AP-1…AP-25`, pipeline phân quyền 7 lớp và bộ persona RRI đều là **heuristic do
> kit này tự định nghĩa** — guardrail có chủ kiến, **không phải chuẩn ngành**,
> không phải chứng chỉ, và **không thay thế** kiểm thử trên tài khoản thật.

---

## Mục lục

1. [Tool này làm gì](#1-tool-này-làm-gì)
2. [Cài đặt môi trường](#2-cài-đặt-môi-trường)
3. [Quickstart 15 phút](#3-quickstart-15-phút)
4. [Triết lý 8 bước & 2 lối đi](#4-triết-lý-8-bước--2-lối-đi)
5. [Build EA chi tiết từng bước](#5-build-ea-chi-tiết-từng-bước)
6. [Schema `ea-spec.yaml` (8 block)](#6-schema-ea-specyaml-8-block)
7. [Deep-review / Audit một EA có sẵn (1 lệnh)](#7-deep-review--audit-một-ea-có-sẵn-1-lệnh)
8. [Workflow Chủ nhà → Thầu → Thợ](#8-workflow-chủ-nhà--thầu--thợ)
9. [Remote worker — MetaEditor/MT5 thật trên Windows VPS](#9-remote-worker--metaeditormt5-thật-trên-windows-vps)
10. [Sinh tài liệu DOCX cho EA](#10-sinh-tài-liệu-docx-cho-ea)
11. [RRI methodology & Review lenses](#11-rri-methodology--review-lenses)
12. [Tích hợp MCP & IDE/agent](#12-tích-hợp-mcp--ideagent)
13. [Anti-pattern, Trader-17 & ma trận chất lượng](#13-anti-pattern-trader-17--ma-trận-chất-lượng)
14. [Chính sách evidence — không PASS giả](#14-chính-sách-evidence--không-pass-giả)
15. [Catalog lệnh đầy đủ theo nhóm](#15-catalog-lệnh-đầy-đủ-theo-nhóm)
16. [Deploy lên VPS](#16-deploy-lên-vps)
17. [Troubleshooting & FAQ](#17-troubleshooting--faq)

---

## 1. Tool này làm gì

VibeCodeKit MQL5 EA là bộ kit build Expert Advisor (EA) MQL5 theo hướng
**LLM-safe, evidence-first**. Năng lực chính:

- **Tạo / scaffold EA** từ mô tả tự do hoặc `ea-spec.yaml` (17 archetype).
- **Sinh RRI questions, blueprint, workflow step** (deterministic, không cần LLM).
- **Lint / static scan** + 25 anti-pattern detector (regex và AST tùy chọn).
- **Compile** qua MetaEditor/MT5 (Wine trên Linux, native trên Windows).
- **Parse/verify** backtest report theo chính sách chống fake-pass.
- **Permission gate** 7 lớp + **package guard** đóng gói an toàn.
- **Deep-review code-base** một EA có sẵn bằng 1 lệnh (Stage 0→7).
- **Evidence manifest** để không claim `PASS / READY / RELEASE` thiếu bằng chứng.

Nguyên tắc cốt lõi: **`command_ok=true` chỉ nghĩa là lệnh chạy xong — KHÔNG
đồng nghĩa EA đã đạt release.** (Xem §14.)

---

## 2. Cài đặt môi trường

### 2.1. Yêu cầu

- Python 3.10+ (khuyến nghị 3.11).
- Linux/macOS/Windows. Wine + MetaEditor **chỉ cần** khi compile/backtest thật.
- Khoảng 1 GB đĩa trống cho venv + Wine prefix (nếu dùng).

### 2.2. Linux (Ubuntu 22.04+) — nhanh nhất

```bash
# 1) Giải nén bản phát hành (.zip) đã tải về
cd vibecodekit-mql5-ea

# 2) Venv riêng cho kit
python -m venv .venv && source .venv/bin/activate

# 3) Cài kit (pyyaml tự kéo; thêm [dev] cho pytest + ruff)
pip install -e ".[dev]"

# 4) (Tùy chọn) Cài Wine + MetaEditor headless (~3 phút, idempotent)
./scripts/setup-wine-metaeditor.sh

# 5) Health check — mọi probe bắt buộc phải ok: true
python -m vibecodekit_mql5.doctor
```

Không có Wine? Dùng **soft mode** — đẩy probe môi trường về WARN, vẫn kiểm
Python + scaffolds + manifest, exit 0 cho CI:

```bash
python -m vibecodekit_mql5.doctor --soft
```

### 2.3. macOS

Cài Wine qua Homebrew (`brew install --cask wine-stable`) rồi làm như Linux từ
bước 2. Nếu chỉ dùng phần phân tích tĩnh (không compile), bỏ qua Wine và dùng
`--soft`.

### 2.4. Windows native

```powershell
cd vibecodekit-mql5-ea
python -m venv .venv ; .venv\Scripts\activate
pip install -e ".[dev]"
python -m vibecodekit_mql5.doctor
```

Windows có MetaEditor/MT5 cài sẵn thì compile/backtest chạy native, không cần Wine.

### 2.5. Docker (CI / VPS)

Kit hỗ trợ image 3 tầng: `base` (Python deps) → `wine` (Wine + MetaEditor) →
`ci`. Dùng cho môi trường reproducible; chi tiết các biến môi trường ở §12.

### 2.6. `mql5-doctor` — health check

`mql5-doctor` kiểm tra: Python version, import kit, scaffolds, manifest, Wine,
MetaEditor binary, terminal path. Mọi probe **bắt buộc** phải `ok: true`. JSON
output có thêm `"soft": true` và `strict_ok` khi chạy `--soft`. Mã thoát: `0`
nếu chỉ có probe optional (Wine/MT5) fail dưới soft mode; `1` nếu probe bắt buộc fail.

---

## 3. Quickstart 15 phút

> Wine/MetaEditor là **tùy chọn** ở bước 1–4; chỉ cần ở bước 5 khi muốn biên
> dịch thật ra `.ex5`.

```bash
# (1) Cài đặt + health check
pip install -e ".[dev]" && python -m vibecodekit_mql5.doctor --soft

# (2) Scaffold EA đầu tiên (preset an toàn nhất: stdlib)
mql5-build stdlib --name SampleEA --symbol EURUSD --tf H1 \
    --out runtime/reference-ea/SampleEA

# (3) Lint (~30s) → scaffold tươi báo 0 ERROR, 1 WARN (AP-22 placeholder)
mql5-lint runtime/reference-ea/SampleEA/SampleEA.mq5

# (4) Trader-17 readiness (cần ≥ 15/17 để qua gate)
mql5-trader-check runtime/reference-ea/SampleEA/SampleEA.mq5

# (5) Pipeline phân quyền 7 lớp (fail-fast)
mql5-permission --mode personal runtime/reference-ea/SampleEA/SampleEA.mq5
```

Scaffold `stdlib` đã include sẵn `CPipNormalizer`, `CRiskGuard`,
`CMagicRegistry`, `CSpreadGuard`, `CSafeTradeManager` — đúng phần pip-math
cross-broker + cap rủi ro + đăng ký magic mà các gate kỳ vọng.

Scaffold tươi **chưa pass** Trader-17 (nhiều mục cần bằng chứng ngoài như
walk-forward, Monte-Carlo, multi-broker) — đó là gate **hoạt động đúng**, không
phải lỗi. Giá trị thật nằm ở vòng lặp **build → lint → trader-check → permission**
trong lúc bạn viết logic chiến lược.

Một lệnh chạy cả pipeline:

```bash
mql5-spec-from-prompt \
  "EA named TrendEA account netting EURUSD H1 trend, risk 0.5% mỗi lệnh" \
  --strict --out EA-IR.json
mql5-auto-build --spec EA-IR.json --out-dir build/MyEA
```

`mql5-auto-build` chain: scan → build → lint → compile → permission-gate →
dashboard → docs, và ghi `auto-build-report.json` idempotent.

---

## 4. Triết lý 8 bước & 2 lối đi

Vòng đời build EA gồm **8 bước**: `SCAN → RRI → VISION → BLUEPRINT → TIP →
BUILD → VERIFY → REFINE/SHIP`. Golden flow khi vận hành:

> **BUILD → COMPILE → BACKTEST → GATE → RELEASE** — chạy `mql5-check status`
> (hoặc `vkmql-check status`) bất cứ lúc nào để biết build đang ở đâu và lệnh
> tiếp theo cần chạy.

**3 mode** điều chỉnh độ ngặt của gate:

| Mode | Permission layer | Ma trận | Dùng khi |
|---|---|---|---|
| `personal` | 1,2,3,4,7 | 16 ô | Solo dev, prototype |
| `team` | 1–5,7 | 48/64 ô | Nhóm nhỏ, review chéo |
| `enterprise` | 1–7 | 64 ô (0 WARN) | Trước khi đưa lên tài khoản thật |

**Chọn 1 trong 2 lối đi:**

- **Lối A — CLI thủ công:** bạn gọi từng lệnh `mql5-*` theo lifecycle (xem §5).
  Phù hợp khi muốn kiểm soát chi tiết.
- **Lối B — AI coding agent qua MCP bridge:** agent gọi tool `vibecodekit-bridge`
  để build/verify/fix-loop (xem §12). Phù hợp khi build chat-driven.

Fast-path theo vai trò:

| Vai trò | Mục tiêu | Lệnh lõi |
|---|---|---|
| **Người mua/vận hành EA** | Giải nén → bản build đã verify | `mql5-selftest` → `mql5-build` → `mql5-flow` → `vkmql-ship release` |
| **Builder / quant** | Viết, compile, backtest, gate | `vkmql-new build`, `vkmql-check compile`, `vkmql-check test`, `vkmql-check audit`, `vkmql-check status` |
| **Reviewer / lead** | Đánh giá build không cần chạy lại | `vkmql-check status --html report.html`, `mql5-review --lens {eng,ceo,cso}`, `mql5-rri --collect`, `mql5-audit` |
| **Maintainer / release** | Ship bundle ký số, tái lập | `mql5-dist --flavor {slim,full,commercial}`, `vkmql-ship release`, `mql5-agent-contract --emit` |

---

## 5. Build EA chi tiết từng bước

### 5.1. Tạo project mới (modular generator)

```bash
mql5-project-gen --name MyPortfolioEA --profile complex-portfolio --out .
# profile khác: grid-safe, trend, mean-reversion, scalping, ...
```

Hoặc scaffold trực tiếp 1 archetype (17 archetype): `stdlib, trend,
mean-reversion, breakout, scalping, hedging-multi, news-trading, arbitrage-stat,
library, indicator-only, grid, dca, portfolio-basket, wizard-composable,
hft-async, ml-onnx, service-llm-bridge`.

```bash
mql5-build trend --name MyEA --symbol EURUSD --tf H1 --out build/MyEA
mql5-build --list   # liệt kê toàn bộ ma trận preset/stack
```

### 5.2. Chỉnh chiến lược

Mở file `.mq5` sinh ra, sửa block signal (phần kit đánh dấu placeholder AP-22).
Giữ nguyên các helper an toàn (`CPipNormalizer`, `CRiskGuard`, …).

### 5.3. AP policy theo profile

```bash
mql5-ap-policy Experts/MyEA.mq5 --profile portfolio
```

- **AP-5** (quá nhiều input) đã profile-aware: ngưỡng `> 6 inputs` nới theo profile.
- **AP-19** dành cho EA ML/ONNX (yêu cầu validate qua Strategy Tester).

### 5.4. EA dùng ML/ONNX: tạo bằng chứng validation

```bash
mql5-ml-validate --model model.onnx --features features.yaml \
  --oos-report oos.xml --tester-report tester.xml --fallback-defined
```

### 5.5. Evidence Matrix 8×8

```bash
mql5-evidence-matrix --init-8x8 --out evidence/matrix.json
```

### 5.6. Compile thật

Điều kiện: có MetaEditor (build ≥ 5260) qua Wine/native, hoặc remote worker (§9).

```bash
mql5-compile-runner --ea Experts/MyEA.mq5 --out evidence/compile
# dry-run chỉ để test flow (KHÔNG tạo release):
mql5-compile-runner --ea Experts/MyEA.mq5 --dry-run
```

### 5.7. Compile repair loop

```bash
mql5-compile-repair --ea Experts/MyEA.mq5 --max-iterations 3
```

Lặp compile → đọc lỗi → sửa heuristic → re-compile, tối đa N vòng.

### 5.8. Backtest bằng MT5 Strategy Tester

```bash
# Sinh tester config
mql5-tester-ini --expert Experts/MyEA.ex5 --symbol EURUSD --timeframe M15 \
  --from-date 2023.01.01 --to-date 2024.01.01 --report tester.xml --out tester.ini

# Chạy end-to-end (drive terminal64.exe + parse XML)
mql5-test-runner --ea Experts/MyEA.ex5 --config tester.ini --out evidence/tester

# Hoặc parse XML report bạn đã chạy tay:
mql5-backtest --report tester.xml --json   # → 14 metric chuẩn
```

> Report import sẵn **không** tự tạo release eligibility — cần chạy qua runner
> có bằng chứng hash.

Không có Wine? Dùng **simulator tick-bar in-process** cho CI hermetic:

```bash
mql5-bt-sim --strategy sma-cross --seed 42 --out tester.xml
mql5-backtest --report tester.xml --json
```

### 5.9. Kiểm robustness (tùy mục tiêu release)

```bash
mql5-walkforward is.xml oos.xml --gate-report gate-wf.json   # IS/OOS Sharpe
mql5-monte-carlo returns.csv --reported-dd 12.0              # bootstrap DD
mql5-overfit-check is.xml oos.xml                            # OOS/IS sanity
mql5-multibroker --reports a.xml,b.xml,c.xml                 # ổn định đa broker
```

### 5.10. Lint / static scan

```bash
mql5-lint Experts/MyEA.mq5 --json            # 8 AP critical (block ship)
mql5-lint Experts/MyEA.mq5 --use-ast         # AP-1/2/7 qua AST scanner
mql5-lint Experts/MyEA.mq5 --format sarif     # SARIF 2.1.0
mql5-method-hiding-check Experts/MyEA.mq5     # build-aware
```

### 5.11. Permission gate 7 lớp

```bash
mql5-permission --mode personal Experts/MyEA.mq5
# layer: source-lint → compile → AP-lint → Trader-17 → methodology →
#         quality-matrix → broker-safety (fail-fast)
```

### 5.12. Package release

```bash
mql5-package --build-dir build/MyEA       # tạo manifest.json (SHA-256) + ship.zip
```

Package guard yêu cầu bộ tài liệu **bundle LLM** (`docs/docs-context.json` + `docs/docs-prompt.md`, xem §10) và
`evidence/manifest.json` với `release_eligible=true`. Thiếu → block.

### 5.13. Flow mẫu đầy đủ (EA portfolio)

```bash
mql5-project-gen --name MyPortfolioEA --profile complex-portfolio --out .
mql5-ap-policy Experts/MyPortfolioEA.mq5 --profile portfolio
mql5-evidence-matrix --init-8x8 --out evidence/matrix.json
mql5-compile-runner --ea Experts/MyPortfolioEA.mq5 --out evidence/compile
mql5-compile-repair --ea Experts/MyPortfolioEA.mq5 --max-iterations 3   # nếu lỗi
mql5-test-runner --ea Experts/MyPortfolioEA.ex5 --config tester.ini --out evidence/tester
mql5-lint Experts/MyPortfolioEA.mq5
mql5-permission --mode team Experts/MyPortfolioEA.mq5
mql5-package --build-dir .   # chỉ khi manifest release_eligible=true
```

### 5.14. Cổng chất lượng backtest & hygiene (tự chạy vs chạy riêng)

Bản v2.6.1 thêm 3 lệnh kiểm chất lượng. **Lưu ý quan trọng:** lệnh build EA (`mql5-build` / `mql5-project-gen`) **không tự chạy** các cổng này — chúng chỉ scaffold/dựng mã. Kiểm chất lượng là **bước riêng, gọi tường minh** qua cổng `vkmql-check`.

| Lệnh | Tự chạy trong `vkmql-check all`? | Ghi chú |
| --- | --- | --- |
| `mql5-backtest-quality` | ✅ Có — stage `quality` | Chấm tester XML theo PF/RF/Sharpe/R²/MaxDD → PASS/WARN/FAIL/INSUFFICIENT. Advisory; chỉ chặn release khi `--require-release`. |
| stage `forward` (dùng `walkforward`) | ✅ Có — stage `forward` | Cần `evidence/walkforward/{is,oos}_report.xml`; thiếu → UNTESTABLE (không FAIL). |
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

---

## 6. Schema `ea-spec.yaml` (8 block)

Tất cả block đều **optional**; chỉ khai báo khi cần. Đây là schema legacy cho
consumer cũ; `mql5-spec-from-prompt` mặc định sinh canonical `EA-IR.json`.
Muốn sinh YAML này phải dùng rõ `--legacy`; `mql5-init` vẫn là wizard 5 câu hỏi.

| Block | Nhóm | Mục đích |
|---|---|---|
| `prop_firm` | PR-2 | Ràng buộc luật prop-firm (daily/total DD) |
| `time_exit` | PR-2 | Thoát lệnh theo thời gian/phiên |
| `stealth` | PR-2 | SL/TP ảo (không gửi broker) |
| `trailing` | PR-8 | Trailing stop |
| `partial_close` | PR-8 | Đóng một phần vị thế |
| `correlation` | PR-8 | Lọc tương quan cặp tiền |
| `swap_filter` | PR-8 | Lọc theo phí swap |
| `logs` | PR-8 | Cấu hình log/telemetry |

Validate spec (8 block): `mql5-auto-build` tự validate; chạy riêng để soi field
nào suy từ prompt vs default:

```bash
mql5-spec-from-prompt "..." --legacy --out ea-spec.yaml --explain --strict
```

Output legacy luôn mang `compatibility.release_eligible: false` và không được
dùng làm bằng chứng release.

---

## 7. Deep-review / Audit một EA có sẵn (1 lệnh)

Khi bạn muốn **rà soát toàn bộ code-base** một EA có sẵn (tìm dead-code,
hàm/biến không dùng, lỗi logic, hot-path, gợi ý hiện đại hóa) — chỉ cần **MỘT
lệnh duy nhất**:

```bash
mql5-ea-deep-review <path-to-ea.mq5 | path-to-project-dir>
# alias: mql5-ea-audit
#   --json   → envelope agent-contract
#   --fast   → bỏ Stage-7 (line-review LLM), chỉ phân tích tĩnh
#   --json-only / --no-docx → điều khiển định dạng (mặc định xuất MD+JSON+DOCX)
#   --out <dir> → ghi deep-review.{md,json,docx} vào thư mục chỉ định
```

Lệnh tự chạy pipeline **7 stage** rồi xuất 1 report hợp nhất:

| Stage | Nội dung |
|---|---|
| 0 | Parse + symbol-graph (def↔use hàm/biến/include) |
| 1 | Static scan / nhận diện hành vi & chiến lược |
| 2 | Anti-pattern lint (8 critical + best-practice) |
| 3 | Structure & complexity (LOC, cyclomatic, hot-path OnTick, duplicate) |
| 4 | Dead-code / dead-logic (unused var/func/include, unreachable, dead branch) |
| 5 | Senior review — risk / execution / state / release |
| 6 | Modernization advisor MQL5 2024–2026 |
| 7 | Grounded line-by-line review (mặc định tạo paste-pack có evidence-line) |

Report gồm: `readiness` (release-blocked/…); `score`/100; `strategy`;
`issue_counts` (critical/error/warn/info); danh sách dead-code; line-review packets.
UTF-16-LE/UTF-8-BOM được decode sạch (đã kiểm trong stress test).

**Prompt tự nhiên** cũng kích hoạt đúng lệnh này khi dùng qua agent, ví dụ:
*"hãy dùng tool scan/deep-review/audit code-base EA này cho tôi"*.

---

## 8. Workflow Chủ nhà → Thầu → Thợ

Trước khi build EA nghiêm túc, kit có workflow hợp đồng (governance):

```text
Owner interview → Contractor blueprint → Blueprint tip/review → Owner approval → Builder orchestrator
```

```bash
mql5-owner-interview --out contract/owner-interview.json \
  --name "Owner" --strategy hedgegrid --capital 1500 --symbol XAUUSD
mql5-contract-blueprint --interview contract/owner-interview.json \
  --out contract/contract-blueprint.json
mql5-blueprint-tip --blueprint contract/contract-blueprint.json \
  --out contract/blueprint-tip.json
mql5-owner-approve --interview contract/owner-interview.json \
  --blueprint contract/contract-blueprint.json --tip contract/blueprint-tip.json \
  --owner-name "Owner" --out contract/owner-approval.json
mql5-contract-build --interview contract/owner-interview.json \
  --blueprint contract/contract-blueprint.json --tip contract/blueprint-tip.json \
  --approval contract/owner-approval.json --out-dir workspace --name MyEA
```

- `mql5-owner-approve` **hash** interview/blueprint/tip; nếu file bị sửa sau khi
  duyệt → approval validation fail.
- `--force-draft-approval` cho phép build nháp để review kỹ thuật; **draft
  không làm release eligible**.
- `mql5-contract-build` không fake release: thiếu compile/backtest/evidence thật
  → `release_eligible=false` + liệt kê `missing_acceptance`.

**Triangle of Power** — 3 vai actor (prompt paste-and-run):

| Actor | Vai | Sở hữu bước |
|---|---|---|
| `chu-nha` | Chủ nhà (người vận hành) | SCAN, VISION, APPROVED, CONFIRM, REFINE |
| `chu-thau` | Thầu (Claude/GPT/Cursor Ask) | VISION design, BLUEPRINT, CONTRACT, TASK-GRAPH, VERIFY-REPORT |
| `tho-thi-cong` | Thợ (Claude Code/Devin/Cursor Edit) | SCAN exec, TIP, BUILD, VERIFY |

Gate liên quan: `mql5-contract-gen`, `mql5-verify-report`, `mql5-task-graph-gen`,
`mql5-completion-report`, `mql5-permission-layer5 --enforce-sign-off`,
`mql5-escalation` (log leo thang actor-to-actor, level 3 = hard block TEAM/ENTERPRISE).

---

## 9. Remote worker — MetaEditor/MT5 thật trên Windows VPS

Dùng Windows worker để chạy MetaEditor/MT5 thật thay vì stub.

### Setup Windows worker

```powershell
cd workers/windows
copy worker_config.example.json worker_config.json
notepad worker_config.json   # khai báo metaeditor64, terminal64, workspace
```

### Compile / backtest remote

```bash
mql5-compile-runner --ea workspace/MyEA/Experts/MyEA.mq5 \
  --backend remote-worker --worker-url http://WINDOWS_WORKER:8787 \
  --worker-token CHANGE_ME --out workspace/MyEA/evidence/compile

mql5-test-runner --ea workspace/MyEA/Experts/MyEA.ex5 \
  --config workspace/MyEA/tester.ini --backend remote-worker \
  --worker-url http://WINDOWS_WORKER:8787 --worker-token CHANGE_ME \
  --out workspace/MyEA/evidence/tester
```

### Multi-broker & walk-forward runner

```bash
mql5-multibroker-runner --brokers brokers.yaml --ea ...Experts/MyEA.ex5 \
  --tester-config tester.ini --report-name tester.xml --out evidence/multibroker
mql5-walkforward-runner --ea ...Experts/MyEA.ex5 --base-config tester.ini \
  --worker-url http://WINDOWS_WORKER:8787 --worker-token CHANGE_ME \
  --from-date 2021-01-01 --to-date 2024-01-01 --is-days 180 --oos-days 60 \
  --step-days 60 --out evidence/walkforward
```

**Fail-safe:** worker unreachable / thiếu `.ex5` / thiếu `tester.xml` / hash
mismatch / broker thiếu evidence → **fail** (không fake pass). Production worker
nên chạy sau service có auth/TLS. Job bundle (v5.1) nhúng zip base64 cho project
phức tạp có `Include/`, `.set`, `.onnx`, `.yaml`.

---

## 10. Sinh tài liệu DOCX cho EA (LLM structure-driven)

```bash
# 1) Sinh bundle ngữ cảnh trực tiếp từ .mq5 thật (inputs parse từ source)
mql5-docs-bundle workspace/MyEA/ea-spec.yaml workspace/MyEA/Experts/MyEA.mq5 \
  --out-dir workspace/MyEA/docs
# 2) LLM đọc docs-context.json + docs-prompt.md → tự viết workspace/MyEA/docs/guide.md
# 3) Convert guide.md → Word .docx
mql5-docs-assemble workspace/MyEA/docs/guide.md --out workspace/MyEA/docs/MyEA.docs.docx
```

Output bundle: `docs-context.json` + `docs-prompt.md` — ngữ cảnh deterministic
lấy từ inputs thật của `.mq5` (semantic-library enriched) + build/lint metrics.
Sau khi LLM viết `guide.md`, `mql5-docs-assemble` tạo `<EA>.docs.docx` (nhúng ảnh
từ `images/`, ToC refresh bằng F9, dấu tiếng Việt). FLOW do LLM tự dựng từ cấu
trúc OnInit/OnTick/OnDeinit của source — không dùng template cố định theo archetype.

`mql5-contract-build` tự gọi `mql5-docs-bundle` sau khi pass; **package guard**
yêu cầu bundle (`docs/docs-context.json` + `docs/docs-prompt.md`) khi ship.
Renderer template cố định cũ (`mql5-ea-docgen` / `mql5-ea-docs` →
`EA-LOGIC-AND-INPUTS-vi.docx`) đã được **gỡ bỏ ở v2.6** để tránh sinh tài liệu
mô tả input không tồn tại.

---

## 11. RRI methodology & Review lenses

**RRI** (1 umbrella + 3 alias):

```bash
mql5-rri                                   # in template Step-2 RRI
mql5-rri bt --metrics bt.json              # Backtest review (5 persona×7 dim×8 axis)
mql5-rri rr --trader-check tc.json --walkforward wf.json \
           --monte-carlo mc.json --overfit of.json   # Risk & Robustness
mql5-rri chart --metrics chart.json        # Indicator-dev RRI (optional)
python -m vibecodekit_mql5.rri.matrix --collect ./reports/ --output matrix.html
python -m vibecodekit_mql5.rri.matrix --audit         # cell-coverage audit
```

Ma trận nhận **6 ô discriminative** (1 mỗi cặp dim×axis); envelope có
`passes_personal_gate_only` / `passes_enterprise_gate_only`.

**Review lenses** (1 umbrella + 4 alias + 1 standalone):

```bash
mql5-review --lens eng          # broker-engineer + devops (BUILD, VERIFY)
mql5-review --lens ceo          # trader + strategy-architect (VISION, REFINE)
mql5-review --lens cso          # risk-auditor (RRI, VERIFY)
mql5-review --lens investigate  # perf-analyst + strategy-architect
mql5-second-opinion EA.mq5      # standalone lint + Trader-17 fast pass
```

---

## 12. Tích hợp MCP & IDE/agent

Kit có **4 MCP server**:

| Server | Vai trò | Lưu ý |
|---|---|---|
| `metaeditor-bridge` | Compile qua MetaEditor | Cần Wine/MetaEditor |
| `mt5-bridge` | Đọc journal/terminal MT5 | **READ-ONLY** (an toàn) |
| `algo-forge-bridge` | Push repo/PR lên Algo Forge | Cần token |
| `vibecodekit-bridge` | build/verify/fix-loop/docs cho agent | Điểm vào chính cho Lối B |

Cấu hình MCP cho từng môi trường:

- **Devin:** khai báo blueprint + secret; dùng Dockerfile reproducible.
- **Codex CLI:** thêm `AGENTS.md` ở root (setup/build/test/lint) + cấu hình MCP server.
- **Claude Code CLI:** thêm `CLAUDE.md` + skill file `build-ea` + MCP server.
- **Codex Desktop:** cấu hình MCP qua Settings UI; `mt5-bridge` chạy trên Windows.
- **Cursor:** `.cursor/rules/mql5-kit.mdc` + MCP qua Cursor Settings.
- **VS Code + Copilot Chat:** `.github/copilot-instructions.md` + `.vscode/mcp.json`.

Fix-loop tiêu biểu qua bridge: `verify.lint` ↔ `verify.auto_fix`; re-render docs
qua `docs.ea_render`. (Vì sao `mt5-bridge` read-only? Để agent **không** đặt
lệnh/sửa terminal — chỉ quan sát.)

---

## 13. Anti-pattern, Trader-17 & ma trận chất lượng

- **25 anti-pattern detector.** 8 AP critical = **ERROR, block ship**; phần còn
  lại là best-practice WARN. `mql5-lint --use-ast` chạy AP-1 (no SL) / AP-2 (SL
  quá chặt) / AP-7 (magic hardcode) qua AST scanner nhẹ (kết quả byte-identical
  với regex trên golden corpus). Tài liệu chi tiết: `docs/anti-patterns-AVOID.md`.
- **Trader-17.** Checklist 17 mục pre-deployment, gate yêu cầu **≥ 15/17**.
  Nhiều mục cần bằng chứng ngoài (walk-forward, Monte-Carlo, multi-broker,
  overfit, VPS, news-session).
- **Ma trận chất lượng 8×8 (64 ô).** PERSONAL dùng 16 ô; TEAM cần 48/64;
  ENTERPRISE cần 64 (0 WARN). Render/publish: `mql5-dashboard`.
- **`--draft`** hạ ERROR xuống WARN non-blocking, ép exit 0 (dùng trong
  chat-driven loop khi EA còn dở); envelope vẫn lưu `data.original_ok`.
  Khác với `--soft` (nới probe môi trường của `doctor`).

---

## 14. Chính sách evidence — không PASS giả

Một kết quả chỉ `RELEASE ELIGIBLE` khi có **đủ**:

- `compile_ok=true`, `backtest_ok=true`, `gate_ok=true`, `evidence_ok=true`
- **Không** dùng `--draft`, `--no-compile`, `--no-gate`, `--unsafe-allow-skips`
- **Không** có stage required bị skip
- Có `evidence/manifest.json` với `release_eligible=true` + hash artifact
  (compile log hash, EX5 hash, backtest/gate report hash khi cần release)

**Không tin** bất kỳ claim `PASS / READY / PRODUCTION READY / ALL GATES PASSED`
nếu thiếu manifest + hash. `command_ok` chỉ nghĩa là lệnh chạy xong.

Các flag chỉ dùng debug/dev (artifact KHÔNG release eligible):
`--draft`, `--no-compile`, `--no-gate`, `--unsafe-allow-skips`
(`--allow-skips` là alias deprecated).

---

## 15. Catalog lệnh đầy đủ theo nhóm

Mọi lệnh gọi qua console-script `mql5-<name>` hoặc `python -m
vibecodekit_mql5.<module>`. **Không** có router master `/mql5`. Ngoài các
primitive `mql5-*`, có nhóm **verb cấp cao** gọn hơn: `vkmql-new`,
`vkmql-check`, `vkmql-ship` và `mql5-new / mql5-check / mql5-flow /
mql5-ship-flow`. Liệt kê máy đọc được: `mql5-manifest --emit > manifest.json`.

**Discovery (4):** `mql5-scan`, `mql5-survey`, `mql5-doctor` (`--soft`),
`mql5-audit`. Wizard: `mql5-init` (`--non-interactive` / `--from-answers`).

**Plan (generators):** `mql5-rri`, `mql5-vision`, `mql5-blueprint`, `mql5-tip`,
`mql5-vision-gen`, `mql5-blueprint-gen`, `mql5-tip-gen`, `mql5-contract-gen`,
`mql5-verify-report`, `mql5-permission-layer5`, `mql5-task-graph-gen`,
`mql5-completion-report`, `mql5-escalation`.

**Build (9):** `mql5-build`, `mql5-auto-build`, `mql5-auto-fix`,
`mql5-spec-from-prompt`, `mql5-project-gen`, `mql5-ea-compose`,
`mql5-architecture-check`, `mql5-dashboard`, `mql5-wizard`. Phụ trợ:
`mql5-pip-normalize`, `mql5-async-build`, `mql5-onnx-export`, `mql5-onnx-embed`,
`mql5-llm-context`, `mql5-forge-init`, `mql5-docs-bundle`,
`mql5-docs-assemble`.

**Verify (12):** `mql5-compile`, `mql5-compile-runner`, `mql5-compile-repair`,
`mql5-lint` (`--use-ast`, `--format sarif`), `mql5-method-hiding-check`,
`mql5-backtest`, `mql5-tester-ini`, `mql5-test-runner`/`mql5-tester-run`,
`mql5-optimize-run`, `mql5-walkforward`, `mql5-monte-carlo`,
`mql5-overfit-check`, `mql5-multibroker`, `mql5-fitness`, `mql5-mfe-mae`,
`mql5-bt-sim`, `mql5-ap-policy`, `mql5-ml-validate`, `mql5-evidence-matrix`.

**Deep-review:** `mql5-ea-deep-review` (alias `mql5-ea-audit`) + các lệnh EA
review/intake: `mql5-ea-senior-review`, `mql5-ea-scan`/`mql5-scan-ea`,
`mql5-ea-patterns`, `mql5-ea-intake`, `mql5-ea-llm-review-pack`/`-run`,
`mql5-ea-auto-llm-review`, `mql5-ea-chat-review-pack`/`-workflow`,
`mql5-ea-review-report`, `mql5-ea-doc-verify`.

**RRI (3 alias):** `mql5-rri-bt`, `mql5-rri-rr`, `mql5-rri-chart`, `mql5-rri-run`.

**Review (5):** `mql5-review`, `mql5-eng-review`, `mql5-ceo-review`,
`mql5-cso`, `mql5-investigate`, `mql5-second-opinion`.

**Contract (Chủ–Thầu–Thợ):** `mql5-owner-interview`, `mql5-contract-blueprint`,
`mql5-blueprint-tip`, `mql5-owner-approve`, `mql5-contract-build`,
`mql5-role-guard`, `mql5-role-state`, `mql5-gate-escalate`, `mql5-refine-tip`.

**Deploy (3):** `mql5-deploy-vps`, `mql5-cloud-optimize`, `mql5-canary`.

**Ship (4):** `mql5-forge-pr`, `mql5-package`, `mql5-ship`, `mql5-refine`.
Maintainer: `mql5-dist`, `mql5-ship-flow`, `mql5-verify-evidence`,
`mql5-agent-contract`, `mql5-manifest`, `mql5-fixture`, `mql5-forge-loop`,
`mql5-selftest`, `mql5-version`.

**Other (4):** `mql5-broker-safety`, `mql5-trader-check`, `mql5-permission`,
`mql5-install`.

> 12 gate hỗ trợ `--json` (envelope `schema_version=1`) và `--gate-report <path>`
> để matrix collector thu nhận: `mql5-lint`, `mql5-trader-check`,
> `mql5-broker-safety`, `mql5-permission`, `mql5-backtest`, `mql5-walkforward`,
> `mql5-monte-carlo`, `mql5-multibroker`, `mql5-overfit-check`, `mql5-mfe-mae`,
> `mql5-doctor`, `mql5-audit`. `--format sarif`: `mql5-lint`,
> `mql5-method-hiding-check`.

---

## 16. Deploy lên VPS

`mql5-deploy-vps` emit checklist MetaQuotes Native VPS (migration **không**
scriptable — nằm sau broker login + UI tài khoản MetaQuotes).

**Pre-flight:** EA pass Layer-7 (broker-safety); Trader-17 ≥ 15/17 ENTERPRISE;
chạy demo ≥ 5 ngày equity ổn định; commit file `.set`.

**Activation:** terminal → chuột phải chart → *Register a Virtual Server* →
MetaQuotes-ID-Server → chọn **MetaQuotes Native VPS** → data center gần engine
broker → *Migrate Experts and Indicators* → trả phí.

**Post:** xác nhận icon VPS xanh; EA xuất hiện trong Experts list của VPS; chạy
`mql5-canary <EA>.ex5 --duration 30m`; trong 24h kiểm equity VPS khớp local ±0.1%.

**Giới hạn đã biết:** ONNX model > 50MB có thể bị từ chối migration (tách model
hoặc dùng Python sidecar); `WebRequest` tới host chưa whitelist sẽ fail im lặng
trên VPS; `OrderSendAsync`+`OnTradeTransaction` chạy được nhưng callback có thể
trễ ~1 tick do network jitter.

---

## 17. Troubleshooting & FAQ

**`wine: command not found` / `metaeditor-bin: not found`** → chạy
`./scripts/setup-wine-metaeditor.sh` (Linux); hoặc dùng `mql5-doctor --soft` +
`mql5-bt-sim` để làm việc không cần Wine.

**Compile báo `metaeditor build < 5260`** → cập nhật MetaEditor; method-hiding
linter sẽ là ERROR ở build ≥ 5260, WARN ở build thấp hơn.

**`spec_validate` báo `unknown top-level key`** → key không thuộc 8 block hợp lệ
(§6); sửa lại tên block.

**`auto_build`/permission fail ở layer 5 (methodology)** → thiếu sign-off
(`APPROVED by …` trên blueprint, `CONFIRM by …` trên contract). Bổ sung rồi
chạy `mql5-permission-layer5 --enforce-sign-off`.

**Permission layer 2 fail trên Linux không Wine** → đúng hành vi (gate không
lặng lẽ skip compile). Cài Wine hoặc dùng remote worker (§9).

**`forge.pr.create` trả dry-run thay vì PR thật / `forge_init` 401** → thiếu
token Algo Forge; cấu hình secret rồi chạy lại.

**Backtest không tạo report** → kiểm `tester.ini` (đường dẫn `.ex5`, symbol, khung
thời gian, khoảng ngày) và `$MQL5_TERMINAL_PATH`.

**Package bị block** → thiếu `evidence/manifest.json release_eligible=true` hoặc
thiếu bộ bundle LLM (`docs/docs-context.json` + `docs/docs-prompt.md`). Tạo evidence thật + docgen rồi package lại.

**Test ONNX e2e fail** → PyTorch chưa cài; cài torch hoặc bỏ qua nhánh ONNX.

**AI agent gọi MCP nhưng không thấy tool** → kiểm cấu hình MCP server (§12) và
kit đã `pip install -e` trong đúng venv.

---

### Khi nào cần bản full maintainer?

Bản slim này tối ưu cho **build EA + dùng với LLM/agent an toàn**. Cần bản full
khi bạn là maintainer và cần: unit/regression test nội bộ, fixtures/golden
dataset, examples/sample report, reference docs, CI/dev container, plan/spec phát
triển tool.
