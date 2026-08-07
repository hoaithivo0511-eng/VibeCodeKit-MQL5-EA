"""Shared helpers for contract build pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import hashlib
import datetime


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def validation_report(ok: bool, missing: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": ok,
        "release_blocking": not ok,
        "missing": missing,
        "warnings": warnings or [],
    }
