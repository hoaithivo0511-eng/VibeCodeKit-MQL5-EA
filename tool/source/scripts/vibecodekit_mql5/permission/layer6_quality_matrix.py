"""Permission Layer 6 — QUALITY-MATRIX (64-cell ≥ 56 PASS).

Loads a matrix JSON (output of ``mql5-rri-matrix`` or hand-edited) and
applies the kit spec §10 thresholds:

    Personal / Team : ≥ 56 PASS, 0 FAIL, ≤ 8 WARN
    Enterprise      : ≥ 60 PASS, 0 FAIL, ≤ 4 WARN

This layer is only enforced for ENTERPRISE mode; lower modes pass
through with ``skipped: true`` so the orchestrator can show what it
did and didn't do.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..rri.matrix import populate_from_inputs


def gate(matrix_json: Path, mode: str = "personal") -> dict:
    if mode != "enterprise":
        return {
            "ok": True,
            "mode": mode,
            "skipped": True,
            "reason": "quality matrix gate is enterprise-only",
            "matrix": str(matrix_json),
        }
    if not matrix_json.exists():
        return {
            "ok": False,
            "mode": mode,
            "matrix": str(matrix_json),
            "error": "matrix JSON not found",
        }
    payload = json.loads(matrix_json.read_text(encoding="utf-8"))
    matrix = populate_from_inputs(payload)
    counts = matrix.counts()
    ok = matrix.passes_enterprise()
    return {
        "ok": ok,
        "mode": mode,
        "counts": counts,
        "thresholds": {"pass_min": 60, "warn_max": 4, "fail_max": 0},
        "matrix": str(matrix_json),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer6")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--mode", choices=("personal", "team", "enterprise"),
                    default="personal")
    args = ap.parse_args()
    result = gate(args.matrix, args.mode)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
