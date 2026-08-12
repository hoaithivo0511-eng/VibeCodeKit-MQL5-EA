#!/usr/bin/env python3
"""Fail closed on unclassified byte-identical tracked files."""
from __future__ import annotations

import hashlib
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / item.decode() for item in raw.split(b"\0") if item]


def allowed(paths: list[str]) -> tuple[bool, str]:
    group = set(paths)
    if (
        any("tool/source/scripts/vibecodekit_mql5/resources/" in p for p in paths)
        and all(p.startswith("tool/source/") for p in paths)
    ):
        return True, "packaged-resource-mirror"
    if all(
        p.startswith("demo/CCBSN_GoldenFixture/")
        or p.startswith("demo/generic-acceptance/")
        for p in paths
    ):
        return True, "self-contained-acceptance-fixtures"
    frozen = {
        "demo/CCBSN-build-plan.json",
        "demo/CCBSN-configured-ir.json",
        "demo/CCBSN_GoldenFixture/BUILD-PLAN.json",
        "demo/CCBSN_GoldenFixture/EA-IR.json",
    }
    if group <= frozen and len(group) > 1:
        return True, "frozen-bundle-input"
    if all(p.startswith("reports/") for p in paths):
        return True, "historical-report-evidence"
    if len(paths) == 2:
        left, right = sorted(paths)
        native_prefix = "native/workers-windows/"
        package_prefix = "tool/source/workers/windows/"
        if (
            left.startswith(native_prefix)
            and right.startswith(package_prefix)
            and left[len(native_prefix):] == right[len(package_prefix):]
        ):
            return True, "native-worker-handoff"
    if all(PurePosixPath(p).name == "LICENSE" for p in paths):
        return True, "license-copy"
    return False, ""


def evaluate() -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in tracked_files():
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            continue
        rel = path.relative_to(ROOT).as_posix()
        groups[hashlib.sha256(path.read_bytes()).hexdigest()].append(rel)
    bad: list[tuple[str, list[str]]] = []
    for digest, paths in sorted(groups.items()):
        if len(paths) < 2:
            continue
        ok, _ = allowed(paths)
        if not ok:
            bad.append((digest, paths))
    return bad


def main() -> int:
    bad = evaluate()
    if bad:
        print("duplicate content policy: FAIL")
        for digest, paths in bad:
            print(digest)
            for path in paths:
                print(f"  {path}")
        return 1
    print("duplicate content policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
