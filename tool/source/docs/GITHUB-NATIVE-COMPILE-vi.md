# GitHub Native Compile Backend — VibeCodeKit MQL5 RC7

Tài liệu này mô tả backend biên dịch MQL5 native Windows bằng GitHub Actions. Backend được thiết kế để giải quyết trường hợp agent/CI chạy trên Linux hoặc sandbox không có MetaEditor nhưng vẫn cần bằng chứng compile Windows thật.

## 1. Nguyên tắc

GitHub Actions là **execution backend**, không phải release bypass.

Luồng chuẩn:

```text
vkmql-check compile
  -> backend router
  -> GitHub Actions windows-2022
  -> ProbeEA
  -> stage project source
  -> MetaEditor64.exe
  -> compile-log.txt + ea.ex5 + result.json
  -> SHA-256/size verification
  -> provenance validation
  -> compile evidence
```

Compile PASS không đồng nghĩa backtest/forward/live PASS.

## 2. Backend router

Surface duy nhất cho agent và người dùng:

```bash
vkmql-check compile MQL5/Experts/MyEA/MyEA.mq5 --backend auto
```

Thứ tự `auto`:

1. native Windows local MetaEditor;
2. GitHub Actions Windows đã cấu hình đầy đủ;
3. remote Windows worker đã cấu hình;
4. Wine MetaEditor cho development/diagnostic;
5. không có backend -> `UNTESTABLE`.

Chọn GitHub rõ ràng:

```bash
vkmql-check compile MQL5/Experts/MyEA/MyEA.mq5 \
  --backend github-actions \
  --project-root . \
  --github-repo OWNER/REPO \
  --github-ref main \
  --github-commit <40-char-commit-sha> \
  --out evidence/compile \
  --json
```

Token có thể truyền bằng `--github-token`, hoặc môi trường:

- `VKMQL_GITHUB_TOKEN`
- `GITHUB_TOKEN`
- `GH_TOKEN`

Repo/ref có thể dùng:

- `VKMQL_GITHUB_REPOSITORY` / `GITHUB_REPOSITORY`
- `VKMQL_GITHUB_REF` / `GITHUB_REF_NAME`

## 3. Cấu hình repository GitHub

Workflow RC7 của kit sử dụng hai repository secrets:

- `MT5_INSTALLER_URL`: HTTPS URL tới installer MT5 phù hợp với môi trường kiểm thử.
- `MT5_INSTALLER_SHA256`: khuyến nghị bắt buộc ở môi trường release; pin SHA-256 installer.

Nếu `MT5_INSTALLER_URL` không tồn tại, native Windows job phải `SKIPPED` và được xem là `UNTESTABLE`. Fast/static gate vẫn có thể PASS nhưng không được diễn giải thành native compile PASS.

Không lưu credential broker, account giao dịch hoặc live-trading secret trong compile workflow.

## 4. Reusable action

Action canonical nằm tại:

```text
.github/actions/mql5-native-compile/
```

Consumer project có template:

```text
vibecodekit_mql5/resources/github/native-compile.workflow.template.yml
```

Khi dùng action từ repo khác phải thay `<PINNED_VKMQL_COMMIT_SHA>` bằng commit SHA 40 ký tự đã review. Không dùng floating `main`/tag làm trust boundary cho release evidence.

## 5. Compile house policy

Tất cả backend dùng cùng policy:

- `Result:` bắt buộc xuất hiện trong MetaEditor log;
- errors = `0`;
- warnings = `0` mặc định;
- `.ex5` bắt buộc tồn tại;
- stale log và stale `.ex5` bị xóa trước run;
- không lấy MetaEditor process exit code làm bằng chứng duy nhất.

Failure taxonomy chính:

- `TOOLCHAIN_INSTALL_FAILED`
- `TOOLCHAIN_PROBE_FAILED`
- `SOURCE_STAGE_FAILED`
- `COMPILE_ERRORS`
- `COMPILE_WARNINGS`
- `LOG_MISSING`
- `RESULT_MISSING`
- `EX5_MISSING`
- `ARTIFACT_HASH_MISMATCH`
- `SOURCE_BINDING_MISMATCH`
- `INVOCATION_FAILED`
- `TIMEOUT`

## 6. ProbeEA

Trước target thật, runner compile một EA tối thiểu.

Nếu ProbeEA thất bại, trạng thái là lỗi toolchain/installer/MetaEditor chứ không kết luận code EA chính bị lỗi.

Điều này tách:

