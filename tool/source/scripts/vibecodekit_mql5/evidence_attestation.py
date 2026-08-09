"""Evidence hash-chain + release attestation (v3 governance).

The release gate's final guard: bind every piece of evidence (compile log,
EX5 binary, tester report, stress report, deep-review report) into a tamper-
evident hash chain, then produce a signed release attestation + ship
manifest. If any evidence file changes after attestation, verification fails;
if a ship manifest claims ``release_eligible`` with a broken chain, it is
rejected.

This reuses :func:`release_policy.sha256_file` for file hashing (anti-bloat
rule #4: one hashing helper for the whole kit).

Public API::

    build_hash_chain(project_dir, evidence_files) -> HashChain
    verify_hash_chain(project_dir) -> VerifyResult
    create_release_attestation(project_dir, *, release_eligible) -> AttestationResult

Outputs into the project dir:
    evidence/attestation/hash-chain.json
    evidence/attestation/signature.json
    release/ship-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from .release_policy import sha256_file
from .provenance import validate_release_provenance

TOOL = "mql5-evidence-attestation"
ATTEST_SUBDIR = "evidence/attestation"
HASH_CHAIN = "hash-chain.json"
SIGNATURE = "signature.json"
SHIP_MANIFEST = "release/ship-manifest.json"
SCHEMA_VERSION = "2.6"

# Default evidence inputs to hash, relative to the project dir. Missing files
# are recorded with exists=False so the chain documents what was absent.
DEFAULT_EVIDENCE: tuple[str, ...] = (
    "evidence/compile/compile-log.txt",
    "evidence/compile/ea.ex5",
    "evidence/backtest/report.xml",
    "evidence/stress/stress-matrix-report.json",
    "evidence/review/deep-review.json",
    "evidence/manifest.json",
)

# Core evidence that MUST physically exist before a build can be called
# release-eligible. A valid hash chain over *absent* files proves nothing, so
# release-eligibility additionally requires every one of these to be present
# AND evidence/manifest.json to assert release_eligible == true.
CORE_EVIDENCE_REQUIRED: tuple[str, ...] = (
    "evidence/compile/compile-log.txt",
    "evidence/compile/ea.ex5",
    "evidence/backtest/report.xml",
    "evidence/stress/stress-matrix-report.json",
    "evidence/review/deep-review.json",
    "evidence/manifest.json",
)
EVIDENCE_MANIFEST = "evidence/manifest.json"


@dataclass
class HashChain:
    root: str
    links: list[dict[str, Any]] = field(default_factory=list)
    created_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_by": TOOL,
            "created_at_utc": self.created_at_utc,
            "root": self.root,
            "links": list(self.links),
        }


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recomputed_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "recomputed_root": self.recomputed_root,
        }


@dataclass
class AttestationResult:
    ok: bool
    release_eligible: bool
    chain_root: str | None = None
    chain_path: str | None = None
    signature_path: str | None = None
    ship_manifest_path: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "release_eligible": self.release_eligible,
            "chain_root": self.chain_root,
            "chain_path": self.chain_path,
            "signature_path": self.signature_path,
            "ship_manifest_path": self.ship_manifest_path,
            "errors": list(self.errors),
        }


def _link_hash(prev: str, rel_path: str, file_sha: str) -> str:
    """Compute a chained hash: H(prev || path || file_sha)."""
    h = hashlib.sha256()
    h.update(prev.encode("utf-8"))
    h.update(rel_path.encode("utf-8"))
    h.update(file_sha.encode("utf-8"))
    return h.hexdigest()


def build_hash_chain(
    project_dir: Path | str,
    evidence_files: list[str] | None = None,
    *,
    write: bool = True,
) -> HashChain:
    """Build a tamper-evident hash chain over the project's evidence files."""
    project_dir = Path(project_dir)
    files = list(evidence_files) if evidence_files is not None else list(DEFAULT_EVIDENCE)

    prev = hashlib.sha256(b"vibecodekit-mql5-ea/evidence-chain/v2.6").hexdigest()
    links: list[dict[str, Any]] = []
    for rel in files:
        abs_path = project_dir / rel
        exists = abs_path.is_file()
        file_sha = sha256_file(abs_path) if exists else ""
        chained = _link_hash(prev, rel, file_sha)
        links.append({
            "path": rel,
            "exists": exists,
            "sha256": file_sha,
            "chained": chained,
        })
        prev = chained

    chain = HashChain(
        root=prev,
        links=links,
        created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    if write:
        out_dir = project_dir / ATTEST_SUBDIR
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / HASH_CHAIN).write_text(json.dumps(chain.to_dict(), indent=2) + "\n", encoding="utf-8")
    return chain


