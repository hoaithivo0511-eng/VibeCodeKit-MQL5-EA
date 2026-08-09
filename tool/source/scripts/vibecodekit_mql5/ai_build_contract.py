"""AI-BUILD-CONTRACT generator + validator (v3; v2.6-compatible).

When an EA is built by an AI coding tool (Claude Code / Codex / Cursor),
the single biggest failure mode is the tool quietly editing things it must
not touch — evidence files, release manifests — or claiming the build is
"ready" without any proof. The **AI-BUILD-CONTRACT** is the guard-rail: a
human-readable + machine-readable contract, generated from ``EA-SPEC.yaml``,
that states exactly which paths the AI may edit, which it may never touch,
which claims are forbidden, and what evidence a release requires.

Public API (used by ``vkmql-new contract`` and ``contract_check``):

    generate_ai_build_contract(project_dir) -> ContractResult
    validate_ai_build_contract(project_dir) -> ValidationResult

Outputs (written into ``project_dir``):

    AI-BUILD-CONTRACT.md     human-readable contract
    AI-BUILD-CONTRACT.json   machine-readable contract

The generator reuses :mod:`spec_schema_v26` for spec validation (anti-bloat
rule #4: never re-implement spec parsing).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import decision_ledger as dl
from . import retro_guards as rg
from .ui_contract import default_ui_contract
from . import spec_schema_v26 as sv
from . import workflow_mode as wm

CONTRACT_MD = "AI-BUILD-CONTRACT.md"
CONTRACT_JSON = "AI-BUILD-CONTRACT.json"
CONTRACT_SCHEMA_VERSION = "3.0"

# Paths an AI coding tool may edit while implementing the EA.
DEFAULT_ALLOWED_PATHS: tuple[str, ...] = (
    "Experts/",
    "Include/",
    "Presets/",
    "Tester/",
    "README.md",
)
# Paths that must NEVER be edited by the AI — these hold proof + governance.
DEFAULT_FORBIDDEN_PATHS: tuple[str, ...] = (
    "evidence/",
    "release/",
    "review/",
    "AI-BUILD-CONTRACT.md",
    "AI-BUILD-CONTRACT.json",
    "EA-SPEC.yaml",
    "DECISIONS.yaml",
    "OWNER_APPROVAL.json",
)
# Claims the AI may never write into docs/status without full evidence.
DEFAULT_FORBIDDEN_CLAIMS: tuple[str, ...] = sv.FORBIDDEN_READY_CLAIMS


@dataclass
class ContractResult:
    ok: bool
    contract: dict[str, Any] = field(default_factory=dict)
    md_path: str | None = None
    json_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "contract": self.contract,
            "md_path": self.md_path,
            "json_path": self.json_path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def build_contract_dict(spec: dict[str, Any]) -> dict[str, Any]:
    """Assemble the machine-readable v3 contract from a validated EA spec."""
    project = spec.get("project", {})
    risk = spec.get("risk", {})
    strategy = spec.get("strategy", {})
    governance = spec.get("governance", {})
    mode_result = wm.resolve_mode(spec)
    effective_mode = mode_result.effective
    release_target = governance.get("release_target", "draft") if isinstance(governance, dict) else "draft"
    required_evidence = ["compile log + EX5 hash", "evidence manifest", "evidence hash chain"]
    if wm.backtest_required(spec):
        required_evidence.append("backtest report")
    if effective_mode == "full":
        required_evidence.extend(["stress matrix report", "deep review report"])
    if release_target in {"forward", "live"}:
        required_evidence.append("owner approval bound to build and evidence hashes")
    ui = spec.get("ui_contract") if isinstance(spec.get("ui_contract"), dict) else default_ui_contract()["ui_contract"]
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "generated_by": "ai_build_contract",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": {
            "name": project.get("name", "MyEA"),
            "version": project.get("version", "0.1.0"),
            "status": project.get("status", "DRAFT-NOT-VALIDATED"),
        },
        "workflow": {
            "requested_mode": mode_result.requested,
            "effective_mode": effective_mode,
            "promotion_reasons": mode_result.reasons,
            "release_target": release_target,
        },
        "allowed_paths": list(DEFAULT_ALLOWED_PATHS),
        "forbidden_paths": list(DEFAULT_FORBIDDEN_PATHS),
        "forbidden_claims": list(DEFAULT_FORBIDDEN_CLAIMS),
        "risk_contract": {
            "max_drawdown_pct": risk.get("max_drawdown_pct"),
            "max_daily_loss_pct": risk.get("max_daily_loss_pct"),
            "max_positions": risk.get("max_positions"),
            "stop_loss_required": risk.get("stop_loss_required", True),
            "forbidden_logic": list(strategy.get("forbidden_logic", []) or []),
        },
        "decision_policy": {
            "ledger": dl.LEDGER_NAME,
            "semantic_changes_require_owner_approval": True,
            "auto_edit_allowed": [
                "formatting",
                "timestamps",
                "generated identifiers",
                "hashes",
                "paths",
                "fields explicitly marked derived",
            ],
        },
        "guard_catalog_version": rg.CATALOG_VERSION,
        "behavioral_guards": rg.select_guards(spec),
        "ui_contract": ui,
        "release_policy": {
            "windows_native_is_release_authority": True,
            "wine_role": "development-ci-only",
            "onnx_mode": "optional-plugin",
            "mcp_stability": "internal-experimental",
            "telemetry": "off",
            "evidence_store": "local",
            "owner_approval_required_for_live": True,
        },
        "release_evidence_required": required_evidence,
        "rules": [
            "The AI coding tool MUST NOT edit any forbidden_paths.",
            "The AI coding tool MUST NOT write forbidden_claims without evidence.",
            "No status above DRAFT-NOT-VALIDATED without the required evidence.",
            "Every change must stay within allowed_paths.",
            "Unbounded martingale / unbounded lot scaling is forbidden.",
            "The AI MUST propose semantic changes and wait for owner approval.",
            "FAIL, UNTESTABLE, SKIPPED and WAIVED MUST remain distinct.",
        ],
    }


def render_contract_md(contract: dict[str, Any]) -> str:
    p = contract["project"]
    rc = contract["risk_contract"]
    lines = [
        f"# AI-BUILD-CONTRACT — {p['name']}",
        "",
        f"- Project: **{p['name']}** v{p['version']}",
        f"- Status: `{p['status']}`",
        f"- Generated: {contract['generated_at_utc']}",
        f"- Schema: {contract['schema_version']}",
        f"- Workflow mode: `{contract['workflow']['effective_mode']}`",
        f"- Release target: `{contract['workflow']['release_target']}`",
        "",
        "> This contract governs what an AI coding tool (Claude Code / Codex /",
        "> Cursor) is allowed to do in this project. Violating it invalidates",
        "> the build. **No evidence = no ready.**",
        "",
        "## Allowed paths (AI may edit)",
    ]
    lines += [f"- `{x}`" for x in contract["allowed_paths"]]
    lines += ["", "## Forbidden paths (AI must NEVER edit)"]
    lines += [f"- `{x}`" for x in contract["forbidden_paths"]]
    lines += ["", "## Forbidden claims (never without evidence)"]
    lines += [f"- `{x}`" for x in contract["forbidden_claims"]]
    lines += [
        "",
        "## Risk contract",
        f"- Max drawdown: `{rc.get('max_drawdown_pct')}%`",
        f"- Max daily loss: `{rc.get('max_daily_loss_pct')}%`",
        f"- Max positions: `{rc.get('max_positions')}`",
        f"- Stop-loss required: `{rc.get('stop_loss_required')}`",
        f"- Forbidden logic: {', '.join('`'+x+'`' for x in rc.get('forbidden_logic', [])) or '_none_'}",
        "",
        "## Release evidence required",
    ]
    lines += [f"- {x}" for x in contract["release_evidence_required"]]
    lines += ["", "## Behavioral guards"]
    for guard in contract.get("behavioral_guards", []):
        lines.append(
            f"- `{guard['id']}` [{guard['severity']}/{guard['class']}]: "
            f"{guard['name']} — checker `{guard['checker']}`"
        )
    lines += [
        "",
        "## Semantic decision policy",
        f"- Ledger: `{contract['decision_policy']['ledger']}`",
        "- Semantic changes require owner approval: `true`",
        "- Evidence hashes do not replace human approval.",
    ]
    lines += ["", "## Rules"]
    lines += [f"{i}. {r}" for i, r in enumerate(contract["rules"], 1)]
    lines += [""]
    return "\n".join(lines)


def _find_spec(project_dir: Path) -> Path:
    for cand in ("EA-SPEC.yaml", "EA-SPEC.yml", "ea-spec.yaml"):
        p = project_dir / cand
        if p.is_file():
            return p
    return project_dir / "EA-SPEC.yaml"


def generate_ai_build_contract(project_dir: Path | str, *, write: bool = True) -> ContractResult:
    """Generate AI-BUILD-CONTRACT.{md,json} from the project's EA-SPEC.yaml."""
    project_dir = Path(project_dir)
    spec_path = _find_spec(project_dir)
    spec_res = sv.load_spec_v26(spec_path)
    if not spec_res.ok:
        return ContractResult(ok=False, errors=spec_res.errors, warnings=spec_res.warnings)

    contract = build_contract_dict(spec_res.spec)
    res = ContractResult(ok=True, contract=contract, warnings=spec_res.warnings)
    if write:
        md_path = project_dir / CONTRACT_MD
        json_path = project_dir / CONTRACT_JSON
        project_dir.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_contract_md(contract), encoding="utf-8")
        json_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        res.md_path = str(md_path)
        res.json_path = str(json_path)
    return res


