"""Remote walk-forward runner.

Generates rolling IS/OOS windows and dispatches OOS Strategy Tester jobs to a
remote worker. Optimization orchestration is represented explicitly as required
evidence, not faked locally.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

from .remote_worker_client import client_from_url
from .worker_protocol import WorkerJobRequest
from .job_bundle import make_files_bundle


def parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError(f"invalid date: {s}")


def fmt_date(d: datetime) -> str:
    return d.strftime("%Y.%m.%d")


def generate_windows(start: str, end: str, is_days: int, oos_days: int, step_days: int | None = None) -> list[dict[str, str]]:
    step = step_days or oos_days
    cur = parse_date(start)
    end_dt = parse_date(end)
    windows = []
    while True:
        is_start = cur
        is_end = is_start + timedelta(days=is_days)
        oos_start = is_end + timedelta(days=1)
        oos_end = oos_start + timedelta(days=oos_days)
        if oos_end > end_dt:
            break
        windows.append({
            "is_from": fmt_date(is_start),
            "is_to": fmt_date(is_end),
            "oos_from": fmt_date(oos_start),
            "oos_to": fmt_date(oos_end),
        })
        cur = cur + timedelta(days=step)
    return windows


def run_oos_window(worker_url: str, token: str | None, window: dict[str, str], *, ea: Path, base_config_text: str | None, out_dir: Path, timeout_sec: int) -> dict[str, Any]:
    idx = window["oos_from"] + "_" + window["oos_to"]
    wout = out_dir / idx
    wout.mkdir(parents=True, exist_ok=True)
    try:
        client = client_from_url(worker_url, token=token)
        bundle = make_files_bundle([ea])
        request = WorkerJobRequest(job_type="backtest", payload={
            "walkforward_window": window,
            "ea_filename": ea.name,
            "base_config_text": base_config_text,
            "expected_report": f"wf_{idx}.xml",
            "note": "OOS run; optimization evidence must be supplied separately before release.",
            "bundle": bundle,
        })
        job_id = client.submit(request)
        result = client.poll(job_id, timeout_sec=timeout_sec)
        (wout / "worker-result.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        check = {"ok": False, "checks": []}
        if result.status == "passed":
            check = client.download_artifacts(result, wout)
            (wout / "worker-artifact-check.json").write_text(json.dumps(check, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"window": window, "ok": result.status == "passed" and bool(check.get("ok")), "status": result.status, "job_id": result.job_id, "worker_id": result.worker_id, "artifact_check": check, "error": result.error}
    except Exception as exc:
        return {"window": window, "ok": False, "reason": f"worker error: {exc}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run remote walk-forward OOS tests.")
    ap.add_argument("--ea", required=True)
    ap.add_argument("--base-config", required=True)
    ap.add_argument("--worker-url", required=True)
    ap.add_argument("--worker-token")
    ap.add_argument("--from-date", required=True)
    ap.add_argument("--to-date", required=True)
    ap.add_argument("--is-days", type=int, required=True)
    ap.add_argument("--oos-days", type=int, required=True)
    ap.add_argument("--step-days", type=int)
    ap.add_argument("--out", default="evidence/walkforward")
    ap.add_argument("--timeout-sec", type=int, default=7200)
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ea = Path(args.ea)
    base_config_text = Path(args.base_config).read_text(encoding="utf-8", errors="ignore") if Path(args.base_config).exists() else None
    windows = generate_windows(args.from_date, args.to_date, args.is_days, args.oos_days, args.step_days)
    rows = [run_oos_window(args.worker_url, args.worker_token, w, ea=ea, base_config_text=base_config_text, out_dir=out, timeout_sec=args.timeout_sec) for w in windows]
    ok = bool(rows) and all(r.get("ok") for r in rows)
    report = {
        "schema_version": "1.0",
        "ok": ok,
        "release_eligible": False,
        "reason": "Walk-forward runner requires optimization evidence and actual worker artifacts before release eligibility can be granted." if not ok else "OOS worker runs passed; attach optimization evidence before release.",
        "window_count": len(windows),
        "passed_count": sum(1 for r in rows if r.get("ok")),
        "windows": windows,
        "results": rows,
    }
    (out / "walkforward-runner.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
