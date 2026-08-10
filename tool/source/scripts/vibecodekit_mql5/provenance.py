"""Canonical release-evidence provenance validation.

Presence of a file, a parseable JSON manifest, or a valid hash chain is not
proof that MetaEditor/Strategy Tester actually produced the evidence. This
module is the single conservative gate used by both ``check_all`` and the
attestation CLI.
"""
from __future__ import annotations

import base64, json, os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .execution_sources import assess_backtest_source, assess_compile_source
from .release_policy import sha256_file
from .trust_root import TRUST_FILE, fingerprint, load_trust_root

EVIDENCE_MANIFEST = Path("evidence/manifest.json")
CORE_ARTIFACTS = (
    "evidence/compile/compile-log.txt",
    "evidence/compile/ea.ex5",
    "evidence/backtest/report.xml",
    "evidence/stress/stress-matrix-report.json",
    "evidence/review/deep-review.json",
)
REQUIRED_PROVENANCE = ("source", "command", "tool_version", "host", "recorded_at_utc")
REQUIRED_RESTART_CASES = (
    "abrupt_terminal_kill",
    "restart_reconcile",
    "no_duplicate_order",
    "legacy_v1_migration_restart",
)
TRUSTED_RESTART_SOURCES = {
    "actual_mt5_restart_recovery",
    "remote_worker_mt5_restart_recovery",
}
RESOLVED_FINDING_STATES = {"RESOLVED", "CLOSED", "FIXED"}


@dataclass
class ProvenanceResult:
    ok: bool
    status: str = "INCOMPLETE"  # PASS | INCOMPLETE | FAIL
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    project_dir: str = ""
    signed_by_key_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "missing": list(self.missing),
            "signed_by_key_id": self.signed_by_key_id,
        }


def _prov_block(manifest: dict[str, Any], stage: str) -> dict[str, Any]:
    block = manifest.get(stage)
    if not isinstance(block, dict):
        return {}
    nested = block.get("provenance")
    return nested if isinstance(nested, dict) else block


def _has_real_provenance(block: dict[str, Any], stage: str, errors: list[str]) -> None:
    for key in REQUIRED_PROVENANCE:
        if not str(block.get(key) or "").strip():
            errors.append(f"{stage} provenance missing {key}")
    if block.get("returncode", block.get("exit_code", 0)) not in (0, "0", None):
        errors.append(f"{stage} provenance reports non-zero exit code")


def _validate_report(path: Path, errors: list[str]) -> None:
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"backtest report is not valid XML: {exc}")
        return
    tags = {el.tag.rsplit("}", 1)[-1] for el in root.iter()}
    if "TotalTrades" not in tags:
        errors.append("backtest report has no TotalTrades metric")
    if not ({"ProfitFactor", "NetProfit", "ExpectedPayoff"} & tags):
        errors.append("backtest report has no performance metric")


def _load_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return data


def _validate_stress_report(
    path: Path,
    *,
    expected_source_tree_sha: str,
    errors: list[str],
) -> None:
    data = _load_json_object(path, "stress report", errors)
    if data is None:
        return
    if data.get("schema_version") != "1.0":
        errors.append("stress report schema_version must be 1.0")
    if str(data.get("status") or "").upper() != "PASS":
        errors.append("stress report status is not PASS")
    source = str(data.get("source") or "").strip()
    if source not in TRUSTED_RESTART_SOURCES:
        errors.append("stress report source is not trusted native restart/recovery evidence")
    bound_tree = str(data.get("candidate_source_tree_sha") or "").strip()
    if not bound_tree:
        errors.append("stress report missing candidate_source_tree_sha")
    elif expected_source_tree_sha and bound_tree != expected_source_tree_sha:
        errors.append("stress report candidate_source_tree_sha does not match compile candidate")

    cases = data.get("restart_recovery_cases")
    if not isinstance(cases, list):
        errors.append("stress report restart_recovery_cases must be a list")
        return
    by_id: dict[str, dict[str, Any]] = {}
    for raw in cases:
        if not isinstance(raw, dict):
            errors.append("stress report contains a non-object restart recovery case")
            continue
        case_id = str(raw.get("id") or "").strip()
        if not case_id:
            errors.append("stress report contains restart recovery case without id")
            continue
        if case_id in by_id:
            errors.append(f"stress report contains duplicate restart recovery case {case_id}")
            continue
        by_id[case_id] = raw
    for case_id in REQUIRED_RESTART_CASES:
        raw = by_id.get(case_id)
        if raw is None:
            errors.append(f"stress report missing required restart recovery case {case_id}")
            continue
        if str(raw.get("status") or "").upper() != "PASS":
            errors.append(f"stress report restart recovery case {case_id} is not PASS")
        if not str(raw.get("evidence") or "").strip():
            errors.append(f"stress report restart recovery case {case_id} has no evidence reference")


