"""Release-grade compile runner with evidence output.

This compatibility command never fabricates compile success. Local/Wine execution delegates to the canonical ``mql5-compile`` engine; remote-worker evidence remains fail-closed and artifact-verified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .capability import detect_capabilities
from .compile_core import CompileFailureCode
from .compile import compile_mq5
from .env_paths import resolve_metaeditor_path
from .evidence_v2 import EvidenceManifestV2, artifact_record
from .execution_sources import assess_compile_source
from .job_bundle import make_project_bundle, write_bundle_preview
from .remote_worker_client import client_from_url
from .worker_protocol import WorkerJobRequest


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_metaeditor(
    ea: Path,
    metaeditor: Path,
    out_dir: Path,
    extra_args: list[str] | None = None,
    timeout_sec: int = 180,
    *,
    max_warnings: int = 0,
) -> dict[str, Any]:
    """Compatibility evidence wrapper over canonical ``compile.compile_mq5``.

    ``mql5-compile`` owns local/Wine MetaEditor execution and compile truth.
    This wrapper preserves the historical evidence-manifest surface without a
    second subprocess/parser implementation.
    """
    if extra_args:
        return {
            "cmd": [], "returncode": None, "log_path": str(out_dir / "compile.log"),
            "ok": False,
            "reason": "extra MetaEditor args are unsupported by the compatibility wrapper",
            "failure_codes": [CompileFailureCode.INVOCATION_FAILED.value],
            "stdout": "", "stderr": "",
        }
    log_path = out_dir / "compile.log"
    result = compile_mq5(
        ea, metaeditor=str(metaeditor), log_path=log_path, timeout=timeout_sec,
        max_warnings=max_warnings,
    )
    return {
        "cmd": [str(metaeditor), "/compile:" + str(ea), "/log:" + str(log_path)],
        "returncode": None, "log_path": str(log_path), "ok": result.success,
        "error_count": result.error_count, "warning_count": result.warning_count,
        "result_summary": result.result_summary, "failure_codes": result.failure_codes,
        "errors": result.errors, "warnings": result.warnings, "ex5_path": result.ex5_path,
        "stdout": "", "stderr": "",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run real MetaEditor compile and write evidence manifest v2.")
    ap.add_argument("--ea", required=True, help="Path to .mq5 file")
    ap.add_argument("--out", default="evidence", help="Evidence output directory")
    ap.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "local-metaeditor", "wine-metaeditor", "remote-worker"],
    )
    ap.add_argument("--metaeditor", default=None, help="MetaEditor64.exe path; defaults to METAEDITOR64/METAEDITOR_PATH")
    ap.add_argument("--worker-url", default=None, help="Remote Windows worker base URL for --backend remote-worker")
    ap.add_argument("--worker-token", default=None, help="Bearer token for remote worker")
    ap.add_argument("--project-root", default=None, help="Project root to bundle for remote compile; defaults to EA parent")
    ap.add_argument("--timeout-sec", type=int, default=3600, help="Remote worker timeout")
    ap.add_argument("--max-warnings", type=int, default=0, help="Maximum allowed MetaEditor warnings; default 0")
    ap.add_argument("--dry-run", action="store_true", help="Do not execute; write non-release manifest")
    args = ap.parse_args(argv)

    ea = Path(args.ea)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = detect_capabilities().to_dict()
    _write_json(out_dir / "capabilities.json", cap)

    compile_info: dict[str, Any] = {"ok": False, "source": "unknown", "ea": str(ea)}
    artifacts = []
    if ea.exists():
        artifacts.append({**artifact_record(ea, "source_mq5"), "required": True})

    metaeditor_path = resolve_metaeditor_path(args.metaeditor)

    if args.dry_run:
        compile_info.update({"source": "stub", "reason": "dry-run requested; no compile executed"})
    elif args.backend == "remote-worker":
        compile_info["source"] = "remote_worker_metaeditor"
        if not args.worker_url:
            compile_info.update({"ok": False, "reason": "--worker-url is required for remote-worker backend"})
        else:
            try:
                project_root = Path(args.project_root) if args.project_root else ea.parent
                bundle = make_project_bundle(project_root, required_file=ea)
                write_bundle_preview(bundle, out_dir / "job-bundle.preview.json")
                request = WorkerJobRequest(
                    job_type="compile",
                    payload={
                        "ea_filename": ea.name,
                        "ea_relative_path": str(
                            ea.name if project_root == ea.parent else ea.resolve().relative_to(project_root.resolve())
                        ),
                        "expected_ex5": ea.with_suffix(".ex5").name,
                        "bundle": bundle,
                    },
                )
                client = client_from_url(args.worker_url, token=args.worker_token)
                job_id = client.submit(request)
                result = client.poll(job_id, timeout_sec=args.timeout_sec)
                _write_json(out_dir / "worker-result.json", result.to_dict())
                if result.status == "passed":
                    check = client.download_artifacts(result, out_dir)
                    _write_json(out_dir / "worker-artifact-check.json", check)
                    compile_info.update(
                        {
                            "ok": bool(check.get("ok")),
                            "worker_id": result.worker_id,
                            "job_id": result.job_id,
                            "artifact_check": check,
                        }
                    )
                    for art in result.artifacts:
                        artifacts.append(
                            {**artifact_record(out_dir / art.filename, art.role), "required": art.required}
                        )
                else:
                    compile_info.update(
                        {
                            "ok": False,
                            "worker_id": result.worker_id,
                            "job_id": result.job_id,
                            "reason": result.error or "worker job failed",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                compile_info.update({"ok": False, "reason": f"remote worker error: {exc}"})
    elif not metaeditor_path:
        compile_info.update({
            "source": "stub",
            "reason": "MetaEditor path not configured; no compile executed",
        })
    elif not ea.exists():
        compile_info.update({
            "source": "actual_metaeditor",
            "reason": "EA source file does not exist",
            "failure_codes": [CompileFailureCode.SOURCE_STAGE_FAILED.value],
        })
    else:
        source = "wine_metaeditor" if args.backend == "wine-metaeditor" else "actual_metaeditor"
        result = run_metaeditor(
            ea,
            Path(metaeditor_path),
            out_dir,
            timeout_sec=min(args.timeout_sec, 3600),
            max_warnings=max(0, args.max_warnings),
        )
        compile_info.update(result)
        compile_info["source"] = source
        artifacts.append({**artifact_record(out_dir / "compile.log", "compile_log"), "required": True})
        artifacts.append({**artifact_record(ea.with_suffix(".ex5"), "compiled_ex5"), "required": True})

    assessment = assess_compile_source(compile_info.get("source"))
    if not assessment.trusted_for_release:
        compile_info["ok"] = False

    manifest = EvidenceManifestV2(
        compile=compile_info,
        backtest={"ok": False, "source": "unknown", "reason": "not run by compile-runner"},
        gates={"ok": False, "reason": "not run by compile-runner"},
        artifacts=artifacts,
        skipped_stages=["backtest", "gate"],
    )
    data = manifest.write(out_dir / "manifest.json")
    print(json.dumps(data["summary"], indent=2, ensure_ascii=False))
    return 0 if compile_info.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
