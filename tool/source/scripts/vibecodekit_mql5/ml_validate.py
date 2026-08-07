"""ML/ONNX validation evidence checker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .evidence_v2 import sha256_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create ML validation evidence manifest.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--oos-report", required=True)
    ap.add_argument("--tester-report", required=True)
    ap.add_argument("--fallback-defined", action="store_true")
    ap.add_argument("--out", default="evidence/ml-validation.json")
    args = ap.parse_args(argv)

    files = {
        "model_sha256": args.model,
        "feature_schema_sha256": args.features,
        "oos_report_sha256": args.oos_report,
        "strategy_tester_report_sha256": args.tester_report,
    }
    report: dict[str, Any] = {"schema_version": "1.0", "fallback_defined": args.fallback_defined}
    missing = []
    for key, path in files.items():
        p = Path(path)
        if p.exists() and p.is_file():
            report[key] = sha256_file(p)
            report[key.replace("_sha256", "_path")] = str(p)
        else:
            report[key] = None
            missing.append(str(p))
    report["ok"] = not missing and args.fallback_defined
    report["missing"] = missing + ([] if args.fallback_defined else ["fallback_defined"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
