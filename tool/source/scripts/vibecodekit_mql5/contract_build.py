"""Contract build orchestrator.

Runs the owner->contractor->builder workflow and writes a unified contract report.
It does not fake compile/backtest. Without real evidence, release_eligible remains false.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import json

from .contract_utils import read_json, write_json, now_iso
from .owner_interview import validate_interview
from .contract_blueprint import validate_blueprint
from .blueprint_tip import review_blueprint
from .owner_approve import validate_approval
from .project_gen import main as project_gen_main
from .ea_compose import main as compose_main
from .architecture_check import check_architecture
from .ap_policy import read_mql_text, evaluate_ap5, evaluate_ap19_ml, evaluate_architecture_ap_rules
from . import docs_bundle as docs_bundle_mod


def ap_policy_report(ea: Path, project: Path, profile: str) -> dict[str, Any]:
    text = read_mql_text(ea, project)
    checks = [evaluate_ap5(text, profile), evaluate_ap19_ml(text, None, profile)] + evaluate_architecture_ap_rules(text, profile)
    ok = not any(c.get("release_blocking") for c in checks)
    return {"ok": ok, "release_blocking": not ok, "checks": checks}


def contract_build(
    *,
    interview_path: Path,
    blueprint_path: Path,
    tip_path: Path,
    approval_path: Path,
    out_dir: Path,
    name: str | None = None,
    draft: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    interview = read_json(interview_path)
    blueprint = read_json(blueprint_path)
    tip = read_json(tip_path)
    approval = read_json(approval_path)

    interview_check = validate_interview(interview)
    blueprint_check = validate_blueprint(blueprint)
    tip_check = review_blueprint(blueprint)
    approval_check = validate_approval(approval)

    profile = blueprint.get("architecture_profile", "grid-safe")
    project_name = name or "ContractEA"
    project_root = out_dir / project_name

    build_steps: list[dict[str, Any]] = []
    can_build_draft = interview_check["ok"] and blueprint_check["ok"] and tip_check["ok"] and approval_check["ok"]
    if can_build_draft:
        rc = project_gen_main(["--name", project_name, "--profile", profile, "--out", str(out_dir)])
        build_steps.append({"step": "project_gen", "returncode": rc})
        compose_rc = compose_main(["--project", str(project_root), "--profile", profile, "--out", str(project_root / "evidence" / "compose.json")])
        build_steps.append({"step": "ea_compose", "returncode": compose_rc})
        ea = project_root / "Experts" / f"{project_name}.mq5"
        arch = check_architecture(project_root, profile)
        ap = ap_policy_report(ea, project_root, "grid" if profile == "grid-safe" else profile)
        # LLM structure-driven docgen (v2.6+): emit docs-context.json +
        # docs-prompt.md from the REAL parsed .mq5 inputs. The legacy
        # hardcoded template generator has been removed.
        doc_bundle = docs_bundle_mod.write_bundle(
            project_root / "ea-spec.yaml", ea, project_root / "docs"
        )
        build_steps.append({"step": "docs_bundle", "returncode": 0 if doc_bundle.ok else 2, "inputs_total": doc_bundle.inputs_total})
    else:
        arch = {"ok": False, "release_blocking": True, "reason": "contract artifacts invalid"}
        ap = {"ok": False, "release_blocking": True, "reason": "contract artifacts invalid"}

    # Compile/backtest remain false unless separate trusted evidence exists.
    compile_ok = False
    backtest_ok = False
    evidence_manifest_release_eligible = False

    acceptance_status = {
        "owner_interview_valid": interview_check["ok"],
        "contract_blueprint_valid": blueprint_check["ok"],
        "blueprint_tip_no_critical": tip_check["ok"],
        "owner_approval_valid": approval_check["ok"],
        "architecture_check_ok": bool(arch.get("ok")),
        "ap_policy_ok": bool(ap.get("ok")),
        "ea_docs_generated": bool((project_root / "docs" / "docs-context.json").is_file()) if can_build_draft else False,
        "ea_docs_verified": bool((project_root / "docs" / "docs-prompt.md").is_file()) if can_build_draft else False,
        "compile_ok": compile_ok,
        "backtest_ok": backtest_ok,
        "evidence_manifest_release_eligible": evidence_manifest_release_eligible,
    }
    if "multi_broker_ok" in blueprint.get("acceptance_criteria", []):
        acceptance_status["multi_broker_ok"] = False
    if "walk_forward_ok" in blueprint.get("acceptance_criteria", []):
        acceptance_status["walk_forward_ok"] = False

    required = blueprint.get("acceptance_criteria", [])
    missing_acceptance = [k for k in required if not acceptance_status.get(k, False)]
    release_eligible = not missing_acceptance and not draft

    report = {
        "schema_version": "1.0",
        "artifact_type": "contract_build_report",
        "created_at": now_iso(),
        "project": str(project_root),
        "profile": profile,
        "draft": draft,
        "release_eligible": release_eligible,
        "missing_acceptance": missing_acceptance,
        "contract_checks": {
            "owner_interview": interview_check,
            "contract_blueprint": blueprint_check,
            "blueprint_tip": tip_check,
            "owner_approval": approval_check,
        },
        "build_steps": build_steps,
        "architecture_check": arch,
        "ap_policy": ap,
        "acceptance_status": acceptance_status,
        "policy": "No release without interview, blueprint, tip, approval, architecture/AP, compile/backtest/evidence acceptance.",
    }
    write_json(out_dir / "contract-build-report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run contract build workflow.")
    ap.add_argument("--interview", required=True)
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--tip", required=True)
    ap.add_argument("--approval", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", default="ContractEA")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args(argv)

    report = contract_build(
        interview_path=Path(args.interview),
        blueprint_path=Path(args.blueprint),
        tip_path=Path(args.tip),
        approval_path=Path(args.approval),
        out_dir=Path(args.out_dir),
        name=args.name,
        draft=args.draft,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["release_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
