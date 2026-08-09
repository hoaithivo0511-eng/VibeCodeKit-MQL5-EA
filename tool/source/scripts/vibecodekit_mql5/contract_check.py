"""vkmql-check contract — project contract checker (v3 governance).

Verifies that an EA project carries the full set of governance contracts and
that none of them have been weakened. This is the gate that turns "the AI
said it's done" into "the kit can prove the contracts are intact".

CLI::

    vkmql-check contract ./MyEA
    python -m vibecodekit_mql5.contract_check ./MyEA --json

Programmatic::

    check_project_contract(project_dir) -> ContractCheckResult

Fail conditions (hard):
  * EA-SPEC.yaml missing or invalid,
  * risk section has no max_drawdown_pct,
  * AI-BUILD-CONTRACT allows editing ``evidence/``,
  * README claims live/production-ready without an evidence manifest.
Warn conditions:
  * RISK/BROKER/EVIDENCE-CONTRACT.yaml or AGENTS.md missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from . import ai_build_contract as abc
from . import spec_schema_v26 as sv

TOOL = "vkmql-check-contract"

# Required governance artefacts. (name, hard) — hard=True fails the gate.
REQUIRED_FILES: tuple[tuple[str, bool], ...] = (
    ("EA-SPEC.yaml", True),
    ("AI-BUILD-CONTRACT.md", True),
    ("AI-BUILD-CONTRACT.json", True),
    ("RISK-CONTRACT.yaml", False),
    ("BROKER-CONTRACT.yaml", False),
    ("EVIDENCE-CONTRACT.yaml", False),
    ("RELEASE-TRUST.yaml", False),
    ("AGENTS.md", False),
)


@dataclass
class ContractCheckResult:
    ok: bool
    project_dir: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_dir": self.project_dir,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checked": list(self.checked),
        }


def _spec_path(project_dir: Path) -> Path:
    for cand in ("EA-SPEC.yaml", "EA-SPEC.yml", "ea-spec.yaml"):
        p = project_dir / cand
        if p.is_file():
            return p
    return project_dir / "EA-SPEC.yaml"


def _readme_ready_claim_error(project_dir: Path) -> str | None:
    """Validate any live/production-ready claim in the README against evidence.

    A README that claims READY/LIVE/PRODUCTION must be backed by a *valid,
    release-eligible* evidence manifest — not merely the existence of a file.
    Returns an error string when the claim is unbacked, else ``None``.
    """
    readme = project_dir / "README.md"
    if not readme.is_file():
        return None
    text = readme.read_text(encoding="utf-8", errors="replace").upper()
    claims_ready = any(claim in text for claim in sv.FORBIDDEN_READY_CLAIMS)
    if not claims_ready:
        return None

    manifest_path = project_dir / "evidence" / "manifest.json"
    if not manifest_path.is_file():
        return "README claims live/production-ready but there is no evidence/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return f"README claims ready but evidence/manifest.json is invalid JSON: {exc}"
    if not isinstance(manifest, dict) or manifest.get("release_eligible") is not True:
        return (
            "README claims live/production-ready but evidence/manifest.json "
            "release_eligible is not true"
        )
    # A bare eligibility flag is not enough: the manifest must carry real
    # artifact hashes proving compile/backtest evidence exists.
    has_hashes = bool(
        manifest.get("chain_root")
        or manifest.get("artifacts")
        or manifest.get("hashes")
        or manifest.get("evidence")
    )
    if not has_hashes:
        return (
            "README claims ready and manifest says eligible, but the manifest "
            "carries no artifact hashes (expected chain_root/artifacts/hashes)"
        )
    return None


def check_project_contract(project_dir: Path | str) -> ContractCheckResult:
    """Run all contract checks over a project directory."""
    project_dir = Path(project_dir)
    res = ContractCheckResult(ok=True, project_dir=str(project_dir))

    if not project_dir.is_dir():
        res.ok = False
        res.errors.append(f"project dir not found: {project_dir}")
        return res

    # 1) presence of governance artefacts
    for name, hard in REQUIRED_FILES:
        present = (project_dir / name).is_file()
        res.checked.append(name)
        if not present:
            msg = f"missing {name}"
            (res.errors if hard else res.warnings).append(msg)

    # 2) EA-SPEC validity + max drawdown (route through the single schema)
    spec_res = sv.load_spec_v26(_spec_path(project_dir))
    if not spec_res.ok:
        res.errors.extend(f"EA-SPEC: {e}" for e in spec_res.errors)
    res.warnings.extend(f"EA-SPEC: {w}" for w in spec_res.warnings)

    # 3) AI-BUILD-CONTRACT integrity (must forbid editing evidence/)
    if (project_dir / abc.CONTRACT_JSON).is_file():
        cval = abc.validate_ai_build_contract(project_dir)
        res.errors.extend(f"AI-BUILD-CONTRACT: {e}" for e in cval.errors)
        res.warnings.extend(f"AI-BUILD-CONTRACT: {w}" for w in cval.warnings)

    # 4) README must not claim live/production-ready without backed evidence
    ready_err = _readme_ready_claim_error(project_dir)
    if ready_err:
        res.errors.append(ready_err)

    res.ok = not res.errors
    return res


def render_report(res: ContractCheckResult) -> str:
    verdict = "CONTRACT-PASSED" if res.ok else "CONTRACT-FAILED"
    lines = [
        "# CONTRACT CHECK",
        "",
        f"- Project: `{res.project_dir}`",
        f"- Verdict: **{verdict}**",
        f"- Checked: {len(res.checked)} artefact(s)",
        "",
        "## Errors",
    ]
    lines += [f"- {e}" for e in res.errors] or ["- none"]
    lines += ["", "## Warnings"]
    lines += [f"- {w}" for w in res.warnings] or ["- none"]
    lines += [
        "",
        "> CONTRACT-PASSED only means the governance contracts are intact;",
        "> it is NOT a release claim. Run the full `vkmql-check all` gate.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Check an EA project's governance contracts.")
    ap.add_argument("project_dir", type=Path, help="Path to the EA project directory.")
    ap.add_argument("--out", type=Path, default=None, help="Write the report markdown here.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    res = check_project_contract(args.project_dir)
    md = render_report(res)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
    if not args.emit_json:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")

    env = Envelope(
        tool=TOOL,
        ok=res.ok,
        exit_code=0 if res.ok else 1,
        summary=(
            f"contract check {'passed' if res.ok else 'FAILED'}: "
            f"{len(res.errors)} error(s), {len(res.warnings)} warning(s)"
        ),
        data=res.to_dict(),
        evidence=[str(args.project_dir)],
        matrix_dim="governance",
        matrix_axis="contract",
        matrix_status="PASS" if res.ok else "FAIL",
    )
    maybe_emit(args, env)
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
