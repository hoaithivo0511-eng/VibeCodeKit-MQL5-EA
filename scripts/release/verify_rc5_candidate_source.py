"""Verify that active tool/source is still the exact Task-09 RC5 source snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(repo_root: Path, manifest_path: Path) -> list[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = data.get("files")
    if not isinstance(records, list):
        return ["Task-09 source manifest lacks files[]"]
    expected = {
        str(rec.get("path")): str(rec.get("sha256"))
        for rec in records
        if isinstance(rec, dict) and rec.get("path")
    }
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "tool/source"],
        text=True, capture_output=True, check=True,
    )
    actual_paths = {
        line.removeprefix("tool/source/")
        for line in proc.stdout.splitlines()
        if line.startswith("tool/source/")
    }
    errors: list[str] = []
    expected_paths = set(expected)
    for rel in sorted(expected_paths - actual_paths):
        errors.append(f"missing tracked source file: {rel}")
    for rel in sorted(actual_paths - expected_paths):
        errors.append(f"unexpected tracked source file after Task 09: {rel}")
    for rel in sorted(expected_paths & actual_paths):
        path = repo_root / "tool/source" / rel
        digest = sha256(path)
        if digest != expected[rel]:
            errors.append(f"source digest drift: {rel}: expected {expected[rel]}, got {digest}")
    if data.get("file_count") != len(expected):
        errors.append(
            f"manifest file_count mismatch: declared {data.get('file_count')}, records {len(expected)}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path("."))
    p.add_argument(
        "--manifest",
        type=Path,
        default=Path("tool/vibecodekit-mql5-v3.3.0rc5-source-full.manifest.json"),
    )
    args = p.parse_args(argv)
    errors = verify(args.repo_root, args.manifest)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: tool/source exactly matches the Task-09 RC5 source manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
