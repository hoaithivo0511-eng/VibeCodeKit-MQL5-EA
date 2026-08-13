#!/usr/bin/env python3
"""Synchronize and verify the wheel's canonical distribution snapshot."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tool" / "source"
PACKAGE_SCRIPTS = SOURCE / "scripts"
SNAPSHOT = PACKAGE_SCRIPTS / "vibecodekit_mql5" / "resources" / "distribution"
if str(PACKAGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SCRIPTS))

from vibecodekit_mql5.distribution_snapshot import (
    SNAPSHOT_MANIFEST,
    manifest_record,
    verify_distribution_snapshot,
)

ROOT_FILES = ("pyproject.toml", "tool-catalog.json", "agent-contract.json")
PACKAGE_CONTRACT = PACKAGE_SCRIPTS / "vibecodekit_mql5" / "agent-contract.json"


def tracked_test_files() -> list[Path]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "tool/source/tests"], cwd=ROOT
    )
    paths = [ROOT / item.decode("utf-8") for item in raw.split(b"\0") if item]
    bad = [path for path in paths if not path.is_file() or path.is_symlink()]
    if bad:
        raise SystemExit(f"tracked test paths must be regular files: {bad[:5]}")
    return sorted(paths)


def source_mapping() -> dict[str, Path]:
    mapping = {name: SOURCE / name for name in ROOT_FILES}
    for path in tracked_test_files():
        rel = path.relative_to(SOURCE).as_posix()
        mapping[rel] = path
    missing = [rel for rel, path in mapping.items() if not path.is_file()]
    if missing:
        raise SystemExit(f"canonical snapshot inputs missing: {missing}")
    return dict(sorted(mapping.items()))


def expected_manifest(mapping: dict[str, Path]) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "wheel-verification-snapshot",
        "file_count": len(mapping),
        "files": [manifest_record(path, rel) for rel, path in mapping.items()],
    }


def synchronize() -> None:
    # The package-local contract is a shipped runtime asset, while the root
    # contract is the canonical generated record. Keep them byte-identical so
    # source checkouts, source archives and installed wheels cannot report
    # different kit versions.
    shutil.copyfile(SOURCE / "agent-contract.json", PACKAGE_CONTRACT)
    mapping = source_mapping()
    allowed = set(mapping) | {SNAPSHOT_MANIFEST}
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    for path in sorted(SNAPSHOT.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            if path.relative_to(SNAPSHOT).as_posix() not in allowed:
                path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    for rel, source in mapping.items():
        destination = SNAPSHOT / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    manifest = expected_manifest(mapping)
    (SNAPSHOT / SNAPSHOT_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify() -> None:
    mapping = source_mapping()
    errors = verify_distribution_snapshot(SNAPSHOT)
    for rel, source in mapping.items():
        target = SNAPSHOT / rel
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            errors.append(f"canonical snapshot drift: {rel}")
    if errors:
        raise SystemExit("distribution snapshot verification failed:\n- " + "\n- ".join(errors))
    print(f"distribution snapshot: PASS ({len(mapping)} files)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sync", "verify"))
    args = parser.parse_args()
    if args.command == "sync":
        synchronize()
        verify()
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
