"""Small stdlib GitHub Actions client used by the native compile backend.

The transport is injectable so dispatch/poll/artifact logic can be tested
without network access. Artifact ZIP extraction is defensive against traversal
and symlink entries before any files become caller-visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
import io
import json
import os
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile


class GitHubActionsError(RuntimeError):
    pass


class GitHubActionsTransport(Protocol):
    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any: ...
    def download(self, path: str) -> bytes: ...


class HttpGitHubActionsTransport:
    def __init__(self, token: str, api_url: str = "https://api.github.com", timeout: int = 60) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vibecodekit-mql5-ea",
        }

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.api_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def download(self, path: str) -> bytes:
        req = urllib.request.Request(self.api_url + path, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return response.read()


@dataclass(frozen=True)
class DispatchedRun:
    run_id: int
    head_sha: str
    html_url: str = ""


def _safe_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename.replace("\\", "/")
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise GitHubActionsError(f"unsafe workflow artifact path: {info.filename!r}")
    unix_mode = (info.external_attr >> 16) & 0o170000
    if unix_mode == 0o120000:
        raise GitHubActionsError(f"workflow artifact contains symlink: {info.filename!r}")
    return rel


def safe_extract_artifact_zip(data: bytes, destination: str | Path) -> list[Path]:
    dest = Path(destination)
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        raise GitHubActionsError(f"unsafe artifact destination: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vkmql-gha-", dir=dest.parent) as temp_name:
        stage = Path(temp_name) / "stage"
        stage.mkdir()
        extracted: list[PurePosixPath] = []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                rel = _safe_zip_member(info)
                target = stage.joinpath(*rel.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append(rel)
        if dest.exists():
            raise GitHubActionsError(f"refusing to overwrite artifact destination: {dest}")
        os.replace(stage, dest)
    return [dest.joinpath(*rel.parts) for rel in extracted]


class GitHubActionsClient:
    def __init__(self, repository: str, transport: GitHubActionsTransport) -> None:
        if repository.count("/") != 1:
            raise ValueError("repository must be owner/name")
        self.repository = repository
        self.transport = transport
        self.base = f"/repos/{repository}"

    def dispatch(self, workflow: str, ref: str, inputs: dict[str, str] | None = None) -> None:
        workflow_id = urllib.parse.quote(workflow, safe="")
        self.transport.request_json(
            "POST",
            f"{self.base}/actions/workflows/{workflow_id}/dispatches",
            {"ref": ref, "inputs": inputs or {}},
        )

    def find_run(self, workflow: str, *, head_sha: str, event: str = "workflow_dispatch") -> DispatchedRun | None:
        workflow_id = urllib.parse.quote(workflow, safe="")
        data = self.transport.request_json(
            "GET",
            f"{self.base}/actions/workflows/{workflow_id}/runs?event={event}&per_page=20",
        ) or {}
        for raw in data.get("workflow_runs", []):
            if str(raw.get("head_sha") or "") == head_sha:
                return DispatchedRun(int(raw["id"]), head_sha, str(raw.get("html_url") or ""))
        return None

    def wait_for_run(self, run_id: int, *, timeout_sec: int = 3600, interval_sec: float = 2.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        while True:
            data = self.transport.request_json("GET", f"{self.base}/actions/runs/{run_id}") or {}
            if data.get("status") == "completed":
                return data
            if time.monotonic() > deadline:
                raise TimeoutError(f"GitHub Actions run timed out: {run_id}")
            time.sleep(interval_sec)

    def list_jobs(self, run_id: int) -> list[dict[str, Any]]:
        data = self.transport.request_json("GET", f"{self.base}/actions/runs/{run_id}/jobs?per_page=100") or {}
        return list(data.get("jobs", []))

    def artifact_by_name(self, run_id: int, name: str) -> dict[str, Any] | None:
        data = self.transport.request_json("GET", f"{self.base}/actions/runs/{run_id}/artifacts?per_page=100") or {}
        for artifact in data.get("artifacts", []):
            if artifact.get("name") == name and not artifact.get("expired"):
                return artifact
        return None

    def download_artifact(self, artifact_id: int, destination: str | Path) -> list[Path]:
        data = self.transport.download(f"{self.base}/actions/artifacts/{artifact_id}/zip")
        return safe_extract_artifact_zip(data, destination)


def client_from_env(repository: str | None = None, token: str | None = None) -> GitHubActionsClient:
    repo = repository or os.environ.get("GITHUB_REPOSITORY", "")
    auth = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not auth:
        raise GitHubActionsError("GITHUB_TOKEN/GH_TOKEN is required for GitHub Actions backend")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    return GitHubActionsClient(repo, HttpGitHubActionsTransport(auth, api_url=api_url))
