"""Real MT5 Strategy Tester runner wrapper.

This command never treats imported/sample reports as release evidence.
Without a configured terminal backend it writes a non-release manifest.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .capability import detect_capabilities
from .env_paths import resolve_terminal_path
from .evidence_v2 import EvidenceManifestV2, artifact_record
from .execution_sources import assess_backtest_source
from .remote_worker_client import client_from_url
from .worker_protocol import WorkerJobRequest
from .job_bundle import make_files_bundle, write_bundle_preview


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run MT5 Strategy Tester and write evidence manifest v2.")
    ap.add_argument("--ea", required=True, help="Path to .ex5 or .mq5")
    ap.add_argument("--config", help="Tester .ini config")
    ap.add_argument("--report", help="Expected tester report path")
    ap.add_argument("--out", default="evidence", help="Evidence output directory")
    ap.add_argument("--backend", default="auto", choices=["auto", "local-terminal", "wine-terminal", "remote-worker"])
    ap.add_argument("--terminal", default=None, help="terminal64.exe path; defaults to MT5_TERMINAL64/MT5_TERMINAL_PATH")
    ap.add_argument("--worker-url", default=None, help="Remote Windows worker base URL for --backend remote-worker")
    ap.add_argument("--worker-token", default=None, help="Bearer token for remote worker")
    ap.add_argument("--timeout-sec", type=int, default=7200, help="Remote worker timeout")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = detect_capabilities().to_dict()
    _write_json(out_dir / "capabilities.json", cap)

    ea = Path(args.ea)
    artifacts = []
    if ea.exists():
        artifacts.append({**artifact_record(ea, "ea_binary_or_source"), "required": True})
    if args.config and Path(args.config).exists():
        artifacts.append({**artifact_record(args.config, "tester_config"), "required": True})

    terminal_path = resolve_terminal_path(args.terminal)
    backtest_info: dict[str, Any] = {"ok": False, "source": "unknown", "ea": str(ea)}

    if args.dry_run:
        backtest_info.update({"source": "manual_unverified", "reason": "dry-run requested; no Strategy Tester executed"})
    elif args.backend == "remote-worker":
        backtest_info["source"] = "remote_worker_strategy_tester"
        if not args.worker_url:
            backtest_info.update({"ok": False, "reason": "--worker-url is required for remote-worker backend"})
        else:
            try:
                files = [ea]
                if args.config:
                    files.append(Path(args.config))
                bundle = make_files_bundle(files)
                write_bundle_preview(bundle, out_dir / "job-bundle.preview.json")
                request = WorkerJobRequest(job_type="backtest", payload={
                    "ea_filename": ea.name,
                    "config_filename": Path(args.config).name if args.config else None,
                    "expected_report": Path(args.report).name if args.report else "tester.xml",
                    "bundle": bundle,
                })
                client = client_from_url(args.worker_url, token=args.worker_token)
                job_id = client.submit(request)
                result = client.poll(job_id, timeout_sec=args.timeout_sec)
                (out_dir / "worker-result.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                if result.status == "passed":
                    check = client.download_artifacts(result, out_dir)
                    (out_dir / "worker-artifact-check.json").write_text(json.dumps(check, indent=2, ensure_ascii=False), encoding="utf-8")
                    backtest_info.update({
                        "ok": bool(check.get("ok")),
                        "worker_id": result.worker_id,
                        "job_id": result.job_id,
                        "artifact_check": check,
                    })
                    for art in result.artifacts:
                        artifacts.append({**artifact_record(out_dir / art.filename, art.role), "required": art.required})
                else:
                    backtest_info.update({"ok": False, "worker_id": result.worker_id, "job_id": result.job_id, "reason": result.error or "worker job failed"})
            except Exception as exc:
                backtest_info.update({"ok": False, "reason": f"remote worker error: {exc}"})
    elif not terminal_path:
        backtest_info.update({"source": "manual_unverified", "reason": "MT5 terminal path not configured; no test executed"})
    elif not args.config:
        backtest_info.update({"source": "actual_mt5_strategy_tester", "reason": "tester config is required"})
    else:
        source = "actual_mt5_strategy_tester"
        cmd = [str(terminal_path), "/portable", "/config:" + str(Path(args.config))]
        # Bound the Strategy Tester run so a stuck terminal cannot hang the
        # pipeline forever. A timeout is a hard failure, never release-eligible.
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=args.timeout_sec
            )
            backtest_info.update({
                "source": source,
                "returncode": proc.returncode,
                "cmd": cmd,
                "ok": proc.returncode == 0,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            })
        except subprocess.TimeoutExpired as exc:
            out_text = exc.stdout or ""
            err_text = exc.stderr or ""
            if isinstance(out_text, bytes):
                out_text = out_text.decode("utf-8", "ignore")
            if isinstance(err_text, bytes):
                err_text = err_text.decode("utf-8", "ignore")
            backtest_info.update({
                "source": source,
                "returncode": None,
                "cmd": cmd,
                "ok": False,
                "timed_out": True,
                "reason": f"Strategy Tester exceeded {args.timeout_sec}s timeout and was terminated.",
                "stdout": out_text[-4000:],
                "stderr": err_text[-4000:],
            })

    if args.report:
        report = Path(args.report)
        backtest_info["report_path"] = str(report)
        if report.exists():
            artifacts.append({**artifact_record(report, "tester_report"), "required": True})
        else:
            if backtest_info.get("ok"):
                backtest_info["ok"] = False
                backtest_info["reason"] = "Terminal returned success but tester report was not found."
        assessment = assess_backtest_source(backtest_info.get("source"), report)
    else:
        if backtest_info.get("ok"):
            backtest_info["ok"] = False
            backtest_info["reason"] = "No tester report path supplied; cannot verify Strategy Tester output."
        assessment = assess_backtest_source(backtest_info.get("source"))

    if not assessment.trusted_for_release:
        backtest_info["ok"] = False

    manifest = EvidenceManifestV2(
        compile={"ok": False, "source": "unknown", "reason": "not run by test-runner"},
        backtest=backtest_info,
        gates={"ok": False, "reason": "not run by test-runner"},
        artifacts=artifacts,
        skipped_stages=["compile", "gate"],
    )
    data = manifest.write(out_dir / "manifest.json")
    print(json.dumps(data["summary"], indent=2, ensure_ascii=False))
    return 0 if backtest_info.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