```text
TOOLCHAIN_PROBE_FAILED
```

khỏi:

```text
COMPILE_ERRORS / COMPILE_WARNINGS
```

## 7. Generic staging

Backend không biết tên EA/project demo.

Nếu project có `MQL5/`, runner staging nội dung đó vào MQL5 tree tạm.

Nếu project có `Experts/`, `Include/`, `Indicators/`, `Libraries/`, `Scripts/`, runner staging các tree chuẩn.

Nếu project self-contained, runner đặt source dưới `MQL5/Experts/__vkmql_project/` và giữ cấu trúc tương đối.

Các thư mục như `.git`, `.venv`, `__pycache__`, `evidence` không được copy vào compiler staging.

## 8. Encoding

File `.mq5` và `.mqh` được đọc từ source và tạo **temporary staging copy** UTF-16 LE BOM cho MetaEditor.

Repo source không bị rewrite.

Evidence giữ:

- original source SHA-256;
- staged SHA-256;
- original encoding;
- compiler encoding;
- transformation = `encoding_only`.

## 9. Standard-library warm-up

`warm-stdlib` có ba mode:

- `auto`: chỉ warm terminal khi target có angle include và standard-library header cần thiết chưa tồn tại;
- `always`: luôn warm;
- `never`: không warm.

Mục tiêu là tránh startup MT5 không cần thiết cho project self-contained.

## 10. Multi-target compile

Reusable action nhận `targets-json` để compile nhiều target trong một lần cài MT5.

Ví dụ logical plan:

```json
[
  {"id":"ea","source":"MQL5/Experts/MyEA/MyEA.mq5","required":true},
  {"id":"tests","source":"MQL5/Scripts/MyEA/RunTests.mq5","required":false}
]
```

Mỗi target có log/EX5 riêng; target đầu tiên là canonical primary compile artifact.

## 11. Evidence schema

`evidence/compile/result.json` bao gồm tối thiểu:

- `source = github_actions_metaeditor`;
- `status`, `ok`, `error_count`, `warning_count`, `failure_codes`;
- target + target/staged/log/EX5 SHA-256;
- source commit + source tree SHA;
- runner OS/arch;
- GitHub repository/run id/job id/workflow ref;
- MetaEditor path/version;
- ProbeEA status;
- artifact descriptors (filename, role, SHA-256, size);
- provenance block.

Canonical artifacts:

```text
evidence/compile/
  result.json
  compile-log.txt
  ea.ex5
  toolchain/
  targets/
```

## 12. Provenance gate

`github_actions_metaeditor` không trusted chỉ vì string source đúng.

Validator yêu cầu:

- Windows runner;
- PASS 0/0;
- ProbeEA PASS;
- full source commit/tree SHA;
- positive numeric run/job id;
- exact repository binding;
- correlated dispatch request;
- job id thuộc đúng workflow run;
- safe artifact relative paths;
- không duplicate artifact filename;
- SHA-256/size của file tải về khớp descriptor;
- target/log/EX5 hashes hợp lệ.

ZIP artifact có traversal hoặc symlink bị reject trước khi commit file vào evidence destination.

## 13. Không ghi CI result ngược vào source branch

Compile workflow không commit `RESULT.md` hoặc EX5 vào branch chỉ để báo trạng thái.

Dùng:

- GitHub Job Summary;
- GitHub Actions artifact;
- `evidence/` pipeline;
- release attestation khi toàn bộ release stages đã đủ.

Điều này tránh tạo commit mới làm source SHA khác với source đã compile.

## 14. Release semantics

Native compile có thể tạo compile authority, nhưng release vẫn cần các gate tương ứng với target level.

Đặc biệt với EA có behavior/risk/execution change:

```text
native compile
  + Strategy Tester
  + quality/stress
  + restart/recovery
  + review
  + artifact hashes
  + attestation
```

mới có thể tiến tới release eligibility.

RC7 chỉ đưa GitHub **native compile backend** vào canonical kit. GitHub Strategy Tester là phase kế tiếp, không được giả lập trong RC7.

## 15. Kiểm tra capability

`detect_capabilities()` schema 1.1 chỉ liệt kê `github_actions_metaeditor` khi repository + ref + token được cấu hình đầy đủ.

Partial configuration được ghi trong `limitations`, không được coi là READY.

Trong môi trường không có local MetaEditor nhưng GitHub backend đã đủ config, agent có thể dùng `vkmql-check compile --backend github-actions` mà không cần Wine/local MT5.
