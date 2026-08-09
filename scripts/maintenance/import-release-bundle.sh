#!/usr/bin/env bash
set -euo pipefail

# Safe release-bundle importer for maintenance use.
# It intentionally does NOT commit, push, force-push, or modify Git refs.
# Usage:
#   bash scripts/maintenance/import-release-bundle.sh <bundle.zip> [destination]

BUNDLE="${1:-}"
DEST="${2:-_release-work/imported}"

if [ -z "$BUNDLE" ] || [ ! -f "$BUNDLE" ]; then
  echo "usage: $0 <bundle.zip> [destination]" >&2
  exit 2
fi

python3 - "$BUNDLE" <<'PY'
from pathlib import Path, PurePosixPath
import sys, zipfile

archive = Path(sys.argv[1])
with zipfile.ZipFile(archive) as zf:
    for info in zf.infolist():
        name = info.filename.replace('\\', '/')
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts:
            raise SystemExit(f"unsafe zip member: {info.filename}")
print("zip path-safety preflight: PASS")
PY

mkdir -p "$DEST"
unzip -q "$BUNDLE" -d "$DEST"

SOURCE_ZIP="$(find "$DEST/tool" -maxdepth 1 -type f -name '*-source-full.zip' -print -quit 2>/dev/null || true)"
if [ -n "$SOURCE_ZIP" ]; then
  mkdir -p "$DEST/tool/source"
  unzip -q "$SOURCE_ZIP" -d "$DEST/tool/source"
  echo "expanded source archive: $SOURCE_ZIP"
else
  echo "warning: no tool/*-source-full.zip found; bundle only was extracted" >&2
fi

echo "import destination: $DEST"
echo "No Git commit or push was performed."
