"""Remote worker HTTP client.

Uses Python stdlib only. Testable with MockWorkerTransport. The actual Windows
worker may expose compatible endpoints:

- POST /jobs
- GET  /jobs/{job_id}
- GET  /jobs/{job_id}/artifacts/{filename}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
import json
import urllib.request
import urllib.error
import time

from .worker_protocol import WorkerJobRequest, WorkerJobResult, WorkerArtifact, verify_artifacts


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
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(self.base_url + path, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            dest.write_bytes(resp.read())


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
        filename = Path(path).name
        src = self.artifact_dir / filename
        if not src.is_file():
            raise FileNotFoundError(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())


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
        dest.mkdir(parents=True, exist_ok=True)
        for art in result.artifacts:
            self.transport.download(f"/jobs/{result.job_id}/artifacts/{art.filename}", dest / art.filename)
        return verify_artifacts(dest, result.artifacts)


def client_from_url(worker_url: str, token: str | None = None, timeout: int = 60) -> RemoteWorkerClient:
    return RemoteWorkerClient(HttpWorkerTransport(worker_url, token=token, timeout=timeout))
