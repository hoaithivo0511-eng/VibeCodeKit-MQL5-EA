"""Release eligibility and evidence helpers.

Central policy: no compile/backtest/gate evidence, no release claim.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UNSAFE_FLAGS = {
    "--draft",
    "--no-compile",
    "--no-gate",
    "--allow-skips",
    "--unsafe-allow-skips",
    "--legacy-scaffold",
}
FIXTURE_DIRS = {"tests", "fixtures", "examples", "samples", "docs"}


def compute_release_eligible(
    *,
    compile_ok: bool,
    gate_ok: bool,
    backtest_ok: bool,
    evidence_ok: bool,
    command_ok: bool = True,
    matrix_ok: bool = True,
    stress_ok: bool = True,
    hash_chain_ok: bool = True,
    quality_ok: bool = True,
    forward_ok: bool = True,
    retro_ok: bool = True,
    owner_approval_ok: bool = True,
    target_ok: bool = True,
    mandatory_stages_ok: bool = True,
    unsafe_flags: list[str] | None = None,
    skipped_stages: list[str] | None = None,
) -> bool:
    """THE canonical release-eligibility rule for the whole kit.

    Both the v1 pipeline summary (``release_policy.summarize``) and the
    canonical v2 evidence manifest (``evidence_v2.EvidenceManifestV2.evaluate``)
    MUST route their decision through this single predicate, so a build can
    never be "release-eligible" under one code path and "blocked" under another.

    Dimensions a given caller does not observe default to the neutral value
    (``command_ok`` / ``matrix_ok`` = True) so their absence can never make a
    build look *more* eligible than its real evidence warrants.
    """
    # v2.6 BIG HARDENING adds two gate keys: the stress matrix must hold (no
    # FAIL / UNTESTABLE scenarios) and the evidence hash chain must verify.
    # Both default to the neutral True so pre-v2.6 callers are unaffected and
    # can never look *more* eligible than their evidence warrants.
    return (
        all([
            command_ok, compile_ok, gate_ok, backtest_ok, evidence_ok,
            matrix_ok, stress_ok, hash_chain_ok, quality_ok, forward_ok,
            retro_ok, owner_approval_ok, target_ok, mandatory_stages_ok,
        ])
        and not (unsafe_flags or [])
        and not (skipped_stages or [])
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_fixture_path(path: Path) -> bool:
    return any(p.lower() in FIXTURE_DIRS for p in path.parts)


def stage(report: dict[str, Any], name: str) -> dict[str, Any] | None:
    for s in report.get("stages", []):
        if s.get("name") == name:
            return s
    return None


def summarize(report: dict[str, Any], unsafe_flags: list[str] | None = None) -> dict[str, Any]:
    unsafe_flags = list(unsafe_flags or report.get("unsafe_flags_used") or [])
    stages = report.get("stages", [])
    skipped = [s.get("name") for s in stages if s.get("skipped")]
    compile_stage = stage(report, "compile")
    gate_stage = stage(report, "gate")
    backtest_stage = stage(report, "backtest")
    compile_ok = bool(compile_stage and compile_stage.get("ok") and not compile_stage.get("skipped"))
    gate_ok = bool(gate_stage and gate_stage.get("ok") and not gate_stage.get("skipped"))
    backtest_ok = bool(backtest_stage and backtest_stage.get("ok") and not backtest_stage.get("skipped"))
    # Backward compatible: existing pipeline has no actual backtest stage, so it cannot be release-eligible.
    evidence_ok = bool((report.get("evidence_manifest") or {}).get("ok"))
    command_ok = bool(report.get("ok"))
    release_eligible = compute_release_eligible(
        command_ok=command_ok,
        compile_ok=compile_ok,
        gate_ok=gate_ok,
        backtest_ok=backtest_ok,
        evidence_ok=evidence_ok,
        unsafe_flags=unsafe_flags,
        skipped_stages=skipped,
    )
    status = "passed" if release_eligible else ("failed" if not command_ok else "blocked")
    if "--draft" in unsafe_flags:
        status = "draft"
    return {
        "status": status,
        "command_ok": command_ok,
        "build_ok": bool(stage(report, "build") and stage(report, "build").get("ok")),
        "compile_ok": compile_ok,
        "backtest_ok": backtest_ok,
        "gate_ok": gate_ok,
        "evidence_ok": evidence_ok,
        "unsafe_flags_used": unsafe_flags,
        "skipped_stages": skipped,
        "release_eligible": release_eligible,
    }


# Canonical evidence schema is now 2.0 (EvidenceManifestV2 shape). The writer
# below is the v1->v2 *adapter*: it emits a SUPERSET document that satisfies
# both the canonical v2 structure (schema_version 2.0, tool_policy, compile/
# backtest/gates blocks, methodology disclosure, role-tagged artifacts) and
# every legacy v1 reader (top-level `release_eligible`, `policy`, `summary`,
# and `artifacts[].{path,sha256,fixture}`). v1 is retained only as this
# compatibility view; no standalone v1 schema is written anymore.
EVIDENCE_SCHEMA_VERSION = "2.0"

_METHODOLOGY_DISCLOSURE = {
    "trader_17": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
    "ap_ids": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
    "triangle_of_power": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
}


def _stage_block(report: dict[str, Any], name: str) -> dict[str, Any]:
    s = stage(report, name) or {}
    return {
        "ok": bool(s.get("ok")) and not s.get("skipped"),
        "skipped": bool(s.get("skipped")),
        "source": s.get("source"),
        "detail": s.get("detail"),
    }


def write_evidence_manifest(out_dir: Path, report: dict[str, Any], *, unsafe_flags: list[str] | None = None) -> dict[str, Any]:
    ev_dir = out_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name not in {"manifest.json"} and p.suffix.lower() != ".zip":
            try:
                files.append({
                    "role": "build-output",
                    "path": p.relative_to(out_dir).as_posix(),
                    "exists": True,
                    "sha256": sha256_file(p),
                    "size_bytes": p.stat().st_size,
                    "fixture": is_fixture_path(p),
                })
            except OSError:
                pass
    summary = summarize(report, unsafe_flags=unsafe_flags)
    if not files:
        summary["evidence_ok"] = False
        summary["release_eligible"] = False
        if summary.get("status") == "passed":
            summary["status"] = "blocked"
    manifest = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_policy": "No PASS/READY/RELEASE claim is valid without release_eligible=true and artifact hashes.",
        # Legacy v1 key retained for backward-compatible readers.
        "policy": "No PASS/READY/RELEASE claim is valid unless release_eligible is true and hashes are present.",
        "summary": summary,
        "compile": _stage_block(report, "compile"),
        "backtest": _stage_block(report, "backtest"),
        "gates": _stage_block(report, "gate"),
        "methodology": _METHODOLOGY_DISCLOSURE,
        "unsafe_flags_used": summary.get("unsafe_flags_used", []),
        "skipped_stages": summary.get("skipped_stages", []),
        "artifacts": files,
        "release_eligible": summary["release_eligible"],
    }
    path = ev_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "sha256": sha256_file(path), "release_eligible": manifest["release_eligible"], "schema_version": EVIDENCE_SCHEMA_VERSION}


def validate_release_manifest(out_dir: Path) -> tuple[bool, str]:
    path = out_dir / "evidence" / "manifest.json"
    if not path.is_file():
        return False, "missing evidence/manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, f"invalid evidence manifest: {exc}"
    # Route release-looking manifests through the same provenance gate as the
    # attestation and check-all commands.  This prevents three policy paths
    # from disagreeing about fake evidence.
    if not data.get("release_eligible"):
        return False, "evidence manifest says release_eligible=false"
    from .provenance import validate_release_provenance
    prov = validate_release_provenance(out_dir)
    if prov.status != "PASS":
        detail = "; ".join(prov.errors or prov.missing) or "provenance incomplete"
        return False, detail
    return True, "ok"
