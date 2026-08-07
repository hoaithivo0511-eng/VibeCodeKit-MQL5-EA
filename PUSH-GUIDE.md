# Hướng dẫn đồng bộ bundle lên kho này

Kho đã được khởi tạo với `.gitattributes` và `README.md`. Phần dữ liệu bundle (187 tệp, 7.062.979 byte, gồm 3 tệp nhị phân tổng 4,66 MB) được đẩy lên bằng Git từ máy của bạn.

## Cách nhanh nhất — dùng gói đã commit sẵn

Gói `VibeCodeKit-MQL5-EA-repo-ready.zip` đã chứa một Git repository hoàn chỉnh (nhánh `main`, commit `88148e7`, 192 tệp).

### Windows PowerShell

```powershell
cd VibeCodeKit-MQL5-EA
git remote add origin https://github.com/hoaithivo0511-eng/VibeCodeKit-MQL5-EA.git
git branch -M main
git push -u origin main --force
```

### macOS / Linux

```bash
cd VibeCodeKit-MQL5-EA
git remote add origin https://github.com/hoaithivo0511-eng/VibeCodeKit-MQL5-EA.git
git branch -M main
git push -u origin main --force
```

Dùng `--force` vì kho trên GitHub đang có commit khởi tạo riêng. Sau lần push này, các lần sau không cần `--force`.

## Cách thay thế — clone rồi copy

```bash
git clone https://github.com/hoaithivo0511-eng/VibeCodeKit-MQL5-EA.git
cd VibeCodeKit-MQL5-EA
git config core.autocrlf false
# copy toàn bộ nội dung bundle đã giải nén vào đây, giữ nguyên cấu trúc thư mục
git add -A
git commit -m "Add VibecodeKit MQL5 v3.3.0rc4 runtime-safety-fix bundle"
git push
```

## Xác minh sau khi push

```bash
git ls-files | wc -l          # kỳ vọng: 192
sha256sum -c UPLOAD-MANIFEST.sha256
```