def _validate_review_report(
    path: Path,
    *,
    expected_source_tree_sha: str,
    errors: list[str],
) -> None:
    data = _load_json_object(path, "review report", errors)
    if data is None:
        return
    if data.get("schema_version") != "1.0":
        errors.append("review report schema_version must be 1.0")
    if str(data.get("status") or "").upper() != "PASS":
        errors.append("review report status is not PASS")
    bound_tree = str(data.get("candidate_source_tree_sha") or "").strip()
    if not bound_tree:
        errors.append("review report missing candidate_source_tree_sha")
    elif expected_source_tree_sha and bound_tree != expected_source_tree_sha:
        errors.append("review report candidate_source_tree_sha does not match compile candidate")
    if not str(data.get("reviewer") or "").strip():
        errors.append("review report missing reviewer")
    if not str(data.get("reviewed_at_utc") or "").strip():
        errors.append("review report missing reviewed_at_utc")

    blockers = data.get("release_blockers")
    if not isinstance(blockers, list):
        errors.append("review report release_blockers must be a list")
    elif blockers:
        errors.append("review report still contains release blockers")

    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("review report findings must be a list")
        return
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"review report findings[{index}] is not an object")
            continue
        severity = str(finding.get("severity") or "").upper().strip()
        status = str(finding.get("status") or "").upper().strip()
        if severity in {"P0", "P1"} and status not in RESOLVED_FINDING_STATES:
            errors.append(f"review report has unresolved {severity} finding at index {index}")


