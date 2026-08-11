"""RC6 native provenance must bind every build and tester input."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _util import FAKE_EX5, generate_keypair, pin_key, sha256_bytes  # type: ignore

TREE = "rc6-candidate-source-tree"
WHEEL_SHA256 = "1" * 64
CASE_IDS = (
    "abrupt_terminal_kill",
    "restart_reconcile",
    "no_duplicate_order",
    "legacy_v1_migration_restart",
)


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _artifact(path: Path, project: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(project).as_posix(),
        "exists": True,
        "sha256": sha256_bytes(path.read_bytes()),
    }


def build_bound_project(root: Path) -> tuple[Path, object, str]:
    from vibecodekit_mql5.provenance import attestation_payload

    project = root / "BoundEA"
    ir_rel = "evidence/input/EA-IR.json"
    source_manifest_rel = "evidence/input/source-manifest.json"
    set_rel = "evidence/input/test.set"
    ini_rel = "evidence/backtest/tester.ini"
    tester_result_rel = "evidence/backtest/tester-result.json"
    mq5_rel = "evidence/input/project/Experts/BoundEA/BoundEA.mq5"
    mqh_rel = "evidence/input/project/Include/BoundEA/Config.mqh"

    _write(project / ir_rel, '{"schema_version":"1.0","ea_name":"BoundEA"}\n')
    _write(project / set_rel, "RiskPercent=1.0\n")
    _write(
        project / ini_rel,
        "[Tester]\nExpert=evidence/compile/ea.ex5\n"
        "ExpertParameters=evidence/input/test.set\nSymbol=EURUSD\nPeriod=H1\n"
        "FromDate=2025.01.01\nToDate=2025.03.31\n",
    )
    _write(
        project / tester_result_rel,
        '{"symbol":"EURUSD","period":"H1","total_trades":9}\n',
    )
    _write(project / mq5_rel, "#property strict\n#include <BoundEA/Config.mqh>\nvoid OnTick() {}\n")
    _write(project / mqh_rel, "input double RiskPercent=1.0;\n")

    source_manifest = {
        "schema_version": "1.0",
        "generated_by": "installed_candidate_wheel",
        "candidate_source_tree_sha": TREE,
        "ea_entrypoint": mq5_rel,
        "files": [
            {
                "path": rel,
                "size": (project / rel).stat().st_size,
                "sha256": sha256_bytes((project / rel).read_bytes()),
            }
            for rel in (mq5_rel, mqh_rel)
        ],
    }
    _write(project / source_manifest_rel, json.dumps(source_manifest, indent=2) + "\n")

    _write(project / "evidence/compile/compile-log.txt", "0 errors, 0 warnings\n")
    _write(project / "evidence/compile/ea.ex5", FAKE_EX5)
    _write(
        project / "evidence/backtest/report.xml",
        '<?xml version="1.0"?><report><TotalTrades>9</TotalTrades>'
        "<ProfitFactor>1.4</ProfitFactor><NetProfit>20</NetProfit></report>\n",
    )
    case_paths: list[str] = []
    for case_id in CASE_IDS:
        rel = f"evidence/stress/cases/{case_id}.log"
        case_paths.append(rel)
        _write(project / rel, f"native case {case_id}: PASS\n")
    stress = {
        "schema_version": "1.0",
        "status": "PASS",
        "source": "actual_mt5_restart_recovery",
        "candidate_source_tree_sha": TREE,
        "restart_recovery_cases": [
            {"id": case_id, "status": "PASS", "evidence": rel}
            for case_id, rel in zip(CASE_IDS, case_paths, strict=True)
        ],
    }
    _write(
        project / "evidence/stress/stress-matrix-report.json", json.dumps(stress, indent=2) + "\n"
    )
    review = {
        "schema_version": "1.0",
        "status": "PASS",
        "candidate_source_tree_sha": TREE,
        "project_source_manifest_sha256": sha256_bytes(
            (project / source_manifest_rel).read_bytes()
        ),
        "reviewer": "candidate-native-runner",
        "reviewed_at_utc": "2026-08-11T00:00:00Z",
        "release_blockers": [],
        "findings": [],
    }
    _write(project / "evidence/review/deep-review.json", json.dumps(review, indent=2) + "\n")

    artifact_rels = (
        "evidence/compile/compile-log.txt",
        "evidence/compile/ea.ex5",
        "evidence/backtest/report.xml",
        "evidence/stress/stress-matrix-report.json",
        "evidence/review/deep-review.json",
        ir_rel,
        source_manifest_rel,
        set_rel,
        ini_rel,
        tester_result_rel,
        mq5_rel,
        mqh_rel,
        *case_paths,
    )
    stamp = {
        "command": "native.exe",
        "tool_version": "native",
        "host": "WIN-RC6",
        "recorded_at_utc": "2026-08-11T00:00:00Z",
        "returncode": 0,
    }
    manifest = {
        "schema_version": "2.1",
        "release_eligible": True,
        "summary": {"release_eligible": True},
        "artifacts": [_artifact(project / rel, project) for rel in artifact_rels],
        "compile": {
            **stamp,
            "source": "actual_metaeditor",
            "candidate": {
                "kit_version": "3.3.0rc6",
                "build_input_commit": "a" * 40,
                "source_tree_sha": TREE,
                "artifacts": {"tool/vibecodekit_mql5_ea-3.3.0rc6.whl": WHEEL_SHA256},
                "runtime_bundle_sha256": "2" * 64,
            },
            "input_binding": {
                "generated_by": "installed_candidate_wheel",
                "candidate_wheel_sha256": WHEEL_SHA256,
                "ea_ir_sha256": sha256_bytes((project / ir_rel).read_bytes()),
                "source_manifest_sha256": sha256_bytes(
                    (project / source_manifest_rel).read_bytes()
                ),
                "ea_entrypoint": mq5_rel,
                "entrypoint_sha256": sha256_bytes((project / mq5_rel).read_bytes()),
            },
        },
        "backtest": {
            **stamp,
            "source": "actual_mt5_strategy_tester",
            "input_binding": {
                "set_sha256": sha256_bytes((project / set_rel).read_bytes()),
                "tester_ini_sha256": sha256_bytes((project / ini_rel).read_bytes()),
                "symbol": "EURUSD",
                "timeframe": "H1",
                "period": "2025.01.01-2025.03.31",
            },
        },
    }
    private, raw_public, public_b64 = generate_keypair()
    key_id = "rc6-test-runner"
    pin_key(project, key_id, raw_public)
    hashes = {str(item["path"]): str(item["sha256"]) for item in manifest["artifacts"]}
    signature = private.sign(attestation_payload(manifest, hashes))
    manifest["runner_attestation"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature_b64": base64.b64encode(signature).decode(),
    }
    _write(project / "evidence/manifest.json", json.dumps(manifest, indent=2) + "\n")
    return project, private, public_b64


def resign(project: Path, private: object) -> None:
    from vibecodekit_mql5.provenance import artifact_paths_for_manifest, attestation_payload

    path = project / "evidence/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    records = {item["path"]: item for item in manifest["artifacts"]}
    for rel in artifact_paths_for_manifest(manifest):
        digest = sha256_bytes((project / rel).read_bytes())
        records[rel]["sha256"] = digest
        hashes[rel] = digest
    manifest["runner_attestation"]["signature_b64"] = base64.b64encode(
        private.sign(attestation_payload(manifest, hashes))  # type: ignore[attr-defined]
    ).decode()
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class TestRC6NativeProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.project, self.private, self.public_b64 = build_bound_project(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def validate(self):
        from vibecodekit_mql5.provenance import validate_release_provenance

        with patch.dict(os.environ, {"VCK_RUNNER_PUBLIC_KEY_B64": self.public_b64}):
            return validate_release_provenance(self.project)

    def test_complete_schema_21_project_passes_and_chain_covers_every_artifact(self) -> None:
        from vibecodekit_mql5.evidence_attestation import build_hash_chain, verify_hash_chain

        result = self.validate()
        self.assertEqual(result.status, "PASS", result.errors)
        chain = build_hash_chain(self.project)
        manifest = json.loads((self.project / "evidence/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(chain.links), len(manifest["artifacts"]) + 1)
        self.assertTrue(verify_hash_chain(self.project).ok)

    def test_hash_chain_never_follows_a_traversal_path(self) -> None:
        from vibecodekit_mql5.evidence_attestation import build_hash_chain, verify_hash_chain

        build_hash_chain(self.project)
        chain_path = self.project / "evidence/attestation/hash-chain.json"
        chain = json.loads(chain_path.read_text(encoding="utf-8"))
        chain["links"][0]["path"] = "../outside-secret"
        chain_path.write_text(json.dumps(chain), encoding="utf-8")
        result = verify_hash_chain(self.project)
        self.assertFalse(result.ok)
        self.assertTrue(any("unsafe hash-chain evidence path" in error for error in result.errors))

    def test_generated_source_tamper_is_rejected_even_after_outer_resign(self) -> None:
        rel = "evidence/input/project/Experts/BoundEA/BoundEA.mq5"
        (self.project / rel).write_text('void OnTick(){ Print("tampered"); }\n', encoding="utf-8")
        resign(self.project, self.private)
        result = self.validate()
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("source manifest hash mismatch" in error for error in result.errors))

    def test_set_tamper_is_rejected_even_after_outer_resign(self) -> None:
        (self.project / "evidence/input/test.set").write_text("RiskPercent=99\n", encoding="utf-8")
        resign(self.project, self.private)
        result = self.validate()
        self.assertTrue(any("set_sha256 does not match" in error for error in result.errors))

    def test_generated_source_must_bind_the_exact_candidate_wheel(self) -> None:
        manifest_path = self.project / "evidence/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["compile"]["input_binding"]["candidate_wheel_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        resign(self.project, self.private)
        result = self.validate()
        self.assertTrue(any("candidate_wheel_sha256" in error for error in result.errors))

    def test_restart_case_must_reference_a_signed_real_file(self) -> None:
        rel = "evidence/stress/stress-matrix-report.json"
        stress = json.loads((self.project / rel).read_text(encoding="utf-8"))
        stress["restart_recovery_cases"][0]["evidence"] = "native-log://not-a-file"
        (self.project / rel).write_text(json.dumps(stress), encoding="utf-8")
        resign(self.project, self.private)
        result = self.validate()
        self.assertTrue(any("evidence is outside" in error for error in result.errors))

    def test_review_must_bind_exact_generated_source_manifest(self) -> None:
        rel = "evidence/review/deep-review.json"
        review = json.loads((self.project / rel).read_text(encoding="utf-8"))
        review["project_source_manifest_sha256"] = "0" * 64
        (self.project / rel).write_text(json.dumps(review), encoding="utf-8")
        resign(self.project, self.private)
        result = self.validate()
        self.assertTrue(any("does not match generated source" in error for error in result.errors))

    def test_zero_trade_backtest_is_not_release_evidence(self) -> None:
        rel = "evidence/backtest/report.xml"
        (self.project / rel).write_text(
            "<report><TotalTrades>0</TotalTrades><NetProfit>0</NetProfit></report>",
            encoding="utf-8",
        )
        resign(self.project, self.private)
        result = self.validate()
        self.assertTrue(
            any("TotalTrades must be a positive integer" in error for error in result.errors)
        )

    def test_rc6_runner_contract_generates_source_from_ir(self) -> None:
        script = Path(__file__).resolve().parents[3] / "scripts/native/Invoke-RC6NativeEvidence.ps1"
        text = script.read_text(encoding="utf-8")
        self.assertIn("[string]$EaIr", text)
        self.assertIn("mql5-ir-build.exe", text)
        self.assertIn('schema_version = "2.1"', text)
        self.assertNotIn("[string]$EaPath", text)


if __name__ == "__main__":
    unittest.main()
