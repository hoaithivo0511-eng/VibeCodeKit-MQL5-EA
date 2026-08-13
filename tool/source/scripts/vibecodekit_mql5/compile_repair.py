"""Compile repair loop.

This is intentionally conservative: it runs real compile attempts through
compile_runner, parses logs, emits repair hints, and never claims success unless
MetaEditor compile evidence says success.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .compile_log_parser import parse_compile_log, repair_hints
from .compile_repair_patch import any_applied, apply_safe_patches
from .compile_runner import main as compile_runner_main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run compile + safe repair-hint loop.")
    ap.add_argument("--ea", required=True)
    ap.add_argument("--out", default="evidence/compile-repair")
    ap.add_argument("--max-iterations", type=int, default=3)
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--metaeditor", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--source-root",
        default=None,
        help="Root that auto-patches are confined to (default: the EA's parent dir).",
    )
    ap.add_argument(
        "--no-auto-patch",
        action="store_true",
        help="Disable safe automatic source mutation; emit hints only.",
    )
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source_root = Path(args.source_root) if args.source_root else Path(args.ea).resolve().parent
    auto_patch = not args.no_auto_patch and not args.dry_run
    attempts: list[dict[str, Any]] = []
    total_patches = 0

    final_ok = False
    for i in range(1, args.max_iterations + 1):
        attempt_dir = out / f"attempt-{i}"
        cmd = ["--ea", args.ea, "--out", str(attempt_dir), "--backend", args.backend]
        if args.metaeditor:
            cmd += ["--metaeditor", args.metaeditor]
        if args.dry_run:
            cmd += ["--dry-run"]
        rc = compile_runner_main(cmd)
        manifest_path = attempt_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        log_path = attempt_dir / "compile.log"
        issues = parse_compile_log(log_path) if log_path.exists() else []
        hints = repair_hints(issues)
        attempt = {
            "iteration": i,
            "compile_runner_rc": rc,
            "manifest_summary": manifest.get("summary", {}),
            "issues": [x.to_dict() for x in issues],
            "repair_hints": hints,
        }
        if manifest.get("summary", {}).get("compile_ok") is True:
            final_ok = True
            attempts.append(attempt)
            break
        if args.dry_run:
            attempts.append(attempt)
            break
        # Real repair step: apply only the provably-safe subset of hints, then
        # re-compile. compile_ok still comes only from MetaEditor evidence.
        if auto_patch:
            patches = apply_safe_patches(
                hints,
                source_root=source_root,
                backup_dir=attempt_dir / "backup",
            )
            attempt["patches"] = patches
            applied_now = sum(1 for p in patches if p.get("applied"))
            total_patches += applied_now
            attempts.append(attempt)
            if not any_applied(patches):
                # Nothing safe left to change; stop instead of spinning.
                break
        else:
            attempt["patches"] = []
            attempts.append(attempt)
            break

    report = {
        "schema_version": "1.0",
        "ea": args.ea,
        "max_iterations": args.max_iterations,
        "iterations_run": len(attempts),
        "final_compile_ok": final_ok,
        "release_eligible": final_ok,
        "auto_patch_enabled": auto_patch,
        "source_root": str(source_root),
        "safe_patches_applied": total_patches,
        "attempts": attempts,
        "note": "This loop applies only mechanically-safe source patches (missing ';'); it does not fabricate compile success.",
    }
    # Renamed compile-repair-report.json -> repair-attempt.json (v2.2.0) so the
    # evidence bundle uses one consistent "<stage>-attempt/report" vocabulary.
    # A back-compat copy under the old name is kept for one minor release so
    # external collectors that still glob the old path keep working.
    report_path = out / "repair-attempt.json"
    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    report_path.write_text(report_text, encoding="utf-8")
    (out / "compile-repair-report.json").write_text(report_text, encoding="utf-8")
    print(json.dumps({"final_compile_ok": final_ok, "iterations_run": len(attempts), "safe_patches_applied": total_patches, "report": str(report_path), "legacy_report": str(out / "compile-repair-report.json")}, indent=2))
    return 0 if final_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
