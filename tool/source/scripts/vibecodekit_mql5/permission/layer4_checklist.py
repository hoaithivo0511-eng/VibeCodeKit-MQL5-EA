"""Permission Layer 4 — CHECKLIST-GATE (Trader-17 ≥ 15/17).

Wraps :mod:`vibecodekit_mql5.trader_check`. Personal mode requires ≥ 15/17
passes; enterprise mode requires 17/17. The ``trader_check`` output is a
JSON blob with a ``checks`` list — this layer just counts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vibecodekit_mql5 import trader_check as tc_mod

MODE_THRESHOLDS: dict[str, int] = {
    "personal": 15,
    "team": 16,
    "enterprise": 17,
}


def _pass_count_from_report(report: dict) -> int:
    """Count PASS entries in a trader_check JSON blob.

    Accepts either the canonical ``evaluate()`` shape (``{check: status}``
    with an ``_summary`` key to ignore) or a list-shaped ``checks: [...]``
    payload.
    """
    if "checks" in report or "results" in report:
        items = report.get("checks") or report.get("results") or []
        return sum(1 for c in items if str(c.get("status", "")).upper() == "PASS")
    return sum(
        1 for k, v in report.items()
        if not str(k).startswith("_") and str(v).upper() == "PASS"
    )


def gate(report_json: Path, mode: str = "personal") -> dict:
    if mode not in MODE_THRESHOLDS:
        raise ValueError(f"unknown mode: {mode!r}")
    with report_json.open("r", encoding="utf-8") as f:
        report = json.load(f)
    passes = _pass_count_from_report(report)
    threshold = MODE_THRESHOLDS[mode]
    ok = passes >= threshold
    return {
        "ok": ok,
        "mode": mode,
        "pass_count": passes,
        "threshold": threshold,
        "report": str(report_json),
    }


def gate_from_ea(ea_path: Path, mode: str = "personal") -> dict:
    """Convenience: run trader_check in-process, then gate."""
    if mode not in MODE_THRESHOLDS:
        raise ValueError(f"unknown mode: {mode!r}")
    from ..mq5_io import read_mq5_text

    text = read_mq5_text(ea_path, errors="replace")
    report = tc_mod.evaluate(text)
    passes = _pass_count_from_report(report)
    threshold = MODE_THRESHOLDS[mode]
    return {
        "ok": passes >= threshold,
        "mode": mode,
        "pass_count": passes,
        "threshold": threshold,
        "report": "<in-process>",
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer4")
    ap.add_argument("--report", type=Path, default=None,
                    help="JSON output of mql5-trader-check")
    ap.add_argument("--ea", type=Path, default=None,
                    help="Path to .mq5 file; if given, runs trader_check in-process")
    ap.add_argument("--mode", choices=tuple(MODE_THRESHOLDS), default="personal")
    args = ap.parse_args()

    if args.report:
        result = gate(args.report, args.mode)
    elif args.ea:
        result = gate_from_ea(args.ea, args.mode)
    else:
        ap.error("provide --report <json> or --ea <mq5>")
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
