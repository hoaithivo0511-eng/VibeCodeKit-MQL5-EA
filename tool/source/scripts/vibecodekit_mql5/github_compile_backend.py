"""GitHub Actions implementation of the VibeCodeKit compile backend."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import json
import shutil
import subprocess
import tempfile
import time
import uuid

from .compile_core import CompileFailureCode
from .github_actions_client import GitHubActionsClient, client_from_env
from .github_compile_evidence import validate_github_compile_record
from .worker_protocol import WorkerArtifact, verify_artifacts

DEFAULT_WORKFLOW = "rc7-github-native-compile.yml"
DEFAULT_ARTIFACT_PREFIX = "vkmql-rc7-native-compile-"


def _safe_target(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    parsed = PurePosixPath(normalized)
    if not normalized or parsed.is_absolute() or any(p in {"", ".", ".."} for p in parsed.parts):
        raise ValueError("GitHub compile target must be a safe repository-relative path")
    if parsed.suffix.lower() != ".mq5":
        raise ValueError("GitHub compile target must end in .mq5")
    return parsed.as_posix()


def _git_head(project_root: str | Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = (proc.stdout or "").strip().lower()
    if proc.returncode != 0 or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("project root is not bound to a full git commit")
    return value


def _failure(reason: str, code: str = CompileFailureCode.INVOCATION_FAILED.value) -> dict[str, Any]:
    return {
        "source": "github_actions_metaeditor",
        "ok": False,
        "status": "FAIL",
        "reason": reason,
        "failure_codes": [code],
    }


def run_github_actions_compile(
    target: str,
    *,
    repository: str,
    ref: str,
    project_root: str | Path = ".",
    expected_commit: str | None = None,
    workflow: str = DEFAULT_WORKFLOW,
    artifact_name: str | None = None,
    evidence_dir: str | Path = "evidence/compile",
    token: str | None = None,
    timeout_sec: int = 3600,
    find_timeout_sec: int = 120,
    client: GitHubActionsClient | None = None,
) -> dict[str, Any]:
    """Dispatch native Windows compile, verify downloaded evidence, then install it."""
    try:
        target_rel = _safe_target(target)
        commit = (expected_commit or _git_head(project_root)).strip().lower()
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("expected commit must be a full git SHA")
        actions = client or client_from_env(repository, token=token)
        request_id = uuid.uuid4().hex
        actions.dispatch(
            workflow,
            ref,
            {"target": target_rel, "enable_native_run": "true", "request_id": request_id},
        )

        deadline = time.monotonic() + find_timeout_sec
        run = None
        while run is None and time.monotonic() <= deadline:
            run = actions.find_run(
                workflow,
                head_sha=commit,
                event="workflow_dispatch",
                request_id=request_id,
            )
            if run is None:
                time.sleep(2.0)
        if run is None:
            return _failure("GitHub Actions dispatch completed but the correlated workflow run was not found")

        run_data = actions.wait_for_run(run.run_id, timeout_sec=timeout_sec)
        if str(run_data.get("head_sha") or "").lower() not in {"", commit}:
            return _failure(
                "GitHub workflow head SHA does not match requested commit",
                CompileFailureCode.SOURCE_BINDING_MISMATCH.value,
            )
        if run_data.get("conclusion") != "success":
            return _failure(
                f"GitHub native compile workflow concluded {run_data.get('conclusion') or 'unknown'}"
            )

        name = artifact_name or f"{DEFAULT_ARTIFACT_PREFIX}{commit}"
        artifact = actions.artifact_by_name(run.run_id, name)
        if artifact is None:
            return _failure(
                "GitHub workflow completed without native compile artifact; MT5 installer secret may be unavailable"
            )

        destination = Path(evidence_dir)
        if destination.exists():
            return _failure(f"refusing to overwrite existing evidence directory: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".vkmql-gh-compile-", dir=destination.parent) as temp_name:
            extracted = Path(temp_name) / "artifact"
            actions.download_artifact(int(artifact["id"]), extracted)
            result_path = extracted / "result.json"
            if not result_path.is_file():
                return _failure("downloaded GitHub compile artifact has no result.json")
            record = json.loads(result_path.read_text(encoding="utf-8"))
            validation = validate_github_compile_record(record)
            if not validation.ok:
                failed = _failure("GitHub compile provenance validation failed")
                failed["validation"] = validation.to_dict()
                return failed
            github = record.get("github") if isinstance(record.get("github"), dict) else {}
            if str(record.get("source_commit") or "").lower() != commit:
                return _failure(
                    "GitHub compile artifact source commit does not match requested commit",
                    CompileFailureCode.SOURCE_BINDING_MISMATCH.value,
                )
            if str(github.get("repository") or "").lower() != repository.lower():
                return _failure(
                    "GitHub compile artifact repository does not match requested repository",
                    CompileFailureCode.SOURCE_BINDING_MISMATCH.value,
                )
            if str(github.get("run_id") or "") != str(run.run_id):
                return _failure(
                    "GitHub compile artifact run id does not match correlated workflow run",
                    CompileFailureCode.SOURCE_BINDING_MISMATCH.value,
                )
            jobs = actions.list_jobs(run.run_id)
            job_ids = {str(job.get("id")) for job in jobs if isinstance(job, dict)}
            if str(github.get("job_id") or "") not in job_ids:
                return _failure(
                    "GitHub compile artifact job id is not part of the correlated workflow run",
                    CompileFailureCode.SOURCE_BINDING_MISMATCH.value,
                )
            descriptors = [WorkerArtifact(**item) for item in record.get("artifacts", [])]
            artifact_check = verify_artifacts(extracted, descriptors)
            if not artifact_check.get("ok"):
                failed = _failure(
                    "GitHub compile artifact SHA-256/size verification failed",
                    CompileFailureCode.ARTIFACT_HASH_MISMATCH.value,
                )
                failed["artifact_check"] = artifact_check
                return failed
            shutil.copytree(extracted, destination)

        record["artifact_check"] = artifact_check
        record["workflow_run_id"] = run.run_id
        record["workflow_run_url"] = run.html_url
        return record
    except Exception as exc:  # noqa: BLE001
        return _failure(f"GitHub Actions compile backend error: {exc}")
