# VibeCodeKit-MQL5-EA

Kho lưu trữ mã nguồn và bằng chứng kiểm thử của **VibecodeKit MQL5 EA v3.3.0rc4** (bản `runtime-safety-fix-bundle`).

Toàn bộ nội dung được giải nén nguyên trạng từ gói `VibecodeKit-MQL5-v330rc4-runtime-safety-fix-bundle.zip`. Gói ZIP gốc được giữ lại ở thư mục gốc để đối chiếu byte-for-byte.

## Cấu trúc

| Đường dẫn | Số tệp | Nội dung |
|---|---:|---|
| `demo/` | 154 | Golden fixture `CCBSN_GoldenFixture`, IR, build plan và bộ `generic-acceptance` (BandReturn, NorthTrend, OrionRecovery, RangePulse) |
| `reports/` | 19 | Báo cáo lint, architecture, contract, coverage, deep-review, build report, acceptance |
| `native/` | 4 | Tài liệu bàn giao xác minh native và worker Windows |
| `tool/` | 3 | Wheel `vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl`, source ZIP đầy đủ và manifest |
| Thư mục gốc | 9 | `BUNDLE-MANIFEST.json`, `SHA256SUMS.txt`, `UPDATE-SUMMARY.json`, `FIX-TRACEABILITY.csv`, `PHASE-TEST-LEDGER.csv`, báo cáo fix tiếng Việt, manifest tải lên và gói ZIP gốc |

Tổng: **187 tệp**, **7.062.979 byte**.

## Trạng thái phiên bản v3.3.0rc4

Trích từ `UPDATE-SUMMARY.json`:

| Gate | Kết quả |
|---|---|
| Source regression | 126/126 PASS |
| Source selftest | 13/13 PASS |
| Wheel regression | 126/126 PASS |
| Wheel selftest | 13/13 PASS |
| Source archive regression | 126/126 PASS |
| Generic cross-project acceptance | 4/4 PASS |
| MetaEditor compile | Chưa xác minh |
| MT5 Strategy Tester | Chưa xác minh |
| `release_eligible` | **false** |

Statement coverage tổng thể: **18,23%**. Các module trọng yếu cao hơn: `advanced_codegen` 95,43%, `feature_registry` 94,59%, `safe_paths` 94,74%, `ea_ir` 93,94%, `build_planner` 91,67%.

CCBSN chỉ là golden acceptance fixture, không phải template mặc định của tool.

## Xác minh toàn vẹn

```bash
# Đối chiếu toàn bộ tệp trong kho với manifest
sha256sum -c UPLOAD-MANIFEST.sha256

# Đối chiếu gói ZIP gốc
sha256sum VibecodeKit-MQL5-v330rc4-runtime-safety-fix-bundle.zip
# Kỳ vọng: 33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c

# Đối chiếu theo manifest của chính bundle
sha256sum -c SHA256SUMS.txt
```

`UPLOAD-SUMMARY.json` ghi lại kết quả kiểm tra giải nén: 259 mục ZIP, 186 tệp, 73 thư mục, 0 tệp thiếu, 0 tệp sai hash, 0 symlink, 0 đường dẫn không an toàn.

## Lưu ý kỹ thuật

- `.gitattributes` đặt `* -text` để Git không chuyển đổi CRLF/LF, giữ nội dung khớp tuyệt đối với gói gốc.
- Ba tệp nhị phân: hai gói `.zip` và một `.whl`.
- Không commit `.env`, token hoặc khóa API vào kho này.

## Cài đặt tool

```bash
pip install tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl
```
