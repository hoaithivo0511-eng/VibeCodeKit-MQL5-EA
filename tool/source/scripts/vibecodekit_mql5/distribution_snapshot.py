"""Integrity checks for the verification snapshot embedded in the wheel."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

SNAPSHOT_MANIFEST = "SNAPSHOT-MANIFEST.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_record(path: Path, relative_path: str) -> dict[str, Any]:
    return {
        "path": PurePosixPath(relative_path).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def locate_snapshot_root() -> Path:
    packaged = Path(__file__).resolve().parent / "resources" / "distribution"
    if (packaged / SNAPSHOT_MANIFEST).is_file():
        return packaged
    from ._resources import distribution_root

    root = distribution_root()
    return root


def verify_distribution_snapshot(root: Path) -> list[str]:
    """Return fail-closed inventory/hash errors for a packaged snapshot."""
    root = Path(root)
    manifest_path = root / SNAPSHOT_MANIFEST
    if not manifest_path.is_file():
        return [f"{SNAPSHOT_MANIFEST} is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"{SNAPSHOT_MANIFEST} is invalid JSON: {exc}"]
    if manifest.get("schema_version") != "1.0":
        return ["snapshot schema_version must be 1.0"]

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        return ["snapshot manifest files must be a list"]
    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for item in raw_files:
        if not isinstance(item, dict):
            errors.append("snapshot manifest contains a non-object file record")
            continue
        rel = str(item.get("path") or "")
        pure = PurePosixPath(rel)
        if not rel or pure.is_absolute() or ".." in pure.parts:
            errors.append(f"unsafe snapshot path: {rel or '<empty>'}")
            continue
        if rel in records:
            errors.append(f"duplicate snapshot path: {rel}")
            continue
        records[rel] = item

    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != SNAPSHOT_MANIFEST
    }
    declared = set(records)
    for rel in sorted(declared - actual):
        errors.append(f"snapshot file missing: {rel}")
    for rel in sorted(actual - declared):
        errors.append(f"undeclared snapshot file: {rel}")
    for rel in sorted(actual & declared):
        path = root / rel
        if path.is_symlink():
            errors.append(f"snapshot symlink forbidden: {rel}")
            continue
        record = records[rel]
        if path.stat().st_size != record.get("size"):
            errors.append(f"snapshot size mismatch: {rel}")
        if sha256_file(path) != record.get("sha256"):
            errors.append(f"snapshot hash mismatch: {rel}")
    if manifest.get("file_count") != len(records):
        errors.append("snapshot file_count mismatch")
    return errors


__all__ = [
    "SNAPSHOT_MANIFEST",
    "locate_snapshot_root",
    "manifest_record",
    "sha256_file",
    "verify_distribution_snapshot",
]
