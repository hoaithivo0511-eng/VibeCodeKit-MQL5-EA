# Audit đồng bộ tài liệu — VibeCodeKit MQL5 v3.3.0rc6

Ngày audit: 2026-08-11

Trạng thái: **PASS / RESOLVED**

Release predicate: **`release_eligible=false` / native evidence PENDING**

## Phạm vi và nguyên tắc

Audit cuối duyệt 204 file Markdown/HTML/RST được Git theo dõi tại root,
`docs/`, `native/`, `reports/`, `demo/` và `tool/source/`. Tài liệu RC4/RC5,
changelog và report kiểm thử cũ được giữ nguyên như bằng chứng lịch sử; tài
liệu active phải mô tả đúng RC6 và không được suy diễn Python/static PASS thành
native MT5 PASS.

Tag tester pre-release `v3.3.0rc6` giữ nguyên candidate Task 17 ban đầu. Task 20
tạo lại candidate documentation-sync từ build input
`3d83321e48196ec8b5ea165afaf05412406d99ff`, source tree
`507eb8dae02a47d41a86d224fc8d4d567d06c691`; không retag hoặc ghi đè asset của
pre-release cũ.

## Đối chiếu phát hiện và kết quả xử lý

| Mức | Phát hiện ban đầu | Kết quả Task 20 |
|---|---|---|
| P1 | `COMMANDS.md` ghi 138 lệnh và gắn catalog hiện hành với v3.1 RC2 | Đã đồng bộ RC6 và 139 entry point; hygiene đối chiếu trực tiếp catalog với `pyproject.toml`. |
| P1 | `USAGE-en.md` ghi v2.4.3/118 lệnh và có link/tài nguyên không tồn tại | Đã định danh v3.3.0rc6/139 lệnh và thay toàn bộ target gãy bằng tài nguyên có thật. |
| P1 | `USER-GUIDE-en.md` ghi 38 test, selftest 8/8 và MCP inventory cũ | Đã cập nhật RC6, selftest 13/13, 4 MCP server/30 bridge tool và dùng catalog có thẩm quyền thay phụ lục đếm tay. |
| P1 | `CODEX-SETUP-PROMPT.md` ghi v3.0-alpha.3, bundle v2.6.1 và selftest 10/10 | Đã cập nhật v3.3.0rc6, source ZIP RC6 và 13/13. |
| P2 | `tool/source/README.md` trình bày v3.1 RC2 như bản hiện hành | Đã tách mốc giới thiệu v3.1 khỏi baseline RC6 hiện hành. |
| P2 | `DOC-MAP.md` chưa phân loại report UI/audit cũ | Đã thêm nhóm historical snapshot và cảnh báo không dùng verdict cũ cho RC6. |
| P1 | 11 scaffold README và 11 resource copy có 22 link phụ thuộc vị trí | Đã dùng target repository ổn định; canonical/resource parity byte-for-byte PASS. |
| P1 | MCP `docs.ea_render` import module runtime không tồn tại | Đã khôi phục renderer tương thích và contract test; 30-tool bridge smoke PASS. |
| P1 | Wheel build có thể thu gom cache không được Git theo dõi | Builder chỉ xuất file Git-tracked vào staging sạch; double-build byte-for-byte PASS. |
| P2 | Test snapshot thất bại khi `pip` tạo sẵn `__pycache__` | Verifier bỏ qua cache runtime và test chấp nhận thư mục đã tồn tại; installed-wheel 254/254 PASS. |

## Kết quả xác định

- 204 file tài liệu được scan; **0 link tương đối bị gãy**.
- 139/139 command trong catalog khớp `[project.scripts]`.
- 11/11 scaffold README khớp bản resource đóng gói.
- MCP bridge load đủ 30 tool; `docs.ea_render` tạo HTML/Markdown và báo lỗi rõ
  nếu tùy chọn PDF chưa có dependency.
- Live source, source ZIP và installed wheel đều đạt 254/254 test, selftest
  13/13; canonical snapshot đạt 48/48 file.
- Wheel tái tạo byte-for-byte với SHA-256
  `4c98c71f66c185b24f526034d9df7d7484e25fa2164e7af87225b230397cf408`.

## Danh tính candidate hiện hành

```text
166462a71b14a0e9623b2cac8aa9c7a316d0b7a7318fb4663ee026dd221fa5f9  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
6fca0b2424008279044a37e9c39a4a5df4099af5e7fd1e364ce98109494b3eaa  tool/vibecodekit-mql5-v3.3.0rc6-source-full.manifest.json
4c98c71f66c185b24f526034d9df7d7484e25fa2164e7af87225b230397cf408  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
10ea6d8bdaf1a43cee370dce93d3c010bb436c1cd597fbb84ec2440d37a2dc  docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json
1b3cfec599a09a9adb3075c74d38d87058d4a056ff9183d7ac5dc3240e5e4a52  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

## Quyết định sử dụng

Candidate đã sẵn sàng tích hợp vào `main` và bàn giao tester theo phạm vi
fail-closed. Nó **chưa sẵn sàng production/live trading**: compile MetaEditor,
MT5 Strategy Tester, restart/recovery và runner trust của Task 18 vẫn PENDING.
