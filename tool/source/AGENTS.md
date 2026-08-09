# Agent Instructions – Slim v2 LLM-safe

## Mục tiêu

Khi dùng package này để build EA, agent phải ưu tiên flow thật và evidence thật, không dùng sample/reference để claim pass.

## Không được claim

Không nói:

```text
all tests passed
production ready
release eligible
ready for live trading
```

trừ khi có `evidence/manifest.json` với:

```json
{
  "release_eligible": true
}
```

và có hash artifact liên quan.

## Các thư mục maintainer không thuộc bản slim

Bản phân phối slim do `mql5-dist` tạo sẽ loại bỏ (source checkout có thể vẫn
giữ các thư mục này để chạy test nội bộ):

```text
docs/agent-prompts/
docs/references/
docs/reference-ea/
examples/
tests/fixtures/
tests/gates/
evidence/
vck-retro-*/
```

Không được hướng dẫn user mở/chạy các path trên trong bản slim.

## Các phần RRI cần giữ

```text
docs/rri-personas/
docs/rri-templates/
```

Đây là template/workflow input. Không xem chúng là kết quả kiểm định.

## Deep review / audit một EA code-base có sẵn (1 lệnh)

Khi user yêu cầu bằng ngôn ngữ tự nhiên, ví dụ:

```text
hãy dùng tool scan deep review mã EA này cho tôi
deep review / audit code base EA này
rà soát toàn bộ code EA, tìm dead code, hàm/biến không dùng, lỗi logic
```

Agent CHỈ chạy MỘT lệnh duy nhất — không cần nhớ nhiều lệnh con:

```bash
mql5-ea-deep-review <path-to-ea.mq5 | path-to-project-dir>
# alias: mql5-ea-audit
# thêm --json để lấy envelope agent-contract, --fast để bỏ Stage-7 line review
```

Lệnh này tự chạy toàn bộ pipeline (Stage 0→7) rồi xuất 1 report hợp nhất
(`_deep_review/deep-review.md` + `.json` + `.docx`):

- Stage 0: parse + symbol graph (mq5_symbols)
- Stage 1: static scan / signals (scan_ea)
- Stage 2: anti-pattern lint (lint + best-practice)
- Stage 3: structure & complexity (structure_audit)
- Stage 4: dead-code / dead-logic (deadcode)
- Stage 5: senior review — risk/execution/state/release (ea_senior_review)
- Stage 6: modernization advisor MQL5 2024–2026 (modernize)
- Stage 7: chuẩn bị grounded line-review paste-pack (`line_review`). Bản thân
  stage này không tuyên bố đã có LLM verdict; `--fast` ghi rõ `SKIPPED` và loại
  Stage 7 khỏi danh sách category đã kiểm tra.

Không được tách thành nhiều lệnh thủ công cho user; pipeline đã gói trong 1 lệnh.

## Flow an toàn

1. Tạo/scaffold EA từ spec.
2. Lint/static scan.
3. Compile nếu có MetaEditor/MT5.
4. Backtest hoặc parse report, nhưng parse report import không tự tạo release eligibility.
5. Permission gate.
6. Kiểm `evidence/manifest.json`.
7. Chỉ package release khi `release_eligible=true`.

## Flag không an toàn

```text
--draft
--no-compile
--no-gate
--unsafe-allow-skips
```

Khi thấy các flag này, phải xem output là draft/diagnostic, không phải release.
