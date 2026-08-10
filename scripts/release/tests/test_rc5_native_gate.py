from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_RELEASE_DIR = Path(__file__).resolve().parents[1]
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

import rc5_native_gate as gate  # noqa: E402
from vibecodekit_mql5.release_policy import sha256_file  # noqa: E402

HASHES = {
    "tool/vibecodekit-mql5-v3.3.0rc5-source-full.zip": "1" * 64,
    "tool/vibecodekit-mql5-v3.3.0rc5-source-full.manifest.json": "2" * 64,
    "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl": "3" * 64,
    "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip": "4" * 64,
}


def _candidate_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    release = root / "docs/release/v3.3.0rc5"
    release.mkdir(parents=True)
    (release / "RC5-CANDIDATE-MANIFEST.json").write_text(
        json.dumps({
            "kit_version": "3.3.0rc5",
            "build_input_commit": "a" * 40,
            "source_tree_sha": "b" * 40,
            "release_eligible": False,
        }), encoding="utf-8",
    )
    (release / "RC5-ARTIFACTS.sha256").write_text(
        "".join(f"{digest}  {path}\n" for path, digest in HASHES.items()), encoding="utf-8",
    )
    return root, gate.expected_candidate_binding(root)


def _prov(status: str = "PASS", *, errors=None, missing=None):
    data = {
        "ok": status == "PASS", "status": status,
        "errors": list(errors or []), "missing": list(missing or []),
        "signed_by_key_id": "windows-runner-01" if status == "PASS" else "",
    }
    return SimpleNamespace(
        status=status, errors=data["errors"], missing=data["missing"],
        to_dict=lambda: dict(data),
    )


def _write_project(tmp_path: Path, binding: dict[str, str]) -> Path:
    project = tmp_path / "release-evidence/v3.3.0rc5"
    paths = {
        gate.SOURCE_MQ5: b"#property strict\nvoid OnTick(){}\n",
        gate.COMPILED_EX5: b"MZ" + b"native-ex5" * 8,
        gate.COMPILE_LOG: b"OrionRecovery.mq5 : 0 errors, 0 warnings, 123 msec elapsed\n",
        gate.BACKTEST_REPORT: b"<Report><TotalTrades>7</TotalTrades><NetProfit>12.3</NetProfit></Report>\n",
    }
    for rel, data in paths.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    async_data = {
        "schema_version": "1.0", "status": "PASS", "source": "actual_mt5_strategy_tester",
        "partial_fill_observed": True, "duplicate_order_count": 0,
        "intent_ids_unique": True,
        "state_sequence": ["PREPARED", "SUBMITTED", "PARTIAL", "COMPLETED"],
    }
    restart_data = {
        "schema_version": "1.0", "status": "PASS", "source": "actual_mt5_strategy_tester",
        "interruption_observed": True, "persisted_intent_reloaded": True,
        "duplicate_order_count": 0, "resolution": "TERMINAL_PROOF",
    }
    for rel, data in ((gate.ASYNC_REPORT, async_data), (gate.RESTART_REPORT, restart_data)):
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    manifest = {
        "schema_version": "2.0", "release_eligible": True,
        "summary": {"release_eligible": True},
        "compile": {
            "ok": True, "source": "actual_metaeditor", "tool_version": "MetaEditor build 5260",
            "errors": 0, "mq5_sha256": sha256_file(project / gate.SOURCE_MQ5),
            "ex5_sha256": sha256_file(project / gate.COMPILED_EX5),
            "candidate_binding": dict(binding),
        },
        "backtest": {
            "ok": True, "source": "actual_mt5_strategy_tester", "tool_version": "MT5 build 5260",
            "candidate_binding": dict(binding),
            "tester": {
                "symbol": "EURUSD", "timeframe": "H1", "model": "1-minute OHLC",
                "from_date": "2025.01.01", "to_date": "2025.03.31",
            },
            "native_scenarios": {
                "async_fill": {
                    "path": gate.ASYNC_REPORT.as_posix(),
                    "sha256": sha256_file(project / gate.ASYNC_REPORT), "status": "PASS",
                },
                "restart_recovery": {
                    "path": gate.RESTART_REPORT.as_posix(),
                    "sha256": sha256_file(project / gate.RESTART_REPORT), "status": "PASS",
                },
            },
        },
    }
    manifest_path = project / gate.EVIDENCE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return project