def validate_ai_build_contract(project_dir: Path | str) -> ValidationResult:
    """Validate an existing AI-BUILD-CONTRACT.json in ``project_dir``.

    Fails when:
      - the contract file is missing or invalid JSON,
      - there is no risk section / no max drawdown bound,
      - the contract allows editing ``evidence/`` (or any forbidden dir).
    """
    project_dir = Path(project_dir)
    path = project_dir / CONTRACT_JSON
    if not path.is_file():
        return ValidationResult(ok=False, errors=[f"missing {CONTRACT_JSON}"])
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(ok=False, errors=[f"invalid contract JSON: {exc}"])

    errors: list[str] = []
    warnings: list[str] = []

    rc = contract.get("risk_contract")
    if not isinstance(rc, dict):
        errors.append("contract is missing the risk section (risk_contract)")
    elif rc.get("max_drawdown_pct") in (None, ""):
        errors.append("contract risk section has no max_drawdown_pct")

    allowed = contract.get("allowed_paths", [])
    forbidden = contract.get("forbidden_paths", [])
    if not isinstance(allowed, list) or not allowed:
        errors.append("contract has no allowed_paths")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("contract has no forbidden_paths")
    else:
        # Hard rule: evidence/ and release/ must be forbidden, never allowed.
        for guarded in ("evidence/", "release/"):
            if any(str(a).strip().startswith(guarded) for a in allowed):
                errors.append(f"contract allows editing {guarded} (must be forbidden)")
            if not any(str(f).strip().startswith(guarded) for f in forbidden):
                errors.append(f"contract does not forbid editing {guarded}")

    if not contract.get("forbidden_claims"):
        warnings.append("contract has no forbidden_claims list")
    if not contract.get("release_evidence_required"):
        warnings.append("contract has no release_evidence_required list")

    schema_version = str(contract.get("schema_version", ""))
    if schema_version == CONTRACT_SCHEMA_VERSION:
        workflow = contract.get("workflow")
        if not isinstance(workflow, dict) or workflow.get("effective_mode") not in wm.MODES:
            errors.append("v3 contract has no valid workflow.effective_mode")
        decision_policy = contract.get("decision_policy")
        if not isinstance(decision_policy, dict) or (
            decision_policy.get("semantic_changes_require_owner_approval") is not True
        ):
            errors.append("v3 contract does not protect owner-approved semantics")
        errors.extend(rg.validate_guard_list(contract.get("behavioral_guards")))
        release_policy = contract.get("release_policy")
        if not isinstance(release_policy, dict) or (
            release_policy.get("owner_approval_required_for_live") is not True
        ):
            errors.append("v3 contract does not require owner approval for live")
    else:
        warnings.append(
            f"legacy contract schema {schema_version or 'missing'}; expected {CONTRACT_SCHEMA_VERSION}"
        )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


