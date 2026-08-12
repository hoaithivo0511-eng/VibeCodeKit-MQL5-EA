from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo
import io
import json

import pytest

import vibecodekit_mql5.capability as capability
import vibecodekit_mql5.compile as compile_cli
from vibecodekit_mql5.github_actions_client import DispatchedRun, GitHubActionsError, safe_extract_artifact_zip
from vibecodekit_mql5.github_compile_backend import run_github_actions_compile
from tests.test_phase33_github_compile_backend import valid_record


def _args(**overrides):
    values = {
        "backend": "auto",
        "metaeditor": None,
        "github_repo": None,
        "github_ref": None,
        "github_token": None,
        "worker_url": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_auto_backend_prefers_github_before_remote_and_wine(monkeypatch):
    monkeypatch.setattr(compile_cli.sys, "platform", "linux")
    monkeypatch.setattr(compile_cli, "resolve_metaeditor_path", lambda _=None: "/tmp/MetaEditor64.exe")
    monkeypatch.setattr(compile_cli.shutil, "which", lambda name: "/usr/bin/wine" if name == "wine" else None)
    monkeypatch.setenv("VKMQL_GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("VKMQL_GITHUB_REF", "main")
    monkeypatch.setenv("VKMQL_GITHUB_TOKEN", "token")
    monkeypatch.setenv("VKMQL_WORKER_URL", "https://worker.example")
    assert compile_cli._select_backend(_args()) == "github-actions"


def test_auto_backend_uses_remote_before_wine(monkeypatch):
    monkeypatch.setattr(compile_cli.sys, "platform", "linux")
    monkeypatch.setattr(compile_cli, "resolve_metaeditor_path", lambda _=None: "/tmp/MetaEditor64.exe")
    monkeypatch.setattr(compile_cli.shutil, "which", lambda name: "/usr/bin/wine" if name == "wine" else None)
    monkeypatch.delenv("VKMQL_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("VKMQL_GITHUB_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.delenv("VKMQL_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("VKMQL_WORKER_URL", "https://worker.example")
    assert compile_cli._select_backend(_args()) == "remote-worker"


def test_capability_reports_github_actions_when_fully_configured(monkeypatch):
    monkeypatch.setattr(capability, "resolve_metaeditor_path", lambda: None)
    monkeypatch.setattr(capability, "resolve_terminal_path", lambda: None)
    monkeypatch.setattr(capability, "which", lambda _name: None)
    monkeypatch.setenv("VKMQL_GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("VKMQL_GITHUB_REF", "main")
    monkeypatch.setenv("VKMQL_GITHUB_TOKEN", "secret")
    report = capability.detect_capabilities()
    assert report.schema_version == "1.1"
    assert "github_actions_metaeditor" in report.compile_backends


def test_capability_never_calls_partial_github_configuration_ready(monkeypatch):
    monkeypatch.setattr(capability, "resolve_metaeditor_path", lambda: None)
    monkeypatch.setattr(capability, "resolve_terminal_path", lambda: None)
    monkeypatch.setattr(capability, "which", lambda _name: None)
    monkeypatch.setenv("VKMQL_GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.delenv("VKMQL_GITHUB_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.delenv("VKMQL_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    report = capability.detect_capabilities()
    assert "github_actions_metaeditor" not in report.compile_backends
    assert any("partially configured" in item for item in report.limitations)


def test_artifact_zip_rejects_symlink(tmp_path):
    buf = io.BytesIO()
    info = ZipInfo("link")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with ZipFile(buf, "w") as archive:
        archive.writestr(info, b"target")
    with pytest.raises(GitHubActionsError):
        safe_extract_artifact_zip(buf.getvalue(), tmp_path / "out")


def test_validator_rejects_duplicate_artifact_filename():
    from vibecodekit_mql5.github_compile_evidence import validate_github_compile_record

    record = valid_record()
    record["artifacts"][1]["filename"] = record["artifacts"][0]["filename"]
    assert validate_github_compile_record(record).ok is False


class BoundClient:
    def __init__(self, record):
        self.record = record

    def dispatch(self, workflow, ref, inputs):
        self.inputs = inputs

    def find_run(self, workflow, *, head_sha, event, request_id):
        assert request_id == self.inputs["request_id"]
        return DispatchedRun(999, head_sha, "https://example/run/999")

    def wait_for_run(self, run_id, *, timeout_sec):
        return {"status": "completed", "conclusion": "success", "head_sha": "c" * 40}

    def artifact_by_name(self, run_id, name):
        return {"id": 12, "name": name, "expired": False}

    def download_artifact(self, artifact_id, destination):
        destination.mkdir(parents=True)
        (destination / "result.json").write_text(json.dumps(self.record), encoding="utf-8")
        return [destination / "result.json"]

    def list_jobs(self, run_id):
        return [{"id": 456, "name": "native-compile"}]


def test_backend_rejects_record_from_different_run(tmp_path):
    record = valid_record()
    record["github"]["run_id"] = "123"
    result = run_github_actions_compile(
        "Experts/EA.mq5",
        repository="owner/repo",
        ref="main",
        expected_commit="c" * 40,
        evidence_dir=tmp_path / "evidence",
        client=BoundClient(record),
        find_timeout_sec=1,
    )
    assert result["ok"] is False
    assert "run id" in result["reason"].lower()
    assert result["failure_codes"] == ["SOURCE_BINDING_MISMATCH"]
