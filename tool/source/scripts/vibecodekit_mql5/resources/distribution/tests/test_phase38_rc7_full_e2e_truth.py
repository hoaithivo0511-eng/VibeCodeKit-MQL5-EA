import hashlib
import json
from pathlib import Path

from vibecodekit_mql5 import provenance


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repo_root() -> Path | None:
    source_root = Path(__file__).resolve().parents[1]
    candidate = source_root.parents[1]
    if (candidate / "README.md").is_file() and (candidate / ".github").is_dir():
        return candidate
    return None


def _valid_github_record(log: bytes, ex5: bytes) -> dict:
    return {
        "schema_version": "1.0",
        "source": "github_actions_metaeditor",
        "ok": True,
        "status": "PASS",
        "error_count": 0,
        "warning_count": 0,
        "failure_codes": [],
        "target": "Experts/ProbeEA.mq5",
        "target_sha256": "a" * 64,
        "staged_sha256": "b" * 64,
        "log_sha256": _sha_bytes(log),
        "ex5_sha256": _sha_bytes(ex5),
        "source_commit": "c" * 40,
        "source_tree_sha": "d" * 40,
        "runner": {"os": "Windows", "arch": "X64", "name": "runner"},
        "github": {
            "repository": "owner/repo",
            "run_id": "123",
            "job_id": "456",
            "workflow_ref": "owner/repo/.github/workflows/native.yml@refs/heads/main",
        },
        "metaeditor": {
            "path": r"C:\\Program Files\\MetaTrader 5\\MetaEditor64.exe",
            "version": "5.0.0.6111",
            "installer_sha256": "e" * 64,
        },
        "toolchain": {"probe_ok": True, "stdlib_warmed": False},
        "provenance": {
            "source": "github_actions_metaeditor",
            "command": "MetaEditor64.exe /compile:ProbeEA.mq5",
            "tool_version": "3.3.0rc7",
            "host": "WIN-RUNNER",
            "recorded_at_utc": "2026-08-12T00:00:00Z",
            "returncode": 0,
        },
        "artifacts": [
            {
                "role": "compile_log",
                "filename": "compile-log.txt",
                "sha256": _sha_bytes(log),
                "size_bytes": len(log),
                "required": True,
            },
            {
                "role": "compiled_ex5",
                "filename": "ea.ex5",
                "sha256": _sha_bytes(ex5),
                "size_bytes": len(ex5),
                "required": True,
            },
        ],
    }


def _write_release_fixture(root: Path, *, github_record: dict) -> None:
    files: dict[str, bytes] = {
        "evidence/compile/compile-log.txt": b"Result: 0 errors, 0 warnings\n",
        "evidence/compile/ea.ex5": b"X" * 128,
        "evidence/backtest/report.xml": (
            b"<Report><TotalTrades>12</TotalTrades><ProfitFactor>1.5</ProfitFactor></Report>"
        ),
        "evidence/stress/stress-matrix-report.json": json.dumps(
            {
                "schema_version": "1.0",
                "status": "PASS",
                "source": "actual_mt5_restart_recovery",
                "candidate_source_tree_sha": "d" * 40,
                "restart_recovery_cases": [
                    {"id": case, "status": "PASS", "evidence": f"case-{case}.json"}
                    for case in provenance.REQUIRED_RESTART_CASES
                ],
            }
        ).encode(),
        "evidence/review/deep-review.json": json.dumps(
            {
                "schema_version": "1.0",
                "status": "PASS",
                "candidate_source_tree_sha": "d" * 40,
                "reviewer": "test-reviewer",
                "reviewed_at_utc": "2026-08-12T00:00:00Z",
                "release_blockers": [],
                "findings": [],
            }
        ).encode(),
    }
    for rel, payload in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    backtest = {
        "ok": True,
        "source": "actual_mt5_strategy_tester",
        "command": "terminal64.exe /config:tester.ini",
        "tool_version": "3.3.0rc7",
        "host": "WIN-RUNNER",
        "recorded_at_utc": "2026-08-12T00:00:00Z",
        "returncode": 0,
    }
    artifacts = []
    for rel in provenance.CORE_ARTIFACTS:
        path = root / rel
        artifacts.append(
            {
                "path": rel,
                "exists": True,
                "sha256": provenance.sha256_file(path),
            }
        )
    manifest = {
        "schema_version": "2.0",
        "release_eligible": True,
        "summary": {"release_eligible": True},
        "compile": github_record,
        "backtest": backtest,
        "artifacts": artifacts,
    }
    manifest_path = root / "evidence/manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_valid_github_native_record_crosses_final_release_provenance_gate(
    tmp_path, monkeypatch
) -> None:
    log = b"Result: 0 errors, 0 warnings\n"
    ex5 = b"X" * 128
    record = _valid_github_record(log, ex5)
    _write_release_fixture(tmp_path, github_record=record)
    monkeypatch.setattr(provenance, "_verify_runner_attestation", lambda *args: None)

    result = provenance.validate_release_provenance(tmp_path)

    assert result.status == "PASS", result.to_dict()
    assert "compile source is not trusted for release" not in result.errors


def test_invalid_github_native_record_is_rejected_by_final_release_provenance(
    tmp_path, monkeypatch
) -> None:
    log = b"Result: 0 errors, 0 warnings\n"
    ex5 = b"X" * 128
    record = _valid_github_record(log, ex5)
    record["runner"]["os"] = "Linux"
    _write_release_fixture(tmp_path, github_record=record)
    monkeypatch.setattr(provenance, "_verify_runner_attestation", lambda *args: None)

    result = provenance.validate_release_provenance(tmp_path)

    assert result.status == "FAIL"
    assert any("GitHub native compile" in error for error in result.errors)


def test_active_docs_describe_rc7_and_vibecodev5_current_workflow() -> None:
    repo = _repo_root()
    if repo is None:
        return

    root_readme = (repo / "README.md").read_text(encoding="utf-8")
    structure = (repo / "STRUCTURE.md").read_text(encoding="utf-8")
    status = (repo / "docs/release/v3.3.0rc7/RC7-CANDIDATE-STATUS.md").read_text(
        encoding="utf-8"
    )
    docs = repo / "tool/source/docs"
    command_doc = (docs / "COMMANDS.md").read_text(encoding="utf-8")
    quickstart = (docs / "QUICKSTART.md").read_text(encoding="utf-8")
    usage = (docs / "USAGE-en.md").read_text(encoding="utf-8")
    user_guide = (docs / "USER-GUIDE-en.md").read_text(encoding="utf-8")
    doc_map = (docs / "DOC-MAP.md").read_text(encoding="utf-8")

    for text in (root_readme, structure, status, command_doc, quickstart, usage, user_guide, doc_map):
        assert "3.3.0rc7" in text

    assert "The 8-step build philosophy" not in usage
    assert "current `v3.3.0rc6` baseline" not in user_guide
    assert "139-command RC6 catalog" not in usage
    assert "v3.3.0rc6 baseline contains" not in command_doc
    assert "SCAN → RRI → SPECIFY → DECIDE → CONTRACT → PLAN → BUILD → VERIFY → EVIDENCE → RETRO" in root_readme
    assert "github-actions" in quickstart
    assert "docs/release/v3.3.0rc7/" in doc_map