__all__ = [
    "ContractResult",
    "ValidationResult",
    "generate_ai_build_contract",
    "validate_ai_build_contract",
    "build_contract_dict",
    "render_contract_md",
]


def main(argv: list[str] | None = None) -> int:
    """CLI: generate (default) or --validate the AI-BUILD-CONTRACT."""
    import argparse
    import sys

    from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

    ap = argparse.ArgumentParser(
        prog="mql5-ai-build-contract",
        description="Generate or validate AI-BUILD-CONTRACT.{md,json} from EA-SPEC.yaml.",
    )
    ap.add_argument("project_dir", type=Path, help="EA project directory.")
    ap.add_argument("--validate", action="store_true",
                    help="Validate an existing contract instead of generating one.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.validate:
        res = validate_ai_build_contract(args.project_dir)
        env = Envelope(
            tool="mql5-ai-build-contract", ok=res.ok, exit_code=0 if res.ok else 1,
            summary=("contract valid" if res.ok else f"contract INVALID: {len(res.errors)} error(s)"),
            data={"errors": res.errors, "warnings": res.warnings},
            evidence=[str(args.project_dir)],
            matrix_dim="governance", matrix_axis="contract",
            matrix_status="PASS" if res.ok else "FAIL",
        )
        if not args.emit_json:
            sys.stdout.write(("OK\n" if res.ok else "INVALID:\n" + "\n".join(res.errors) + "\n"))
        maybe_emit(args, env)
        return 0 if res.ok else 1

    res = generate_ai_build_contract(args.project_dir)
    env = Envelope(
        tool="mql5-ai-build-contract", ok=True, exit_code=0,
        summary="wrote AI-BUILD-CONTRACT.{md,json}",
        data={"md_path": res.md_path, "json_path": res.json_path},
        evidence=[p for p in (res.md_path, res.json_path) if p],
    )
    if not args.emit_json:
        sys.stdout.write(f"wrote {res.md_path}\nwrote {res.json_path}\n")
    maybe_emit(args, env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
