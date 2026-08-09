"""Remote multi-broker Strategy Tester runner.

Runs the same EA/test payload across multiple worker URLs and aggregates
artifact/evidence status. It is fail-safe: any missing/failed broker makes the
overall result non-release-eligible.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import csv

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from .remote_worker_client import client_from_url
from .worker_protocol import WorkerJobRequest
from .job_bundle import make_files_bundle


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML broker config")
        return yaml.safe_load(text)
    return json.loads(text)


def run_broker_job(broker: dict[str, Any], *, ea: Path, config_text: str | None, report_name: str, out_dir: Path, timeout_sec: int) -> dict[str, Any]:
    name = broker.get("name") or broker.get("id") or "broker"
    worker_url = broker.get("worker_url")
    token = broker.get("token")
    broker_out = out_dir / name
    broker_out.mkdir(parents=True, exist_ok=True)
    if not worker_url:
        return {"broker": name, "ok": False, "reason": "missing worker_url"}

    try:
        client = client_from_url(worker_url, token=token)
        bundle = make_files_bundle([ea])
        request = WorkerJobRequest(job_type="backtest", payload={
            "broker": name,
            "ea_filename": ea.name,
            "config_text": config_text,
            "expected_report": report_name,
            "bundle": bundle,
        })
        job_id = client.submit(request)
        result = client.poll(job_id, timeout_sec=timeout_sec)
        (broker_out / "worker-result.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        check = {"ok": False, "checks": []}
        if result.status == "passed":
            check = client.download_artifacts(result, broker_out)
            (broker_out / "worker-artifact-check.json").write_text(json.dumps(check, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "broker": name,
            "ok": result.status == "passed" and bool(check.get("ok")),
            "status": result.status,
            "worker_id": result.worker_id,
            "job_id": result.job_id,
            "artifact_check": check,
            "error": result.error,
        }
    except Exception as exc:
        return {"broker": name, "ok": False, "reason": f"worker error: {exc}"}


def write_csv_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["broker", "ok", "status", "worker_id", "job_id", "reason", "error"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run remote backtests across multiple broker workers.")
    ap.add_argument("--brokers", required=True, help="JSON/YAML config with brokers list")
    ap.add_argument("--ea", required=True)
    ap.add_argument("--tester-config", required=True)
    ap.add_argument("--report-name", default="tester.xml")
    ap.add_argument("--out", default="evidence/multibroker")
    ap.add_argument("--timeout-sec", type=int, default=7200)
    args = ap.parse_args(argv)

    cfg = load_config(args.brokers)
    brokers = cfg.get("brokers", [])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ea = Path(args.ea)
    config_text = Path(args.tester_config).read_text(encoding="utf-8", errors="ignore") if Path(args.tester_config).exists() else None

    rows = [run_broker_job(b, ea=ea, config_text=config_text, report_name=args.report_name, out_dir=out, timeout_sec=args.timeout_sec) for b in brokers]
    ok = bool(rows) and all(r.get("ok") for r in rows)
    report = {
        "schema_version": "1.0",
        "ok": ok,
        "release_eligible": ok,
        "broker_count": len(rows),
        "passed_count": sum(1 for r in rows if r.get("ok")),
        "results": rows,
    }
    (out / "multibroker-runner.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv_summary(out / "multibroker-runner.csv", rows)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
