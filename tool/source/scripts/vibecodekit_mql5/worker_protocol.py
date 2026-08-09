"""Remote worker protocol for Windows MT5/MetaEditor execution.

The local CLI orchestrates jobs; the Windows worker performs real MetaEditor
compile and MT5 Strategy Tester runs. This module contains pure data contracts
and local verification helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Literal
import hashlib
import json
import time
import uuid

JobType = Literal["compile", "backtest", "multibroker", "walkforward"]
JobStatus = Literal["queued", "running", "passed", "failed", "cancelled"]


def utc_ms() -> int:
    return int(time.time() * 1000)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    def from_dict(cls, data: dict[str, Any]) -> "WorkerJobResult":
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
    base = Path(directory)
    checks = []
    ok = True
    for art in artifacts:
        path = base / art.filename
        exists = path.is_file()
        actual = sha256_file(path) if exists else None
        match = exists and actual == art.sha256
        if art.required and not match:
            ok = False
        checks.append({
            "role": art.role,
            "filename": art.filename,
            "exists": exists,
            "expected_sha256": art.sha256,
            "actual_sha256": actual,
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
