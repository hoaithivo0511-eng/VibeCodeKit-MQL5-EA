#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# SETUP-CODESPACE.sh
# Giai nen toan bo tool VibeCodeKit MQL5 v3.3.0rc4 vao repo va day len GitHub.
# Chay trong GitHub Codespaces (hoac bat ky may nao da co git + unzip).
#
# Cach dung:
#   1. Upload tep VibecodeKit-MQL5-v330rc4-runtime-safety-fix-bundle.zip
#      vao thu muc goc cua repo.
#   2. Chay:  bash SETUP-CODESPACE.sh
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"
echo "Thu muc lam viec: $REPO_ROOT"
echo

# --- 0. Tim tep bundle -----------------------------------------------------
BUNDLE="${1:-}"
if [ -z "$BUNDLE" ]; then
  BUNDLE="$(ls -1 *.zip 2>/dev/null | grep -i 'runtime-safety-fix-bundle' | head -1 || true)"
fi
if [ -z "$BUNDLE" ] || [ ! -f "$BUNDLE" ]; then
  echo "LOI: khong tim thay tep bundle .zip o thu muc goc repo."
  echo "     Hay upload 'VibecodeKit-MQL5-v330rc4-runtime-safety-fix-bundle.zip' vao day roi chay lai."
  exit 1
fi
echo "==> Buoc 1/7  Da tim thay bundle: $BUNDLE ($(stat -c%s "$BUNDLE") byte)"

# --- 1. Giai nen bundle ----------------------------------------------------
echo "==> Buoc 2/7  Giai nen bundle vao goc repo"
unzip -o -q "$BUNDLE" -d .

INNER="tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip"
if [ ! -f "$INNER" ]; then
  echo "LOI: khong thay $INNER sau khi giai nen bundle."
  exit 1
fi

# --- 2. Giai nen ma nguon tool --------------------------------------------
echo "==> Buoc 3/7  Giai nen ma nguon tool vao tool/source"
mkdir -p tool/source
unzip -o -q "$INNER" -d tool/source

# --- 3. Doi chieu SHA256 cua bundle ---------------------------------------
if [ -f "SHA256SUMS.txt" ]; then
  echo "==> Buoc 4/7  Doi chieu SHA256SUMS.txt"
  if sha256sum -c SHA256SUMS.txt --quiet 2>/dev/null; then
    echo "    OK: tat ca tep trong bundle khop SHA256."
  else
    echo "    CANH BAO: mot so dong khong doi chieu duoc (thuong do duong dan tuong doi). Bo qua duoc."
  fi
else
  echo "==> Buoc 4/7  Khong co SHA256SUMS.txt, bo qua doi chieu"
fi

# --- 4. Tao lai manifest cua toan repo ------------------------------------
echo "==> Buoc 5/7  Tao REPO-MANIFEST.sha256"
find . -path ./.git -prune -o -type f -print \
  | grep -v '^./REPO-MANIFEST.sha256$' \
  | LC_ALL=C sort \
  | xargs -d '\n' sha256sum > REPO-MANIFEST.sha256
FILES=$(wc -l < REPO-MANIFEST.sha256)
BYTES=$(find . -path ./.git -prune -o -type f -printf '%s\n' | awk '{s+=$1} END {print s}')
echo "    Tong cong: $FILES tep, $BYTES byte"

# --- 5. Commit -------------------------------------------------------------
echo "==> Buoc 6/7  Commit"
git add -A
if git diff --cached --quiet; then
  echo "    Khong co thay doi nao de commit."
else
  git -c user.name="hoaithivo0511-eng" \
      -c user.email="hoaithivo0511@gmail.com" \
      commit -q -m "feat: giai nen toan bo tool VibeCodeKit MQL5 v3.3.0rc4 ($FILES tep)"
  echo "    Da commit."
fi

# --- 6. Push ---------------------------------------------------------------
echo "==> Buoc 7/7  Day len GitHub"
git push origin HEAD:main
echo
echo "HOAN TAT. Repo hien co $FILES tep."
echo "Kiem tra lai bang: git ls-files | wc -l"
