#!/usr/bin/env python3
"""Verify RC5 Task 10 native evidence without manufacturing trust.

The verifier has two modes:
- default: validate the package candidate and report native evidence as PENDING
  when no signed native project is present;
- --require-pass: require a complete, trusted, signed MetaEditor/MT5 evidence
  project and fail otherwise.

A PASS is bound to the exact RC5 package candidate through a candidate block
inside the signed compile provenance payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPTS = ROOT / "tool" / "source" / "scripts"
if str(SOURCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SOURCE_SCRIPTS))

from vibecodekit_mql5.evidence_attestation import evaluate_release_evidence  # noqa: E402

CANDIDATE_MANIFEST = ROOT / "docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json"
ARTIFACT_HASHES = ROOT / "docs/release/v3.3.0rc5/RC5-ARTIFACTS.sha256"
DEFAULT_NATIVE_PROJECT = ROOT / "docs/release/v3.3.0rc5/native-evidence/project"
RUNTIME_BUNDLE = ROOT / "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_candidate() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest = read_json(CANDIDATE_MANIFEST)
    if manifest.get("kit_version") != "3.3.0rc5":
        errors.append("candidate manifest kit_version is not 3.3.0rc5")
    records = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    artifact_map: dict[str, str] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rel = str(rec.get("path") or "")
        expected = str(rec.get("sha256") or "")
        path = ROOT / rel
        if not rel or not expected or not path.is_file():
            errors.append(f"candidate artifact missing or malformed: {rel or '<empty>'}")
            continue
        actual = sha256(path)
        if actual != expected:
            errors.append(f"candidate artifact hash mismatch: {rel}")
        artifact_map[rel] = expected

    runtime_expected = ""
    if ARTIFACT_HASHES.is_file():
        for line in ARTIFACT_HASHES.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1] == RUNTIME_BUNDLE.name:
                runtime_expected = parts[0]
                break
    if not runtime_expected or not RUNTIME_BUNDLE.is_file():
        errors.append("runtime candidate bundle hash record is missing")
    elif sha256(RUNTIME_BUNDLE) != runtime_expected:
        errors.append("runtime candidate bundle hash mismatch")

    binding = {
        "kit_version": manifest.get("kit_version"),
        "build_input_commit": manifest.get("build_input_commit"),
        "source_tree_sha": manifest.get("source_tree_sha"),
        "artifacts": artifact_map,
        "runtime_bundle_sha256": runtime_expected,
    }
    return binding, errors


def candidate_binding_errors(native_manifest: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    compile_block = native_manifest.get("compile")
    if not isinstance(compile_block, dict):
        return ["native evidence manifest has no compile block"]
    actual = compile_block.get("candidate")
    if not isinstance(actual, dict):
        return ["signed compile provenance has no candidate binding"]
    errors: list[str] = []
    for key in ("kit_version", "build_input_commit", "source_tree_sha", "runtime_bundle_sha256"):
        if actual.get(key) != expected.get(key):
            errors.append(f"candidate binding mismatch for {key}")
    if actual.get("artifacts") != expected.get("artifacts"):
        errors.append("candidate binding artifact map mismatch")
    return errors


def restart_contract_errors(project: Path) -> list[str]:
    path = project / "evidence/stress/stress-matrix-report.json"
    if not path.is_file():
        return ["restart/crash stress evidence is missing"]
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"restart/crash stress evidence is invalid JSON: {exc}"]
    cases = data.get("restart_recovery_cases")
    if not isinstance(cases, list):
        return ["stress report has no restart_recovery_cases list"]
    required = {
        "abrupt_terminal_kill",
        "restart_reconcile",
        "no_duplicate_order",
        "legacy_v1_migration_restart",
    }
    status = {
        str(item.get("id")): str(item.get("status", "")).upper()
        for item in cases
        if isinstance(item, dict)
    }
    errors = []
    for case in sorted(required):
        if status.get(case) != "PASS":
            errors.append(f"restart recovery case {case} is not PASS")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--native-project", default=str(DEFAULT_NATIVE_PROJECT))
    ap.add_argument("--require-pass", action="store_true")
    args = ap.parse_args()

    expected, errors = expected_candidate()
    project = Path(args.native_project)
    report: dict[str, Any] = {
        "task": "PR-10-native-evidence",
        "candidate_ok": not errors,
        "candidate": expected,
        "native_project": str(project),
        "native_status": "PENDING",
        "release_eligible": False,
        "errors": list(errors),
    }

    manifest_path = project / "evidence/manifest.json"
    if project.is_dir() and manifest_path.is_file():
        try:
            native_manifest = read_json(manifest_path)
            errors.extend(candidate_binding_errors(native_manifest, expected))
            errors.extend(restart_contract_errors(project))
            result = evaluate_release_evidence(project)
            report["provenance"] = result.to_dict()
            if result.status == "PASS" and not errors:
                report["native_status"] = "PASS"
                report["release_eligible"] = True
            else:
                report["native_status"] = result.status
                errors.extend(x for x in result.errors if x not in errors)
                errors.extend(f"missing: {x}" for x in result.missing)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"native evidence verification failed: {exc}")
            report["native_status"] = "FAIL"

    report["errors"] = errors
    print(json.dumps(report, indent=2, sort_keys=True))

    if errors and report["native_status"] == "FAIL":
        return 2
    if args.require_pass and report["native_status"] != "PASS":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