def _manifest(project: Path) -> dict:
    return json.loads((project / gate.EVIDENCE_MANIFEST).read_text(encoding="utf-8"))


def _save_manifest(project: Path, data: dict) -> None:
    (project / gate.EVIDENCE_MANIFEST).write_text(json.dumps(data), encoding="utf-8")


def test_expected_candidate_binding_is_exact_task09_identity(tmp_path: Path):
    repo, binding = _candidate_repo(tmp_path)
    assert binding == {
        "kit_version": "3.3.0rc5", "source_tree_sha": "b" * 40,
        "build_input_commit": "a" * 40, "source_zip_sha256": "1" * 64,
        "source_manifest_sha256": "2" * 64, "wheel_sha256": "3" * 64,
        "runtime_bundle_sha256": "4" * 64,
    }
    assert gate.expected_candidate_binding(repo) == binding


def test_missing_native_manifest_is_blocked_not_pass(tmp_path: Path):
    repo, _ = _candidate_repo(tmp_path)
    result = gate.validate_rc5_native_evidence(repo, tmp_path / "missing-project")
    assert result.status == "BLOCKED" and result.ok is False
    assert "evidence/manifest.json" in result.missing


def test_valid_signed_semantics_pass_when_generic_provenance_passes(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "PASS", result.to_dict()
    assert result.ok is True and all(result.checks.values())


def test_candidate_binding_mismatch_is_fail(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    data = _manifest(project)
    data["compile"]["candidate_binding"]["wheel_sha256"] = "f" * 64
    _save_manifest(project, data)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL"
    assert any("wheel_sha256 mismatch" in err for err in result.errors)


def test_async_duplicate_order_is_release_failure(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    async_path = project / gate.ASYNC_REPORT
    data = json.loads(async_path.read_text(encoding="utf-8")); data["duplicate_order_count"] = 1
    async_path.write_text(json.dumps(data), encoding="utf-8")
    manifest = _manifest(project)
    manifest["backtest"]["native_scenarios"]["async_fill"]["sha256"] = sha256_file(async_path)
    _save_manifest(project, manifest)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL" and "async-fill evidence reports duplicate orders" in result.errors


def test_restart_requires_terminal_proof_or_operator_required(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    restart_path = project / gate.RESTART_REPORT
    data = json.loads(restart_path.read_text(encoding="utf-8")); data["resolution"] = "BLIND_RETRY"
    restart_path.write_text(json.dumps(data), encoding="utf-8")
    manifest = _manifest(project)
    manifest["backtest"]["native_scenarios"]["restart_recovery"]["sha256"] = sha256_file(restart_path)
    _save_manifest(project, manifest)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL"
    assert any("TERMINAL_PROOF or OPERATOR_REQUIRED" in err for err in result.errors)


def test_compile_log_error_count_cannot_be_overridden_by_manifest(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    (project / gate.COMPILE_LOG).write_text("OrionRecovery.mq5 : 2 errors, 0 warnings\n", encoding="utf-8")
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL" and "MetaEditor compile reports 2 error(s)" in result.errors


def test_signed_scenario_hash_mismatch_fails(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    with (project / gate.ASYNC_REPORT).open("a", encoding="utf-8") as handle:
        handle.write("\n")
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("PASS"))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL" and any("SHA-256 mismatch" in err for err in result.errors)


def test_generic_provenance_fail_remains_fail(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("FAIL", errors=["runner key is not pinned"]))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "FAIL" and "runner key is not pinned" in result.errors


def test_generic_provenance_incomplete_remains_blocked(tmp_path: Path, monkeypatch):
    repo, binding = _candidate_repo(tmp_path)
    project = _write_project(tmp_path, binding)
    monkeypatch.setattr(gate, "validate_release_provenance", lambda _: _prov("INCOMPLETE", missing=["VCK_RUNNER_PUBLIC_KEY_B64"]))
    result = gate.validate_rc5_native_evidence(repo, project)
    assert result.status == "BLOCKED" and "VCK_RUNNER_PUBLIC_KEY_B64" in result.missing
