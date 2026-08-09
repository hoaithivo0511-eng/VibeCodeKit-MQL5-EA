#!/usr/bin/env python3
"""Generate or verify the repository-wide SHA-256 manifest.

The manifest covers every Git-tracked regular file except REPO-MANIFEST.sha256
itself. Paths are sorted and rendered as `./<repo-relative-path>` so the file
remains stable across runners.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import subprocess
from pathlib import Path

MANIFEST = Path("REPO-MANIFEST.sha256")


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    names = [name.decode("utf-8") for name in raw.split(b"\0") if name]
    paths = [Path(name) for name in names if name != MANIFEST.as_posix()]
    missing = [p.as_posix() for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"tracked path is not a regular file: {missing[:20]}")
    return sorted(paths, key=lambda p: p.as_posix())


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render() -> str:
    lines = [f"{digest(path)}  ./{path.as_posix()}" for path in tracked_files()]
    return "\n".join(lines) + "\n"


def check() -> int:
    if not MANIFEST.is_file():
        print(f"repository manifest missing: {MANIFEST}")
        return 1
    expected = render()
    actual = MANIFEST.read_text(encoding="utf-8")
    if actual == expected:
        print(f"repository manifest: PASS ({len(expected.splitlines())} tracked files)")
        return 0
    print("repository manifest: FAIL")
    diff = difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile="committed/REPO-MANIFEST.sha256",
        tofile="computed/REPO-MANIFEST.sha256",
        lineterm="",
    )
    for index, line in enumerate(diff):
        if index >= 200:
            print("... diff truncated ...")
            break
        print(line)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the manifest")
    mode.add_argument("--check", action="store_true", help="verify the committed manifest")
    args = parser.parse_args()

    if args.write:
        content = render()
        MANIFEST.write_text(content, encoding="utf-8", newline="\n")
        print(f"repository manifest written: {len(content.splitlines())} tracked files")
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
