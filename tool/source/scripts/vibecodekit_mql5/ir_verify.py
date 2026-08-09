"""Verify canonical EA-IR binding, generated artefacts and native evidence.

This gate prevents semantic drift between intake, generated source, compile
logs and Strategy Tester evidence.  Native evidence is accepted only when it
carries the exact canonical ``ir_sha256`` of the project being verified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ea_ir import EAIR, from_dict

TRUSTED_COMPILE_TYPES = {"actual_metaeditor", "remote_worker_metaeditor"}
TRUSTED_TESTER_TYPES = {"actual_mt5_strategy_tester", "remote_worker_strategy_tester"}


@dataclass
class IRVerifyResult:
    project: str
    ir_sha256: str | None = None
    ok: bool = False
    static_verified: bool = False
    compile_verified: bool = False
    tester_verified: bool = False
    release_eligible: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "ir_sha256": self.ir_sha256,
            "ok": self.ok,
            "status": {
                "static_verified": self.static_verified,
                "compile_verified": self.compile_verified,
                "tester_verified": self.tester_verified,
                "release_eligible": self.release_eligible,
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "checked_artifacts": self.checked_artifacts,
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_artifact_manifest(project: Path, ir: EAIR, paths: list[Path]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    root = project.resolve()
    for path in sorted({p.resolve() for p in paths}):
        try:
            rel = path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"artifact outside project: {path}") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        artifacts.append({
            "path": rel.as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {
        "schema_version": "1",
        "artifact_type": "ea_ir_generated_artifacts",
        "ir_sha256": ir.sha256(),
        "artifacts": artifacts,
        "release_eligible": False,
    }


def _load_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid {label} JSON: {exc}")
        return None
    if not isinstance(raw, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return raw


def _verify_native_evidence(
    path: Path | None,
    *,
    expected_hash: str,
    accepted_types: set[str],
    label: str,
    errors: list[str],
    warnings: list[str],
) -> bool:
    if path is None:
        warnings.append(f"{label} evidence not supplied")
        return False
    raw = _load_json(path, f"{label} evidence", errors)
    if raw is None:
        return False
    if raw.get("ir_sha256") != expected_hash:
        errors.append(
            f"{label} evidence IR hash mismatch: {raw.get('ir_sha256')!r} != {expected_hash!r}"
        )
        return False
    if raw.get("status") not in {"PASS", "passed", True}:
        errors.append(f"{label} evidence status is not PASS")
        return False
    evidence_type = raw.get("evidence_type")
    if evidence_type not in accepted_types:
        errors.append(
            f"{label} evidence_type {evidence_type!r} is not trusted; "
            f"accepted={sorted(accepted_types)}"
        )
        return False
    if not raw.get("artifacts") and not raw.get("hashes"):
        errors.append(f"{label} evidence carries no artifact hashes")
        return False
    return True


def verify_project(
    project: Path | str,
    *,
    compile_evidence: Path | None = None,
    tester_evidence: Path | None = None,
) -> IRVerifyResult:
    project = Path(project)
    res = IRVerifyResult(project=str(project))
    if not project.is_dir():
        res.errors.append(f"project not found: {project}")
        return res

    ir_raw = _load_json(project / "EA-IR.json", "EA-IR", res.errors)
    if ir_raw is None:
        return res
    try:
        ir = from_dict(ir_raw)
    except ValueError as exc:
        res.errors.append(f"EA-IR invalid: {exc}")
        return res
    expected = ir.sha256()
    res.ir_sha256 = expected

    plan = _load_json(project / "BUILD-PLAN.json", "BUILD-PLAN", res.errors)
    if plan is not None and plan.get("ir_sha256") != expected:
        res.errors.append("BUILD-PLAN ir_sha256 does not match EA-IR")

    name = str(ir.identity.get("name") or "")
    main = project / "Experts" / name / f"{name}.mq5"
    config = project / "Include" / name / "Config.mqh"
    for path, label in ((main, "main EA"), (config, "Config.mqh")):
        if not path.is_file():
            res.errors.append(f"missing {label}: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if expected not in text:
            res.errors.append(f"{label} is not bound to canonical IR hash")
        res.checked_artifacts.append(str(path.relative_to(project)))

    matrix = project / "requirements-matrix.csv"
    if not matrix.is_file():
        res.errors.append("missing requirements-matrix.csv")
    else:
        with matrix.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            res.errors.append("requirements-matrix.csv is empty")
        blocked_must = [r for r in rows if r.get("priority") == "must" and r.get("status") == "BLOCKED"]
        planned_only = [r for r in rows if r.get("status") == "PLANNED"]
        if blocked_must:
            res.errors.append(f"{len(blocked_must)} must requirement(s) remain BLOCKED")
        if planned_only:
            res.errors.append(f"{len(planned_only)} requirement(s) remain PLANNED after source generation")
        res.checked_artifacts.append("requirements-matrix.csv")

    manifest_path = project / "evidence" / "ir-artifacts.json"
    manifest = _load_json(manifest_path, "IR artifact manifest", res.errors)
    if manifest is not None:
        if manifest.get("ir_sha256") != expected:
            res.errors.append("IR artifact manifest hash does not match EA-IR")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            res.errors.append("IR artifact manifest has no artifacts")
        else:
            root = project.resolve()
            for item in artifacts:
                if not isinstance(item, dict) or not item.get("path"):
                    res.errors.append("malformed artifact manifest entry")
                    continue
                path = (root / str(item["path"])).resolve()
                try:
                    path.relative_to(root)
                except ValueError:
                    res.errors.append(f"artifact manifest path escapes project: {item['path']}")
                    continue
                if not path.is_file():
                    res.errors.append(f"manifest artifact missing: {item['path']}")
                    continue
                if path.stat().st_size != item.get("size") or sha256_file(path) != item.get("sha256"):
                    res.errors.append(f"manifest artifact changed: {item['path']}")
                res.checked_artifacts.append(str(item["path"]))

    res.static_verified = not res.errors
    res.compile_verified = _verify_native_evidence(
        compile_evidence,
        expected_hash=expected,
        accepted_types=TRUSTED_COMPILE_TYPES,
        label="compile",
        errors=res.errors,
        warnings=res.warnings,
    )
    res.tester_verified = _verify_native_evidence(
        tester_evidence,
        expected_hash=expected,
        accepted_types=TRUSTED_TESTER_TYPES,
        label="tester",
        errors=res.errors,
        warnings=res.warnings,
    )
    res.release_eligible = bool(
        res.static_verified and res.compile_verified and res.tester_verified and not res.errors
    )
    # Static-only verification is a successful command result but never a
    # release claim.  Native evidence errors do make the command fail when a
    # file was explicitly supplied.
    supplied_native = compile_evidence is not None or tester_evidence is not None
    res.ok = res.release_eligible if supplied_native else res.static_verified
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-ir-verify", description=__doc__.splitlines()[0])
    ap.add_argument("project", type=Path)
    ap.add_argument("--compile-evidence", type=Path)
    ap.add_argument("--tester-evidence", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    result = verify_project(
        args.project,
        compile_evidence=args.compile_evidence,
        tester_evidence=args.tester_evidence,
    )
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    out = args.out or (args.project / "IR-VERIFY-REPORT.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
