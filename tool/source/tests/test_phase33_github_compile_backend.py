import hashlib
import io
import zipfile

import pytest

from vibecodekit_mql5.evidence_v2 import EvidenceManifestV2
from vibecodekit_mql5.github_actions_client import (
    GitHubActionsClient,
    GitHubActionsError,
    safe_extract_artifact_zip,
)
from vibecodekit_mql5.github_compile_evidence import validate_github_compile_record


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_record():
    log = b"Result: 0 errors, 0 warnings"
    ex5 = b"X" * 64
    return {
        "schema_version": "1.0",
        "source": "github_actions_metaeditor",
        "ok": True,
        "status": "PASS",
        "error_count": 0,
        "warning_count": 0,
        "failure_codes": [],
        "target": "Experts/EA.mq5",
        "target_sha256": "a" * 64,
        "staged_sha256": "b" * 64,
        "log_sha256": _sha(log),
        "ex5_sha256": _sha(ex5),
        "source_commit": "c" * 40,
        "source_tree_sha": "d" * 40,
        "runner": {"os": "Windows", "arch": "X64", "name": "runner"},
        "github": {
            "repository": "owner/repo",
            "run_id": "123",
            "job_id": "456",
            "workflow_ref": "owner/repo/.github/workflows/native.yml@refs/heads/main",
        },
        "metaeditor": {"path": r"C:\\MetaTrader 5\\MetaEditor64.exe", "version": "5.00"},
        "toolchain": {"probe_ok": True},
        "provenance": {
            "source": "github_actions_metaeditor",
            "command": "MetaEditor64.exe /compile:EA.mq5",
            "tool_version": "3.3.0rc7",
            "host": "WIN",
            "recorded_at_utc": "2026-08-12T00:00:00Z",
            "returncode": 0,
        },
        "artifacts": [
            {
                "role": "compile_log",
                "filename": "compile-log.txt",
                "sha256": _sha(log),
                "size_bytes": len(log),
                "required": True,
            },
            {
                "role": "compiled_ex5",
                "filename": "ea.ex5",
                "sha256": _sha(ex5),
                "size_bytes": len(ex5),
                "required": True,
            },
        ],
    }


def test_valid_github_native_record_is_provenance_verified():
    assert validate_github_compile_record(valid_record()).ok is True


@pytest.mark.parametrize("mutation", ["linux", "job", "warnings", "commit", "probe", "artifact_path"])
def test_adversarial_github_compile_record_fails(mutation):
    record = valid_record()
    if mutation == "linux":
        record["runner"]["os"] = "Linux"
    elif mutation == "job":
        record["github"]["job_id"] = "unknown"
    elif mutation == "warnings":
        record["warning_count"] = 1
    elif mutation == "commit":
        record["source_commit"] = "short"
    elif mutation == "probe":
        record["toolchain"]["probe_ok"] = False
    elif mutation == "artifact_path":
        record["artifacts"][0]["filename"] = "../escape.log"
    assert validate_github_compile_record(record).ok is False


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buf.getvalue()


def test_artifact_zip_rejects_path_traversal(tmp_path):
    with pytest.raises(GitHubActionsError):
        safe_extract_artifact_zip(_zip([("../escape.txt", b"x")]), tmp_path / "out")


class Transport:
    def request_json(self, method, path, payload=None):
        if path.endswith("/dispatches"):
            return None
        if "/runs?" in path:
            return {
                "workflow_runs": [
                    {
                        "id": 1,
                        "head_sha": "a" * 40,
                        "display_title": "vkmql-native-old",
                        "html_url": "old",
                    },
                    {
                        "id": 2,
                        "head_sha": "a" * 40,
                        "display_title": "vkmql-native-request123",
                        "html_url": "new",
                    },
                ]
            }
        return {}

    def download(self, path):
        return b""


def test_dispatch_run_correlation_rejects_stale_same_commit_run():
    client = GitHubActionsClient("owner/repo", Transport())
    run = client.find_run("native.yml", head_sha="a" * 40, request_id="request123")
    assert run is not None
    assert run.run_id == 2


def test_compile_pass_does_not_imply_release_pass():
    record = valid_record()
    manifest = EvidenceManifestV2(
        compile=record,
        backtest={"ok": False, "source": "unknown"},
        gates={"ok": False},
        artifacts=[{"exists": True, "sha256": "f" * 64, "required": True}],
        skipped_stages=["backtest", "gate"],
    )
    summary = manifest.evaluate()
    assert summary["compile_ok"] is True
    assert summary["release_eligible"] is False
