"""Remote worker HTTP client.

Uses Python stdlib only. Testable with MockWorkerTransport. The actual Windows
worker may expose compatible endpoints:

- POST /jobs
- GET  /jobs/{job_id}
- GET  /jobs/{job_id}/artifacts/{filename}
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .worker_protocol import (
    ArtifactSecurityError,
    ArtifactVerificationError,
    WorkerArtifact,
    WorkerJobRequest,
    WorkerJobResult,
    safe_artifact_path,
    validate_artifact_filename,
    verify_artifacts,
)


class WorkerTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_json(self, path: str) -> dict[str, Any]: ...
    def download(self, path: str, dest: Path) -> None: ...


class HttpWorkerTransport:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_json(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def download(self, path: str, dest: Path) -> None:
        if dest.is_symlink() or dest.exists():
            raise ArtifactSecurityError(f"refusing to overwrite transport destination: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(self.base_url + path, headers=self._headers(), method="GET")
        with (
            urllib.request.urlopen(req, timeout=self.timeout) as resp,
            dest.open("xb") as handle,
        ):
            shutil.copyfileobj(resp, handle)


class MockWorkerTransport:
    """Deterministic in-process transport for tests and dry runs."""

    def __init__(self, result: WorkerJobResult | None = None, artifact_dir: str | Path | None = None) -> None:
        self.result = result
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.submitted: list[dict[str, Any]] = []

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.submitted.append({"path": path, "payload": payload})
        if self.result is None:
            return {"job_id": payload.get("job_id"), "status": "queued"}
        return {"job_id": self.result.job_id, "status": self.result.status}

    def get_json(self, path: str) -> dict[str, Any]:
        if self.result is None:
            return {"job_id": "mock", "job_type": "compile", "status": "failed", "worker_id": "mock", "error": "no mock result"}
        return self.result.to_dict()

    def download(self, path: str, dest: Path) -> None:
        if self.artifact_dir is None:
            raise FileNotFoundError("mock artifact_dir not configured")
        marker = "/artifacts/"
        if marker not in path:
            raise ArtifactSecurityError(f"invalid mock artifact route: {path!r}")
        filename = urllib.parse.unquote(path.split(marker, 1)[1])
        src = safe_artifact_path(self.artifact_dir, filename)
        if not src.is_file():
            raise FileNotFoundError(src)
        if dest.is_symlink() or dest.exists():
            raise ArtifactSecurityError(f"refusing to overwrite mock destination: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())


def _artifact_paths(artifacts: list[WorkerArtifact]) -> list[tuple[WorkerArtifact, PurePosixPath]]:
    resolved: list[tuple[WorkerArtifact, PurePosixPath]] = []
    seen: set[str] = set()
    for art in artifacts:
        relative = validate_artifact_filename(art.filename)
        key = relative.as_posix()
        if key in seen:
            raise ArtifactSecurityError(f"duplicate worker artifact filename: {key!r}")
        seen.add(key)
        resolved.append((art, relative))
    return resolved


def _ensure_safe_parent(root: Path, relative: PurePosixPath) -> Path:
    """Create missing target parents while rejecting existing symlinks."""
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ArtifactSecurityError(f"artifact destination is not a real directory: {root}")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ArtifactSecurityError(
                f"artifact destination crosses a symlink: {relative.as_posix()!r}"
            )
        current.mkdir(exist_ok=True)
        if not current.is_dir():
            raise ArtifactSecurityError(f"artifact parent is not a directory: {current}")
    return safe_artifact_path(root, relative.as_posix())


def _commit_staged(
    destination: Path,
    stage: Path,
    backup: Path,
    artifacts: list[tuple[WorkerArtifact, PurePosixPath]],
) -> dict[str, Any]:
    """Commit verified files with per-file atomic replace and batch rollback."""
    records: list[tuple[Path, Path | None, bool]] = []
    try:
        for _art, relative in artifacts:
            final_path = _ensure_safe_parent(destination, relative)
            staged_path = safe_artifact_path(stage, relative.as_posix())
            backup_path: Path | None = None
            if final_path.exists():
                if final_path.is_symlink() or not final_path.is_file():
                    raise ArtifactSecurityError(f"unsafe existing artifact target: {final_path}")
                backup_path = _ensure_safe_parent(backup, relative)
                os.replace(final_path, backup_path)
            records.append((final_path, backup_path, False))
            os.replace(staged_path, final_path)
            records[-1] = (final_path, backup_path, True)

        committed_check = verify_artifacts(
            destination, [artifact for artifact, _relative in artifacts]
        )
        if not committed_check["ok"]:  # pragma: no cover - filesystem fault
            raise ArtifactVerificationError(committed_check)
        return committed_check
    except Exception:
        for final_path, backup_path, installed in reversed(records):
            if installed and final_path.is_file() and not final_path.is_symlink():
                final_path.unlink()
            if backup_path is not None and backup_path.is_file():
                final_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup_path, final_path)
        raise


class RemoteWorkerClient:
    def __init__(self, transport: WorkerTransport) -> None:
        self.transport = transport

    def submit(self, request: WorkerJobRequest) -> str:
        resp = self.transport.post_json("/jobs", request.to_dict())
        return resp.get("job_id") or request.job_id

    def poll(self, job_id: str, *, timeout_sec: int = 3600, interval_sec: float = 2.0) -> WorkerJobResult:
        deadline = time.time() + timeout_sec
        while True:
            data = self.transport.get_json(f"/jobs/{job_id}")
            result = WorkerJobResult.from_dict(data)
            if result.status in {"passed", "failed", "cancelled"}:
                return result
            if time.time() > deadline:
                raise TimeoutError(f"worker job timed out: {job_id}")
            time.sleep(interval_sec)

    def download_artifacts(self, result: WorkerJobResult, dest_dir: str | Path) -> dict[str, Any]:
        dest = Path(dest_dir)
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            raise ArtifactSecurityError(f"artifact destination is not a real directory: {dest}")
        artifacts = _artifact_paths(result.artifacts)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".vck-worker-", dir=dest.parent) as txn_name:
            transaction = Path(txn_name)
            stage = transaction / "stage"
            backup = transaction / "backup"
            stage.mkdir()

            for art, relative in artifacts:
                staged_path = _ensure_safe_parent(stage, relative)
                encoded = "/".join(urllib.parse.quote(part, safe="") for part in relative.parts)
                self.transport.download(
                    f"/jobs/{result.job_id}/artifacts/{encoded}", staged_path
                )

            staged_check = verify_artifacts(stage, result.artifacts)
            if not staged_check["ok"]:
                raise ArtifactVerificationError(staged_check)

            # All network I/O and descriptor verification completed before any
            # caller-visible file is replaced.
            return _commit_staged(dest, stage, backup, artifacts)


def client_from_url(worker_url: str, token: str | None = None, timeout: int = 60) -> RemoteWorkerClient:
    return RemoteWorkerClient(HttpWorkerTransport(worker_url, token=token, timeout=timeout))
