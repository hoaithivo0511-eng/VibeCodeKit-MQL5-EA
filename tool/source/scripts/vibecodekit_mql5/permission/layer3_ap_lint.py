"""Permission Layer 3 — AP-LINT (8 critical anti-patterns).

Invokes the linter (`vibecodekit_mql5.lint`) and asserts none of
the 8 critical anti-patterns are flagged as ERROR. WARN-level findings
(best-practice anti-patterns) do **not** fail this layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vibecodekit_mql5 import lint as lint_mod

CRITICAL_AP_CODES: tuple[str, ...] = (
    "AP-1",
    "AP-3",
    "AP-5",
    "AP-15",
    "AP-17",
    "AP-18",
    "AP-20",
    "AP-21",
)


def gate(source: Path) -> dict:
    findings = list(lint_mod.lint_file(source))
    critical_errors = [
        f for f in findings
        if f.severity == "ERROR" and f.code in CRITICAL_AP_CODES
    ]
    warns = [f for f in findings if f.severity == "WARN"]
    ok = not critical_errors
    return {
        "ok": ok,
        "path": str(source),
        "critical_errors": [
            {"code": f.code, "line": f.line, "message": f.message}
            for f in critical_errors
        ],
        "warns_total": len(warns),
        "warn_codes": sorted({f.code for f in warns}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer3")
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    result = gate(args.source)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