def attestation_payload(manifest: dict[str, Any], hashes: dict[str, str]) -> bytes:
    """Canonical bytes signed by the native runner, never by the repo writer."""
    return json.dumps(
        {
            "schema_version": manifest.get("schema_version"),
            "compile": manifest.get("compile"),
            "backtest": manifest.get("backtest"),
            "artifacts": hashes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _verify_runner_attestation(manifest: dict[str, Any], hashes: dict[str, str], result: ProvenanceResult) -> None:
    """Verify detached native-runner signature against an in-repo pinned key."""
    block = manifest.get("runner_attestation")
    if not isinstance(block, dict) or not block.get("signature_b64") or block.get("algorithm") != "Ed25519":
        result.missing.append("external runner Ed25519 attestation")
        return

    key_id = str(block.get("key_id") or "").strip()
    if not key_id:
        result.errors.append("runner attestation does not declare key_id; cannot match a pinned key")
        return

    trust = load_trust_root(result.project_dir or ".")
    if trust.errors:
        result.errors.extend(trust.errors)
        return
    if not trust.present:
        result.missing.append(f"{TRUST_FILE} (pinned runner trust root)")
        return
    if not trust.keys:
        result.missing.append(f"{TRUST_FILE} declares no usable runner key")
        return

    pinned = trust.by_key_id(key_id)
    if pinned is None:
        result.errors.append(
            f"runner key_id {key_id!r} is not pinned in {TRUST_FILE}; "
            f"pinned key_ids are {[k.key_id for k in trust.keys]}"
        )
        return

    public_key = os.environ.get("VCK_RUNNER_PUBLIC_KEY_B64", "").strip()
    if not public_key:
        result.missing.append("VCK_RUNNER_PUBLIC_KEY_B64 (native runner trust root)")
        return

    try:
        raw = base64.b64decode(public_key, validate=True)
    except Exception:  # noqa: BLE001
        result.errors.append("VCK_RUNNER_PUBLIC_KEY_B64 is not valid base64")
        return
    if len(raw) != 32:
        result.errors.append("VCK_RUNNER_PUBLIC_KEY_B64 is not a 32-byte Ed25519 public key")
        return

    supplied = fingerprint(raw)
    if supplied != pinned.public_key_sha256:
        result.errors.append(
            f"supplied runner public key does not match the pin for key_id {key_id!r} "
            f"(pinned {pinned.public_key_sha256[:16]}..., supplied {supplied[:16]}...)"
        )
        return

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(raw)
        key.verify(base64.b64decode(block["signature_b64"]), attestation_payload(manifest, hashes))
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"external runner attestation verification failed: {exc.__class__.__name__}")
        return

    result.signed_by_key_id = key_id


def validate_release_provenance(project_dir: Path | str) -> ProvenanceResult:
    """Validate canonical manifest, native evidence semantics, provenance and hashes."""
    root = Path(project_dir)
    result = ProvenanceResult(ok=False, project_dir=str(root))
    manifest_path = root / EVIDENCE_MANIFEST
    if not manifest_path.is_file():
        result.missing.append(str(EVIDENCE_MANIFEST))
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.status = "FAIL"
        result.errors.append(f"invalid evidence manifest: {exc}")
        return result
    result.manifest = manifest
    if manifest.get("schema_version") != "2.0":
        result.errors.append("manifest schema_version must be 2.0")
    if manifest.get("release_eligible") is not True:
        result.errors.append("manifest release_eligible is not true")
    summary = manifest.get("summary")
    if not isinstance(summary, dict) or summary.get("release_eligible") is not True:
        result.errors.append("manifest summary.release_eligible is not true")

    compile_block = _prov_block(manifest, "compile")
    backtest_block = _prov_block(manifest, "backtest")
    _has_real_provenance(compile_block, "compile", result.errors)
    _has_real_provenance(backtest_block, "backtest", result.errors)
    if not assess_compile_source(compile_block.get("source")).trusted_for_release:
        result.errors.append("compile source is not trusted for release")
    if not assess_backtest_source(backtest_block.get("source"), root / CORE_ARTIFACTS[2]).trusted_for_release:
        result.errors.append("backtest source is not trusted for release")

    artifacts = manifest.get("artifacts")
    by_path = {str(a.get("path")): a for a in artifacts if isinstance(a, dict)} if isinstance(artifacts, list) else {}
    verified_hashes: dict[str, str] = {}
    for rel in CORE_ARTIFACTS:
        path = root / rel
        if not path.is_file():
            result.missing.append(rel)
            continue
        record = by_path.get(rel)
        if not record or record.get("exists") is not True or not record.get("sha256"):
            result.errors.append(f"artifact manifest record missing for {rel}")
        elif record.get("sha256") != sha256_file(path):
            result.errors.append(f"artifact hash mismatch for {rel}")
        else:
            verified_hashes[rel] = str(record.get("sha256"))

    ex5 = root / CORE_ARTIFACTS[1]
    if ex5.is_file() and ex5.stat().st_size < 32:
        result.errors.append("ea.ex5 is implausibly small; refusing fixture/stub binary")
    report = root / CORE_ARTIFACTS[2]
    if report.is_file():
        _validate_report(report, result.errors)

    compile_candidate = compile_block.get("candidate")
    expected_source_tree_sha = (
        str(compile_candidate.get("source_tree_sha") or "").strip()
        if isinstance(compile_candidate, dict)
        else ""
    )
    stress = root / CORE_ARTIFACTS[3]
    if stress.is_file():
        _validate_stress_report(stress, expected_source_tree_sha=expected_source_tree_sha, errors=result.errors)
    review = root / CORE_ARTIFACTS[4]
    if review.is_file():
        _validate_review_report(review, expected_source_tree_sha=expected_source_tree_sha, errors=result.errors)

    if not result.missing:
        _verify_runner_attestation(manifest, verified_hashes, result)

    if result.errors:
        result.status = "FAIL"
    elif result.missing:
        result.status = "INCOMPLETE"
    else:
        result.status = "PASS"
        result.ok = True
    return result
