"""Canonical release-evidence provenance validation.

Presence of a file, a parseable JSON manifest, or a valid hash chain is not
proof that MetaEditor/Strategy Tester actually produced the evidence.  This
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
    # An empty ``<report/>`` is a fixture, not a Strategy Tester result.  A
    # real report must expose at least one metric and a trade count.
    tags = {el.tag.rsplit("}", 1)[-1] for el in root.iter()}
    if "TotalTrades" not in tags:
        errors.append("backtest report has no TotalTrades metric")
    if not ({"ProfitFactor", "NetProfit", "ExpectedPayoff"} & tags):
        errors.append("backtest report has no performance metric")

def attestation_payload(manifest: dict[str, Any], hashes: dict[str, str]) -> bytes:
    """Canonical bytes signed by the native runner, never by the repo writer."""
    return json.dumps({"schema_version": manifest.get("schema_version"), "compile": manifest.get("compile"), "backtest": manifest.get("backtest"), "artifacts": hashes}, sort_keys=True, separators=(",", ":")).encode()

def _verify_runner_attestation(manifest: dict[str, Any], hashes: dict[str, str], result: ProvenanceResult) -> None:
    """Verify the detached native-runner signature against a *pinned* key.

    Two independent conditions must both hold:

    1. The signature verifies over the canonical payload.
    2. The key that made it is named in the project's ``RELEASE-TRUST.yaml``
       pin, matched by ``key_id`` **and** by SHA-256 fingerprint.

    Condition 2 is what closes ADV-6. Verifying a signature against a key
    supplied by the same party that produced the evidence proves only internal
    consistency, not provenance: an attacker can always generate a fresh
    keypair and sign their own forgery. Requiring the key to match an in-repo
    pin means a forged release must additionally modify a reviewed, hash-chained
    contract artifact -- a visible act rather than an invisible one.

    Failure taxonomy is deliberate:
      * absent signature / absent pin / absent env key -> ``missing`` (INCOMPLETE)
      * present but wrong / unpinned / malformed       -> ``errors`` (FAIL)
    An unpinned key is an active rejection, never a silent pass.
    """
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
        # The ADV-6 path lands exactly here: a well-formed, self-generated key
        # that signs perfectly but was never authorised for this project.
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
    """Validate canonical manifest, trusted execution provenance and hashes."""
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
    stress = root / CORE_ARTIFACTS[3]
    review = root / CORE_ARTIFACTS[4]
    for path, label in ((stress, "stress report"), (review, "review report")):
        if path.is_file():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{label} is not valid JSON: {exc}")

    # A manifest is author-controlled. Release provenance therefore requires a
    # detached Ed25519 signature made by a configured native runner key.
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
