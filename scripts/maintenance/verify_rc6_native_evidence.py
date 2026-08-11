#!/usr/bin/env python3
"""Verify RC6 native evidence and exact candidate/source/input binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPTS = ROOT / "tool" / "source" / "scripts"
if str(SOURCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SOURCE_SCRIPTS))

from vibecodekit_mql5.evidence_attestation import (
    evaluate_release_evidence,
)

RELEASE_DIR = ROOT / "docs/release/v3.3.0rc6"
CANDIDATE_MANIFEST = RELEASE_DIR / "RC6-CANDIDATE-MANIFEST.json"
ARTIFACT_HASHES = RELEASE_DIR / "RC6-ARTIFACTS.sha256"
DEFAULT_NATIVE_PROJECT = RELEASE_DIR / "native-evidence/project"
RUNTIME_BUNDLE = ROOT / "VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def expected_candidate() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not CANDIDATE_MANIFEST.is_file():
        return {}, [f"candidate manifest missing: {CANDIDATE_MANIFEST}"]
    manifest = read_json(CANDIDATE_MANIFEST)
    if manifest.get("kit_version") != "3.3.0rc6":
        errors.append("candidate manifest kit_version is not 3.3.0rc6")
    records = (
        manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    )
    artifact_map: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            errors.append("candidate manifest contains a non-object artifact")
            continue
        rel = str(record.get("path") or "")
        expected = str(record.get("sha256") or "")
        path = ROOT / rel
        if not rel or not expected or not path.is_file():
            errors.append(
                f"candidate artifact missing or malformed: {rel or '<empty>'}"
            )
            continue
        if sha256(path) != expected:
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

    return {
        "kit_version": manifest.get("kit_version"),
        "build_input_commit": manifest.get("build_input_commit"),
        "source_tree_sha": manifest.get("source_tree_sha"),
        "artifacts": artifact_map,
        "runtime_bundle_sha256": runtime_expected,
    }, errors


def candidate_binding_errors(
    native_manifest: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    if native_manifest.get("schema_version") != "2.1":
        return ["RC6 native evidence manifest schema_version is not 2.1"]
    compile_block = native_manifest.get("compile")
    if not isinstance(compile_block, dict):
        return ["native evidence manifest has no compile block"]
    actual = compile_block.get("candidate")
    if not isinstance(actual, dict):
        return ["signed compile provenance has no candidate binding"]
    errors: list[str] = []
    for key in (
        "kit_version",
        "build_input_commit",
        "source_tree_sha",
        "runtime_bundle_sha256",
    ):
        if actual.get(key) != expected.get(key):
            errors.append(f"candidate binding mismatch for {key}")
    if actual.get("artifacts") != expected.get("artifacts"):
        errors.append("candidate binding artifact map mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-project", default=str(DEFAULT_NATIVE_PROJECT))
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    expected, errors = expected_candidate()
    project = Path(args.native_project)
    report: dict[str, Any] = {
        "task": "RC6-native-evidence",
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
            result = evaluate_release_evidence(project)
            report["provenance"] = result.to_dict()
            if result.status == "PASS" and not errors:
                report["native_status"] = "PASS"
                report["release_eligible"] = True
            else:
                report["native_status"] = result.status
                errors.extend(item for item in result.errors if item not in errors)
                errors.extend(f"missing: {item}" for item in result.missing)
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
