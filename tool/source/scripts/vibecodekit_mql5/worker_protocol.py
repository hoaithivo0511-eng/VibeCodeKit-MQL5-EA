"""Remote worker protocol for Windows MT5/MetaEditor execution.

The local CLI orchestrates jobs; the Windows worker performs real MetaEditor
compile and MT5 Strategy Tester runs. This module contains pure data contracts
and local verification helpers.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

JobType = Literal["compile", "backtest", "multibroker", "walkforward"]
JobStatus = Literal["queued", "running", "passed", "failed", "cancelled"]


class ArtifactSecurityError(ValueError):
    """Raised when worker-controlled artifact metadata escapes its boundary."""


class ArtifactVerificationError(RuntimeError):
    """Raised when staged worker artifacts do not match their descriptors."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        super().__init__("worker artifact verification failed")


def utc_ms() -> int:
    return int(time.time() * 1000)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_artifact_filename(filename: str) -> PurePosixPath:
    """Return a portable relative artifact path or reject unsafe metadata.

    Worker filenames are untrusted protocol input.  Both POSIX traversal and
    Windows drive/UNC spellings are rejected even when the client itself runs
    on another platform.
    """
    if not isinstance(filename, str) or not filename:
        raise ArtifactSecurityError("artifact filename must be a non-empty string")
    if "\x00" in filename:
        raise ArtifactSecurityError("artifact filename contains a NUL byte")

    normalized = filename.replace("\\", "/")
    raw_parts = normalized.split("/")
    windows_path = PureWindowsPath(filename)
    if normalized.startswith("/") or windows_path.is_absolute() or windows_path.drive:
        raise ArtifactSecurityError(f"artifact filename must be relative: {filename!r}")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ArtifactSecurityError(f"artifact filename contains an unsafe segment: {filename!r}")
    if any(":" in part for part in raw_parts):
        raise ArtifactSecurityError(f"artifact filename contains a Windows stream/drive marker: {filename!r}")
    return PurePosixPath(*raw_parts)


def safe_artifact_path(directory: str | Path, filename: str) -> Path:
    """Resolve ``filename`` below ``directory`` without following leaf symlinks."""
    base = Path(directory)
    if base.is_symlink():
        raise ArtifactSecurityError(f"artifact directory is a symlink: {base}")
    relative = validate_artifact_filename(filename)
    root = base.resolve(strict=False)
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:  # pragma: no cover - defence behind parser
        raise ArtifactSecurityError(f"artifact path escapes destination: {filename!r}") from exc

    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ArtifactSecurityError(f"artifact path crosses a symlink: {filename!r}")
    return candidate


@dataclass
class WorkerArtifact:
    role: str
    filename: str
    sha256: str
    size_bytes: int
    required: bool = True
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerJobRequest:
    job_type: JobType
    payload: dict[str, Any]
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    protocol_version: str = "1.0"
    created_at_ms: int = field(default_factory=utc_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerJobResult:
    job_id: str
    job_type: JobType
    status: JobStatus
    worker_id: str
    artifacts: list[WorkerArtifact] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    protocol_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.artifacts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerJobResult:
        arts = [WorkerArtifact(**a) if isinstance(a, dict) else a for a in data.get("artifacts", [])]
        return cls(
            job_id=data["job_id"],
            job_type=data["job_type"],
            status=data["status"],
            worker_id=data.get("worker_id", "unknown"),
            artifacts=arts,
            metrics=data.get("metrics", {}),
            logs=data.get("logs", []),
            error=data.get("error"),
            started_at_ms=data.get("started_at_ms"),
            finished_at_ms=data.get("finished_at_ms"),
            protocol_version=data.get("protocol_version", "1.0"),
        )


def verify_artifacts(directory: str | Path, artifacts: list[WorkerArtifact]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    ok = True
    for art in artifacts:
        try:
            path = safe_artifact_path(directory, art.filename)
        except ArtifactSecurityError as exc:
            ok = False
            checks.append({
                "role": art.role,
                "filename": art.filename,
                "exists": False,
                "expected_sha256": art.sha256,
                "actual_sha256": None,
                "expected_size_bytes": art.size_bytes,
                "actual_size_bytes": None,
                "match": False,
                "required": art.required,
                "error": str(exc),
            })
            continue
        exists = path.is_file()
        actual = sha256_file(path) if exists else None
        actual_size = path.stat().st_size if exists else None
        expected_hash = art.sha256.lower()
        hash_shape_ok = len(expected_hash) == 64 and all(
            char in "0123456789abcdef" for char in expected_hash
        )
        size_shape_ok = isinstance(art.size_bytes, int) and art.size_bytes >= 0
        match = bool(
            exists
            and hash_shape_ok
            and size_shape_ok
            and actual == expected_hash
            and actual_size == art.size_bytes
        )
        if not match:
            ok = False
        checks.append({
            "role": art.role,
            "filename": art.filename,
            "exists": exists,
            "expected_sha256": art.sha256,
            "actual_sha256": actual,
            "expected_size_bytes": art.size_bytes,
            "actual_size_bytes": actual_size,
            "match": match,
            "required": art.required,
        })
    return {"ok": ok, "checks": checks}


def write_worker_result(path: str | Path, result: WorkerJobResult) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def read_worker_result(path: str | Path) -> WorkerJobResult:
    return WorkerJobResult.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
