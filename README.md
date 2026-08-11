# VibeCodeKit-MQL5-EA

Kho hardening dành cho **VibeCodeKit MQL5 EA v3.3.0rc6**. Task 17 đã đóng
băng một candidate xác định theo nguyên tắc fail-closed từ cây mã nguồn
`tool/source/` hiện hành. Đây **chưa phải bản phát hành production** cho đến
khi bằng chứng native đáng tin cậy được liên kết đầy đủ và điều kiện promotion
của Task 19 được đáp ứng.

> Trạng thái phát hành: **candidate-integrated / `release_eligible=false`**.
> Artifact RC4 và RC5 được giữ lại như lịch sử bất biến. RC6 đã hoàn tất parity
> giữa source, source ZIP và wheel, nhưng điều kiện production vẫn bị chặn do
> chưa có bằng chứng MetaEditor, MT5 Strategy Tester và restart/recovery đáng
> tin cậy.

Pre-release dành cho tester: [v3.3.0rc6](https://github.com/hoaithivo0511-eng/VibeCodeKit-MQL5-EA/releases/tag/v3.3.0rc6).

## Cấu trúc repository

| Đường dẫn | Mục đích |
|---|---|
| `tool/source/` | Mã nguồn hardening v3.3.0rc6 đang hoạt động; chỉ sinh candidate artifact sau khi các gate triển khai đã đạt. |
| `tool/*.whl` | Wheel RC4/RC5 lịch sử và wheel candidate RC6 có tên riêng sau Task 17. |
| `tool/*-source-full.zip` | Source archive RC4/RC5 lịch sử và source candidate RC6 có tên riêng sau Task 17. |
| `demo/` | Fixture chuẩn CCBSN và fixture nghiệm thu chéo cho project tổng quát. CCBSN là bằng chứng kiểm thử, không phải template mặc định. |
| `reports/` | Bằng chứng lịch sử; bằng chứng RC6 phải được tạo lại và không được tái sử dụng verdict cũ. |
| `native/` | Tài liệu bàn giao kiểm thử native MetaEditor/MT5 và tài nguyên cho Windows worker. |
| `docs/release/` | Lịch sử RC4/RC5 bất biến cùng plan, ledger và native runbook của RC6. |
| `docs/maintenance/` | Quy trình bảo trì repository, tách biệt với tài liệu phát hành cho người dùng. |
| `scripts/maintenance/` | Công cụ hỗ trợ bảo trì repository; không tự động commit hoặc push. |
| `.github/workflows/` | Gate CI xác định cho regression mã nguồn, parity artifact và vệ sinh repository. |

Xem `STRUCTURE.md` để biết chính sách cây thư mục theo định hướng phát hành.
README này không ghi cứng số lượng file/byte vì chúng dễ lỗi thời;
`REPO-MANIFEST.sha256` là inventory toàn vẹn có thẩm quyền sau khi hoàn tất
release-prep.

## Trạng thái xác định của RC4 đã đóng băng

Gói RC4 đã audit có kết quả:

| Gate | Trạng thái |
|---|---|
| Regression mã nguồn | 126/126 PASS |
| Selftest mã nguồn | 13/13 PASS |
| Regression wheel | 126/126 PASS |
| Selftest wheel | 13/13 PASS |
| Regression source archive | 126/126 PASS |
| Nghiệm thu chéo project tổng quát | 4/4 PASS |
| Biên dịch native bằng MetaEditor | PENDING / chưa được chứng minh trong môi trường repository này |
| MT5 Strategy Tester | PENDING / chưa được chứng minh trong môi trường repository này |
| Đủ điều kiện phát hành production | **false cho đến khi có bằng chứng native** |

Bằng chứng coverage lịch sử ghi nhận statement coverage toàn package là
18,23%; các module trọng yếu có coverage cao hơn đáng kể. Coverage là chỉ số
về khả năng bảo trì, không phải bằng chứng về tính đúng đắn của giao dịch.

## Danh tính artifact RC4 cố định

Các hash sau đã đóng băng cho bộ artifact RC4. Công việc RC6 không được âm thầm
thay đổi hoặc ghi đè chúng:

```text
33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip
a8e091caf35b59fbf436d10c5c8e1dc0414d3e355d029162295192c02029566f  tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip
5945a91c9f2b74ee3bbe3a7977991445d3e95885e396c3f95a14262ac8eb127a  tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl
```

Artifact RC4 và RC5 tiếp tục là dữ liệu lịch sử bất biến. Cây
`tool/source/` của RC6 đã được đóng băng tại Task 17 với source tree
`53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`; source ZIP và wheel RC6 đều đạt
cùng bộ 252 test và selftest 13/13 trên cả ba kênh.

## Danh tính candidate RC6 fail-closed

```text
3bc4ce857613c7f82f2aecb0648b84e1971939f282a1fd056d93440d21305059  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
a2ba69f0b568d7362017d3e81f28feea80ddb71f33494989089c4669136578d6  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
f13cc038ce6187543e6e556b257ec109990a3646c3c16eea8ca67489c1ac9396  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

Các hash này nhận diện một candidate đã tích hợp package, không phải bản phát
hành production. `release_eligible` vẫn là `false` cho đến khi Task 18 và
Task 19 đạt.

## Kiểm tra xác định tại máy local

```bash
# Kiểm thử mã nguồn
cd tool/source
python -m pip install -e '.[dev]'
python -m pytest -q
mql5-selftest
cd ../..

# Kiểm tra hash artifact RC4 đã đóng băng
printf '%s  %s\n' \
  33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c \
  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip | sha256sum -c -
```

GitHub Actions chạy regression mã nguồn RC6 độc lập với kiểm tra toàn vẹn
artifact RC4 đã đóng băng. Workflow tích hợp package RC6 kiểm tra canonical
snapshot, wheel tái tạo xác định, parity giữa source/archive/wheel và metadata
candidate fail-closed.

## An toàn và ngữ nghĩa phát hành

`tool/source/DRAFT-NOT-VALIDATED.txt` được giữ lại có chủ đích để cảnh báo rằng
**artifact nháp do tool sinh ra không tự động được biên dịch, qua gate hoặc
được xác thực**.

Không được xem một EA vừa sinh là sẵn sàng cho production nếu chưa có biên dịch
MetaEditor thực, kiểm tra broker/môi trường và bằng chứng MT5 Strategy Tester.
Repository mặc định không theo dõi file `.ex5`; output native chỉ nên xuất hiện
trong bộ bằng chứng đã ký/attest hoặc GitHub Release assets.

## Tài liệu

- Hướng dẫn tiếng Việt: `tool/source/docs/HUONG-DAN-TOAN-TAP-vi.md`.
- Runbook tạo bằng chứng native: `docs/release/v3.3.0rc6/TASK-18-NATIVE-EVIDENCE-RUNBOOK.md`.
- Kết quả rà soát đồng bộ tài liệu RC6: `docs/release/v3.3.0rc6/DOCUMENTATION-AUDIT.md`.

## Giấy phép

MIT. File `LICENSE` ở root giống hệt `tool/source/LICENSE`.
