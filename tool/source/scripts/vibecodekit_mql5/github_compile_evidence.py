"""Validation for GitHub Actions native MetaEditor compile evidence.

A source label is never enough to establish trust. This module validates the
machine-readable record emitted by the Windows compile action before
``execution_sources`` may classify it as release-trusted compile evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_PROVENANCE = ("source", "command", "tool_version", "host", "recorded_at_utc")
_REQUIRED_ARTIFACT_ROLES = {"compile_log", "compiled_ex5"}


@dataclass
class GitHubCompileValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(value: object) -> bool:
    return bool(_SHA256.fullmatch(str(value or "").strip().lower()))


def _git_sha(value: object) -> bool:
    return bool(_GIT_SHA.fullmatch(str(value or "").strip().lower()))


def validate_github_compile_record(record: dict[str, Any] | None) -> GitHubCompileValidation:
    errors: list[str] = []
    warnings: list[str] = []
    data = record if isinstance(record, dict) else {}

    if data.get("source") != "github_actions_metaeditor":
        errors.append("compile source is not github_actions_metaeditor")
    if data.get("ok") is not True or str(data.get("status") or "").upper() != "PASS":
        errors.append("GitHub native compile status is not PASS")
    if data.get("error_count") != 0:
        errors.append("GitHub native compile error_count is not zero")
    if data.get("warning_count") != 0:
        errors.append("GitHub native compile warning_count is not zero")
    if data.get("failure_codes") not in ([], None):
        errors.append("GitHub native compile contains failure_codes")

    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    if not str(runner.get("os") or "").lower().startswith("windows"):
        errors.append("GitHub native compile runner OS is not Windows")

    github = data.get("github") if isinstance(data.get("github"), dict) else {}
    for key in ("repository", "workflow_ref"):
        if not str(github.get(key) or "").strip():
            errors.append(f"GitHub native compile missing github.{key}")
    for key in ("run_id", "job_id"):
        value = str(github.get(key) or "").strip()
        if not value.isdigit() or int(value) <= 0:
            errors.append(f"GitHub native compile github.{key} is not a positive numeric id")

    if not _git_sha(data.get("source_commit")):
        errors.append("GitHub native compile source_commit is not a full git SHA")
    if not _git_sha(data.get("source_tree_sha")):
        errors.append("GitHub native compile source_tree_sha is not a full git tree SHA")
    for key in ("target_sha256", "log_sha256", "ex5_sha256"):
        if not _sha256(data.get(key)):
            errors.append(f"GitHub native compile {key} is not SHA-256")

    target = str(data.get("target") or "").replace("\\", "/").strip()
    if not target or target.startswith("/") or ".." in target.split("/"):
        errors.append("GitHub native compile target is not a safe relative path")

    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    for key in _REQUIRED_PROVENANCE:
        if not str(provenance.get(key) or "").strip():
            errors.append(f"GitHub native compile provenance missing {key}")
    if provenance.get("source") != "github_actions_metaeditor":
        errors.append("GitHub native compile provenance source mismatch")
    if provenance.get("returncode") not in (0, "0"):
        errors.append("GitHub native compile provenance returncode is not zero")

    metaeditor = data.get("metaeditor") if isinstance(data.get("metaeditor"), dict) else {}
    if not str(metaeditor.get("path") or "").strip():
        errors.append("GitHub native compile missing MetaEditor path provenance")
    if not str(metaeditor.get("version") or "").strip():
        errors.append("GitHub native compile missing MetaEditor version provenance")
    toolchain = data.get("toolchain") if isinstance(data.get("toolchain"), dict) else {}
    if toolchain.get("probe_ok") is not True:
        errors.append("GitHub native compile toolchain ProbeEA did not PASS")

    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    roles: set[str] = set()
    for index, raw in enumerate(artifacts):
        if not isinstance(raw, dict):
            errors.append(f"GitHub native compile artifacts[{index}] is not an object")
            continue
        role = str(raw.get("role") or "")
        roles.add(role)
        filename = str(raw.get("filename") or "").replace("\\", "/")
        if not filename or filename.startswith("/") or any(
            part in {"", ".", ".."} for part in filename.split("/")
        ):
            errors.append(f"GitHub native compile artifact {role or index} has unsafe filename")
        if not _sha256(raw.get("sha256")):
            errors.append(f"GitHub native compile artifact {role or index} has invalid SHA-256")
        size = raw.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            errors.append(f"GitHub native compile artifact {role or index} has invalid size")
    missing_roles = sorted(_REQUIRED_ARTIFACT_ROLES - roles)
    if missing_roles:
        errors.append("GitHub native compile missing required artifact roles: " + ", ".join(missing_roles))

    return GitHubCompileValidation(ok=not errors, errors=errors, warnings=warnings)
