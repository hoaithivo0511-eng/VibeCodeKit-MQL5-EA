"""Strict EA-IR -> plan -> composable MQL5 source pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import lint as lint_mod
from .build_planner import plan
from .composable_codegen import generate
from .ea_ir import from_dict


def run(ir_path: Path, out_dir: Path, *, force: bool = False, allow_beta: bool = True) -> dict[str, Any]:
    raw = json.loads(ir_path.read_text(encoding="utf-8"))
    ir = from_dict(raw)
    build_plan = plan(ir, allow_beta=allow_beta)
    report: dict[str, Any] = {
        "ir_sha256": ir.sha256(),
        "status": {
            "intake_complete": True,
            "requirements_confirmed": ir.ready_for_planning,
            "capability_satisfied": build_plan.ok,
            "source_generated": False,
            "source_complete": False,
            "compile_verified": False,
            "tester_verified": False,
            "release_eligible": False,
        },
        "plan": build_plan.to_dict(),
        "lint": None,
    }
    if not build_plan.ok:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "IR-BUILD-REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        return report

    generate(ir, build_plan, out_dir, force=force)
    main_path = out_dir / "Experts" / ir.identity["name"] / f"{ir.identity['name']}.mq5"
    source_files = sorted([*out_dir.rglob("*.mq5"), *out_dir.rglob("*.mqh")])
    errors: list[str] = []
    warnings: list[str] = []
    combined: list[str] = []
    per_file: dict[str, dict[str, list[str]]] = {}
    for source_path in source_files:
        findings = lint_mod.lint_file(source_path)
        file_errors = [f.format() for f in findings if f.severity == "ERROR"]
        file_warnings = [f.format() for f in findings if f.severity == "WARN"]
        rel = source_path.relative_to(out_dir).as_posix()
        per_file[rel] = {"errors": file_errors, "warnings": file_warnings}
        errors.extend(f"{rel}: {item}" for item in file_errors)
        warnings.extend(f"{rel}: {item}" for item in file_warnings)
        combined.append(source_path.read_text(encoding="utf-8"))
    source = "\n".join(combined)
    order_calls = any(token in source for token in ("Trade.Open(", ".Buy(", ".Sell("))
    unresolved = any(token in source for token in ("__NAME__", "__HASH__", "[DEV FILL]", "TODO", "IMPLEMENT_ME"))
    expected_markers = {f"// VCK-IMPLEMENTED:{feature.path}" for feature in build_plan.features}
    missing_markers = sorted(marker for marker in expected_markers if marker not in source)
    report["lint"] = {"errors": errors, "warnings": warnings, "files": per_file}
    report["traceability"] = {"expected": len(expected_markers), "missing_markers": missing_markers}
    report["status"]["source_generated"] = True
    report["status"]["source_complete"] = not errors and order_calls and not unresolved and not missing_markers
    report["generated_main"] = str(main_path)
    report["ok"] = bool(report["status"]["source_complete"])
    (out_dir / "IR-BUILD-REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-ir-build")
    ap.add_argument("--ir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--stable-only", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = run(args.ir, args.out_dir, force=args.force, allow_beta=not args.stable_only)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"mql5-ir-build: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
