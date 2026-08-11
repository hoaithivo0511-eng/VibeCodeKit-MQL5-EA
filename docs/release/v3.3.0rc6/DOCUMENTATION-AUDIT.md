# Audit đồng bộ tài liệu — VibeCodeKit MQL5 v3.3.0rc6

Ngày audit: 2026-08-11

Trạng thái: **PARTIAL / cần candidate kế tiếp để sửa tài liệu đóng gói**

## Phạm vi và nguyên tắc

Audit đã duyệt 202 file Markdown/HTML/RST hiện hữu được Git theo dõi, gồm tài
liệu ở root, `docs/`, `native/`, `reports/`, `demo/` và `tool/source/`. Lần
kiểm tra cuối bao phủ 203 file sau khi thêm chính báo cáo này. File sinh ra từ
build/cache không nằm trong phạm vi tài liệu phát hành.

Phân loại được áp dụng như sau:

- tài liệu RC4/RC5, changelog và report kiểm thử cũ là bằng chứng lịch sử bất
  biến; số version và kết quả test cũ trong các file này không phải lỗi;
- tài liệu active phải mô tả đúng v3.3.0rc6 và trạng thái fail-closed hiện tại;
- tài liệu nằm trong `tool/source/` là một phần của source tree candidate đã
  đóng băng. Mọi thay đổi tại đây làm thay đổi source tree, source ZIP, wheel,
  manifest và checksum, nên phải đi qua một candidate có version/danh tính mới.

## Kết quả theo bề mặt tài liệu

| Bề mặt | Kết quả | Nhận xét |
|---|---|---|
| `README.md` ở root | PASS sau cập nhật | Đã chuyển sang tiếng Việt, giữ nguyên hash, gate và trạng thái `release_eligible=false`. |
| `STRUCTURE.md` | PASS | Mô tả đúng RC6, source tree đóng băng và Task 18 còn chặn production. |
| `docs/release/v3.3.0rc6/` | PASS | Plan, Task 11–19, checksum và pre-release notes nhất quán với candidate hiện tại. |
| `native/NATIVE-VALIDATION-HANDOFF.md` | PASS | Đúng version RC6 và không tuyên bố native gate đã đạt. |
| Tài liệu RC4/RC5 và report cũ | PASS/HISTORICAL | Giữ nguyên để bảo toàn bằng chứng và diễn tiến phát hành. |
| Tài liệu active trong `tool/source/` | **DEBT** | Có version/số lượng lệnh/kết quả test lỗi thời và link nội bộ bị gãy; chưa sửa trong RC6 vì source tree và tag đã đóng băng. |

## Sai lệch active đã xác nhận

| Mức | File | Sai lệch được xác nhận | Giá trị RC6 cần dùng |
|---|---|---|---|
| P1 | `tool/source/docs/COMMANDS.md` | Tiêu đề và nội dung ghi 138 lệnh, đồng thời gắn catalog với v3.1 RC2. | Catalog RC6 có 139 entry point công khai. |
| P1 | `tool/source/docs/USAGE-en.md` | Ghi v2.4.3, 118 lệnh, gọi `COMMANDS.md` là tài liệu 43 lệnh; hai link đến `references/` và example portfolio không tồn tại. | Phải định danh v3.3.0rc6, 139 lệnh và trỏ đến tài nguyên có thật. |
| P1 | `tool/source/docs/USER-GUIDE-en.md` | Ghi baseline v2.4.3, 118 lệnh, 38 test và selftest 8/8. | RC6 hiện có catalog 139 lệnh, 252 test parity và selftest 13/13. |
| P1 | `tool/source/docs/CODEX-SETUP-PROMPT.md` | Tiêu đề v3.0-alpha.3, ví dụ bundle v2.6.1 và yêu cầu selftest 10/10. | Phải dùng v3.3.0rc6, tên bundle RC6 và selftest 13/13. |
| P2 | `tool/source/README.md` | Phần mở đầu trình bày v3.1 RC2 như mô tả của bản hiện hành. | Cần tách rõ lịch sử v3.1 khỏi trạng thái và tính năng RC6. |
| P2 | `tool/source/docs/DOC-MAP.md` | Chưa phân loại rõ các HTML audit/UI report là snapshot lịch sử. | Phải ghi rõ report lịch sử không đại diện verdict RC6. |
| P1 | 11 file `tool/source/scripts/vibecodekit_mql5/resources/scaffolds/*/*/README.md` | Có tổng cộng 22 link tương đối đến `docs/COMMANDS.md` và `docs/QUICKSTART.md` bị gãy sau khi scaffold được sao chép vào package resources. | Đồng bộ resource với link phù hợp vị trí đóng gói hoặc dùng link repository ổn định. |

Link scan tương đối ghi nhận tổng cộng 24 tham chiếu bị gãy; không có link gãy
trong README root hoặc tài liệu release/native RC6. Các URL bên ngoài không
được dùng làm bằng chứng release và không nằm trong verdict này.

Các tài liệu đặt tên theo version như `EA-IR-COMPILER-v3.1-vi.md`, changelog,
report RC4/RC5 và nội dung compatibility v2.6/v2.6.1 được xác định là lịch sử
có chủ đích, không phải lỗi cần thay version hàng loạt.

## Quyết định phát hành

Không sửa các file trên trực tiếp vào tag/pre-release `v3.3.0rc6`, vì làm vậy
sẽ khiến tài liệu trong source tree không còn khớp với artifact và checksum đã
phát hành. Không được retag hoặc ghi đè artifact RC6.

Candidate kế tiếp phải thực hiện một task documentation-sync riêng:

1. sửa các bề mặt active đã liệt kê và đồng bộ 11 bản sao resource đóng gói;
2. thêm contract test lấy version và số lệnh từ metadata/catalog thay vì ghi
   cứng trong tài liệu;
3. dựng lại source ZIP, wheel và bundle với tên/version mới;
4. chạy lại source/archive/wheel parity, selftest và hygiene;
5. phát hành tag/pre-release mới, giữ RC6 bất biến.

## Trạng thái sử dụng

RC6 vẫn phù hợp để team tester kiểm thử theo phạm vi pre-release. Audit tài liệu
không thay đổi release predicate: `release_eligible=false`; MetaEditor, MT5
Strategy Tester và restart/recovery của Task 18 vẫn PENDING, vì vậy chưa được
quảng bá RC6 là production-ready.