def verify_hash_chain(project_dir: Path | str) -> VerifyResult:
    """Recompute the hash chain and compare to the stored attestation.

    Fails if any evidence file changed after attestation (sha mismatch) or if
    the recomputed root differs from the stored root.
    """
    project_dir = Path(project_dir)
    chain_path = project_dir / ATTEST_SUBDIR / HASH_CHAIN
    if not chain_path.is_file():
        return VerifyResult(ok=False, errors=[f"missing {ATTEST_SUBDIR}/{HASH_CHAIN}"])
    try:
        stored = json.loads(chain_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return VerifyResult(ok=False, errors=[f"invalid hash-chain JSON: {exc}"])

    errors: list[str] = []
    warnings: list[str] = []
    prev = hashlib.sha256(b"vibecodekit-mql5-ea/evidence-chain/v2.6").hexdigest()
    for link in stored.get("links", []):
        rel = link.get("path", "")
        abs_path = project_dir / rel
        exists_now = abs_path.is_file()
        sha_now = sha256_file(abs_path) if exists_now else ""
        if exists_now != bool(link.get("exists")):
            errors.append(f"evidence presence changed for {rel} (existed={link.get('exists')}, now={exists_now})")
        if sha_now != link.get("sha256", ""):
            errors.append(f"evidence changed after attestation: {rel}")
        prev = _link_hash(prev, rel, sha_now)

    if prev != stored.get("root"):
        errors.append("recomputed hash-chain root does not match stored root")
    return VerifyResult(ok=not errors, errors=errors, warnings=warnings, recomputed_root=prev)


@dataclass
class ReleaseEvidenceResult:
    status: str  # "PASS" | "INCOMPLETE" | "FAIL"
    chain_valid: bool = False
    core_evidence_present: bool = False
    manifest_valid: bool = False
    release_eligible_consistent: bool = False
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def release_ready(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "chain_valid": self.chain_valid,
            "core_evidence_present": self.core_evidence_present,
            "manifest_valid": self.manifest_valid,
            "release_eligible_consistent": self.release_eligible_consistent,
            "missing": list(self.missing),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }


def evaluate_release_evidence(project_dir: Path | str) -> ReleaseEvidenceResult:
    """Decide whether a project carries *complete, consistent* release evidence.

    A valid hash chain alone is NOT sufficient — the chain can be valid while
    every evidence file is absent (it just hashes their absence). Release
    readiness therefore requires, all together:

      * a hash chain that verifies (no tamper),
      * every file in :data:`CORE_EVIDENCE_REQUIRED` physically present,
      * a parseable ``evidence/manifest.json`` whose ``release_eligible`` is
        literally ``true``.

    Status:
      PASS        all of the above hold,
      FAIL        the stored chain exists but no longer verifies (tamper),
      INCOMPLETE  no attestation yet, or evidence missing / manifest not eligible.
    """
    project_dir = Path(project_dir)
    res = ReleaseEvidenceResult(status="INCOMPLETE")

    chain_path = project_dir / ATTEST_SUBDIR / HASH_CHAIN
    chain_present = chain_path.is_file()
    verify = verify_hash_chain(project_dir)
    res.chain_valid = verify.ok
    if chain_present:
        res.errors.extend(verify.errors)

    # 1) core evidence presence
    res.missing = [rel for rel in CORE_EVIDENCE_REQUIRED if not (project_dir / rel).is_file()]
    res.core_evidence_present = not res.missing

    # 2) manifest validity + eligibility.  A manifest is only meaningful when
    # its execution provenance and artifact hashes are independently checked.
    manifest_path = project_dir / EVIDENCE_MANIFEST
    manifest_eligible = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            res.manifest_valid = True
            manifest_eligible = manifest.get("release_eligible") is True
            if not manifest_eligible:
                res.warnings.append("evidence/manifest.json: release_eligible is not true")
        except Exception as exc:  # noqa: BLE001
            res.errors.append(f"evidence/manifest.json invalid: {exc}")

    prov = validate_release_provenance(project_dir)
    res.provenance = prov.to_dict()
    if prov.errors:
        res.errors.extend(prov.errors)
    if prov.missing:
        res.missing.extend(x for x in prov.missing if x not in res.missing)
    res.manifest_valid = res.manifest_valid and prov.status == "PASS"

    res.release_eligible_consistent = (
        res.chain_valid
        and res.core_evidence_present
        and res.manifest_valid
        and manifest_eligible
    )

    # 3) derive status
    #
    # Distinguishing FAIL from INCOMPLETE matters operationally: INCOMPLETE
    # means "not configured / not run yet" and is the normal state of a
    # work-in-progress project, whereas FAIL means "something asserted a
    # release claim that does not hold". Collapsing an active rejection into
    # INCOMPLETE would bury a hostile signal in routine noise -- an attacker
    # presenting an unauthorised signing key would look identical to a
    # developer who simply had not run the tester yet.
    if res.release_eligible_consistent and prov.status == "PASS":
        res.status = "PASS"
    elif chain_present and not verify.ok:
        res.status = "FAIL"  # tamper: chain exists but no longer matches evidence
    elif prov.status == "FAIL" or res.errors:
        res.status = "FAIL"  # an assertion was made and it did not hold
    else:
        res.status = "INCOMPLETE"
    return res


def create_release_attestation(
    project_dir: Path | str,
    *,
    release_eligible: bool,
    evidence_files: list[str] | None = None,
) -> AttestationResult:
    """Build the chain, sign it, and write the ship manifest.

    A ship manifest may only claim ``release_eligible=true`` when the freshly
    built chain verifies. If the caller asserts eligibility but the chain is
    invalid, the manifest is forced to ``release_eligible=false``.
    """
    project_dir = Path(project_dir)
    chain = build_hash_chain(project_dir, evidence_files, write=True)
    verify = verify_hash_chain(project_dir)
    evidence = evaluate_release_evidence(project_dir)

    # A build is only release-eligible when the caller asked for it AND the full
    # evidence set is present, consistent, and the chain verifies. A valid chain
    # over absent evidence can never flip this to true.
    effective_eligible = bool(release_eligible and evidence.release_ready)
    errors: list[str] = list(verify.errors)
    if release_eligible and not evidence.release_ready:
        detail: list[str] = []
        if not evidence.chain_valid:
            detail.append("hash chain invalid")
        if evidence.missing:
            detail.append("missing evidence: " + ", ".join(evidence.missing))
        if (
            evidence.manifest_valid
            and not evidence.release_eligible_consistent
            and not evidence.missing
            and evidence.chain_valid
        ):
            detail.append("evidence/manifest.json release_eligible is not true")
        errors.append(
            "release_eligible requested but evidence incomplete — forced to false"
            + (f" ({'; '.join(detail)})" if detail else "")
        )

    attest_dir = project_dir / ATTEST_SUBDIR
    attest_dir.mkdir(parents=True, exist_ok=True)
    signature = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": TOOL,
        "signed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chain_root": chain.root,
        "algo": "sha256-chain",
        "chain_valid": verify.ok,
    }
    sig_path = attest_dir / SIGNATURE
    sig_path.write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")

    ship_path = project_dir / SHIP_MANIFEST
    ship_path.parent.mkdir(parents=True, exist_ok=True)
    ship_manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": TOOL,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chain_root": chain.root,
        "chain_valid": verify.ok,
        "release_eligible": effective_eligible,
        "core_evidence_present": evidence.core_evidence_present,
        "missing_evidence": list(evidence.missing),
        "policy": (
            "release_eligible requires a verified hash chain AND every core "
            "evidence file present AND evidence/manifest.json release_eligible=true."
        ),
    }
    ship_path.write_text(json.dumps(ship_manifest, indent=2) + "\n", encoding="utf-8")

    return AttestationResult(
        ok=(effective_eligible if release_eligible else verify.ok),
        release_eligible=effective_eligible,
        chain_root=chain.root,
        chain_path=str(attest_dir / HASH_CHAIN),
        signature_path=str(sig_path),
        ship_manifest_path=str(ship_path),
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Evidence hash-chain + release attestation.")
    ap.add_argument("project_dir", type=Path, help="Path to the EA project directory.")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("build", help="Build the evidence hash chain.")
    sub.add_parser("verify", help="Verify the stored hash chain.")
    att = sub.add_parser("attest", help="Create a release attestation + ship manifest.")
    att.add_argument("--release-eligible", action="store_true",
                     help="Assert release-eligibility (downgraded if chain invalid).")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.action == "build":
        chain = build_hash_chain(args.project_dir)
        env = Envelope(tool=TOOL, ok=True, exit_code=0,
                       summary=f"built hash chain root={chain.root[:12]}…",
                       data={"root": chain.root, "links": chain.links},
                       evidence=[str(args.project_dir)])
        if not args.emit_json:
            sys.stdout.write("hash-chain built\n")
        maybe_emit(args, env)
        return 0

    if args.action == "verify":
        res = verify_hash_chain(args.project_dir)
        env = Envelope(tool=TOOL, ok=res.ok, exit_code=0 if res.ok else 1,
                       summary="hash chain valid" if res.ok else f"hash chain INVALID: {len(res.errors)} error(s)",
                       data=res.to_dict(), evidence=[str(args.project_dir)],
                       matrix_dim="governance", matrix_axis="attestation",
                       matrix_status="PASS" if res.ok else "FAIL")
        if not args.emit_json:
            sys.stdout.write(("OK\n" if res.ok else "INVALID:\n" + "\n".join(res.errors) + "\n"))
        maybe_emit(args, env)
        return 0 if res.ok else 1

    # attest
    res = create_release_attestation(args.project_dir, release_eligible=args.release_eligible)
    env = Envelope(tool=TOOL, ok=res.ok, exit_code=0 if res.ok else 1,
                   summary=(f"attestation: release_eligible={res.release_eligible}"),
                   data=res.to_dict(), evidence=[str(args.project_dir)],
                   matrix_dim="governance", matrix_axis="attestation",
                   matrix_status="PASS" if res.ok else "FAIL")
    if not args.emit_json:
        sys.stdout.write(f"release_eligible={res.release_eligible}\n")
    maybe_emit(args, env)
    return 0 if res.ok else 1


def verify_main(argv: list[str] | None = None) -> int:
    """Entry for ``vkmql-check evidence <project>``.

    This is a *release evidence* gate, not a bare hash-chain verify. A valid
    chain over absent evidence is reported INCOMPLETE (exit 1), never "OK",
    so it can never contradict ``vkmql-check all`` (which marks the same state
    UNTESTABLE).
    """
    ap = argparse.ArgumentParser(prog="vkmql-check-evidence")
    ap.add_argument("project_dir", type=Path)
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    res = evaluate_release_evidence(args.project_dir)
    ok = res.status == "PASS"
    if not args.emit_json:
        if ok:
            sys.stdout.write("OK — release evidence complete and hash chain valid\n")
        else:
            lines = [f"{res.status}:"]
            lines.extend(f"- {e}" for e in res.errors)
            if res.missing:
                lines.append("- missing core evidence: " + ", ".join(res.missing))
            lines.extend(f"- {w}" for w in res.warnings)
            sys.stdout.write("\n".join(lines) + "\n")
    env = Envelope(
        tool="vkmql-check-evidence",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=(
            "release evidence complete" if ok
            else f"evidence {res.status}: {len(res.missing)} missing, {len(res.errors)} error(s)"
        ),
        data=res.to_dict(),
        evidence=[str(args.project_dir)],
        matrix_dim="governance",
        matrix_axis="attestation",
        matrix_status="PASS" if ok else ("FAIL" if res.status == "FAIL" else "WARN"),
    )
    maybe_emit(args, env)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
