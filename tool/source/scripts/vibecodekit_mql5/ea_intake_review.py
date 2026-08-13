"""One-shot existing EA intake + review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ea_intake import intake_source
from . import docs_bundle as docs_bundle_mod
from .architecture_check import check_architecture
from .ap_policy import read_mql_text, evaluate_ap5, evaluate_ap19_ml, evaluate_architecture_ap_rules
from .ea_senior_review import review_project
from .ea_review_report import write_review_docx


def ap_report(ea: Path, project: Path, profile: str) -> dict[str, Any]:
    text = read_mql_text(ea, project)
    checks = [evaluate_ap5(text, profile), evaluate_ap19_ml(text, None, profile)] + evaluate_architecture_ap_rules(text, profile)
    ok = not any(c.get("release_blocking") for c in checks)
    return {"ok": ok, "release_blocking": not ok, "checks": checks}


def run_intake_review(source: str | Path, out_dir: str | Path, name: str | None = None, profile: str = "auto") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    intake = intake_source(source, out, name)
    project = Path(intake["project"])
    ea = Path(intake["main_ea"])
    review_dir = project / "review"
    review_dir.mkdir(exist_ok=True)

    # LLM structure-driven docgen (v2.6+): emit docs-context.json +
    # docs-prompt.md from the REAL parsed .mq5 inputs of the intake EA.
    # The legacy hardcoded template generator has been removed.
    docs_dir = project / "docs"
    spec_path = project / "ea-spec.yaml"
    if not spec_path.is_file():
        spec_path.write_text(
            json.dumps({"name": name or project.name}, indent=2),
            encoding="utf-8",
        )
    doc_bundle = docs_bundle_mod.write_bundle(spec_path, ea, docs_dir)
    docgen_rc = 0 if doc_bundle.ok else 2

    verify_profile = profile
    if verify_profile == "auto":
        verify_profile = "grid-hedge" if "hedge" in project.name.lower() or "grid" in ea.read_text(encoding="utf-8", errors="ignore").lower() else "generic"

    arch = None
    if verify_profile in {"grid-safe", "grid-hedge", "grid"}:
        try:
            arch = check_architecture(project, "grid-safe")
        except Exception as e:
            arch = {"ok": False, "error": repr(e)}
    else:
        arch = {"ok": None, "reason": "architecture profile not enforced for generic review"}

    ap = ap_report(ea, project, "grid" if verify_profile in {"grid-hedge", "grid-safe", "grid"} else "default")
    senior = review_project(project, verify_profile)
    senior_json = review_dir / "EA-SENIOR-REVIEW.json"
    senior_docx = review_dir / "EA-SENIOR-REVIEW.docx"
    senior_json.write_text(json.dumps(senior, indent=2, ensure_ascii=False), encoding="utf-8")
    write_review_docx(senior, senior_docx)

    arch_path = review_dir / "architecture-check.json"
    arch_path.write_text(json.dumps(arch, indent=2, ensure_ascii=False), encoding="utf-8")
    ap_path = review_dir / "ap-policy.json"
    ap_path.write_text(json.dumps(ap, indent=2, ensure_ascii=False), encoding="utf-8")

    result = {
        "ok": True,
        "source": str(source),
        "project": str(project),
        "main_ea": str(ea),
        "profile": verify_profile,
        "docgen_rc": docgen_rc,
        "docgen_mode": "llm-bundle",
        "architecture_ok": arch.get("ok") if isinstance(arch, dict) else None,
        "ap_ok": ap["ok"],
        "senior_score": senior["score"],
        "senior_readiness": senior["readiness"],
        "outputs": {
            "docs_context": str(project / "docs" / "docs-context.json"),
            "docs_prompt": str(project / "docs" / "docs-prompt.md"),
            "senior_review_docx": str(senior_docx),
            "senior_review_json": str(senior_json),
            "architecture_check": str(arch_path),
            "ap_policy": str(ap_path),
        },
    }
    (review_dir / "EA-INTAKE-REVIEW-SUMMARY.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-shot intake + static senior review for existing EA.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name")
    ap.add_argument("--profile", default="auto")
    args = ap.parse_args(argv)
    result = run_intake_review(args.source, args.out_dir, args.name, args.profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["senior_readiness"] != "release-blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
