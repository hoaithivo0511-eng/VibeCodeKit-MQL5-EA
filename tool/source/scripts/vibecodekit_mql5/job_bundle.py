"""Job bundle helpers for remote worker payloads.

A remote worker cannot compile/test complex EA projects if the client only sends
a filename. This module creates deterministic zip bundles with hashes so workers
receive the source tree / EX5 / tester config needed for real execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import base64
import hashlib
import io
import zipfile

DEFAULT_EXCLUDES = {
    ".git", ".venv", "__pycache__", ".pytest_cache", "dist", "build",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _should_skip(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDES for part in path.parts)


def make_zip_bytes(files: list[tuple[Path, str]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arcname in sorted(files, key=lambda x: x[1]):
            z.write(src, arcname)
    return buf.getvalue()


def collect_project_files(project_root: str | Path, *, include_exts: set[str] | None = None) -> list[tuple[Path, str]]:
    root = Path(project_root).resolve()
    include_exts = include_exts or {".mq5", ".mqh", ".set", ".ini", ".yaml", ".yml", ".json", ".onnx", ".csv"}
    files: list[tuple[Path, str]] = []
    for p in root.rglob("*"):
        if not p.is_file() or _should_skip(p.relative_to(root)):
            continue
        if p.suffix.lower() not in include_exts:
            continue
        files.append((p, p.relative_to(root).as_posix()))
    return files


def make_project_bundle(project_root: str | Path, required_file: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    files = collect_project_files(root)
    if required_file:
        req = Path(required_file).resolve()
        if req.is_file() and all(src.resolve() != req for src, _ in files):
            try:
                arc = req.relative_to(root).as_posix()
            except ValueError:
                arc = req.name
            files.append((req, arc))
    data = make_zip_bytes(files)
    return {
        "bundle_type": "project_zip",
        "project_root_name": root.name,
        "file_count": len(files),
        "sha256": sha256_bytes(data),
        "zip_base64": base64.b64encode(data).decode("ascii"),
        "files": [arc for _, arc in sorted(files, key=lambda x: x[1])],
    }


def make_files_bundle(files: list[str | Path]) -> dict[str, Any]:
    pairs: list[tuple[Path, str]] = []
    for f in files:
        p = Path(f)
        if p.is_file():
            pairs.append((p, p.name))
    data = make_zip_bytes(pairs)
    return {
        "bundle_type": "files_zip",
        "file_count": len(pairs),
        "sha256": sha256_bytes(data),
        "zip_base64": base64.b64encode(data).decode("ascii"),
        "files": [arc for _, arc in sorted(pairs, key=lambda x: x[1])],
    }


def write_bundle_preview(bundle: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview = {k: v for k, v in bundle.items() if k != "zip_base64"}
    p.write_text(__import__("json").dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
