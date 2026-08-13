"""Blueprint risk/tip reviewer.

Static review before build. Produces risk flags; critical flags block contract build.
"""
from __future__ import annotations

import argparse
from typing import Any

from .contract_utils import read_json, write_json, now_iso


def review_blueprint(data: dict[str, Any]) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []
    rc = data.get("risk_contract", {})
    modules = data.get("required_modules", [])
    acceptance = data.get("acceptance_criteria", [])

    def flag(level: str, code: str, message: str) -> None:
        flags.append({"level": level, "code": code, "message": message})

    if data.get("architecture_profile") == "grid-safe":
        if "AsyncTradeExecutor" not in modules:
            flag("critical", "MISSING_ASYNC_EXECUTOR", "grid-safe blueprint must require AsyncTradeExecutor.")
        if "BasketCloseEngine" not in modules:
            flag("critical", "MISSING_BASKET_CLOSE_ENGINE", "grid-safe blueprint must require BasketCloseEngine.")
        if rc.get("max_levels") in (None, 0):
            flag("critical", "MISSING_MAX_LEVELS", "grid-safe blueprint must bound max grid levels.")
        if rc.get("max_dd_percent") in (None, 0):
            flag("critical", "MISSING_MAX_DD", "grid-safe blueprint must define max DD hard stop.")
        if rc.get("freeze_dd_percent") in (None, 0):
            flag("critical", "MISSING_FREEZE_DD", "grid-safe blueprint must define freeze DD.")
        if rc.get("no_unbounded_martingale") is not True:
            flag("critical", "UNBOUNDED_MARTINGALE_ALLOWED", "unbounded martingale is not allowed.")

    if "compile_ok" not in acceptance:
        flag("critical", "NO_COMPILE_ACCEPTANCE", "Blueprint acceptance criteria must require compile_ok.")
    if "backtest_ok" not in acceptance:
        flag("critical", "NO_BACKTEST_ACCEPTANCE", "Blueprint acceptance criteria must require backtest_ok.")
    if "evidence_manifest_release_eligible" not in acceptance:
        flag("critical", "NO_EVIDENCE_RELEASE_GATE", "Blueprint must require release eligible evidence manifest.")
    if "multi_broker_ok" not in acceptance:
        flag("warn", "NO_MULTIBROKER_ACCEPTANCE", "Multi-broker validation is recommended for broker-sensitive EAs.")
    if "walk_forward_ok" not in acceptance:
        flag("warn", "NO_WALKFORWARD_ACCEPTANCE", "Walk-forward validation is recommended for parameter stability.")

    critical = [f for f in flags if f["level"] == "critical"]
    return {
        "schema_version": "1.0",
        "artifact_type": "blueprint_tip",
        "created_at": now_iso(),
        "ok": not critical,
        "release_blocking": bool(critical),
        "critical_count": len(critical),
        "warn_count": sum(1 for f in flags if f["level"] == "warn"),
        "flags": flags,
        "tips": [
            "Keep risk contract measurable and release-gated.",
            "Do not treat marketing claims as evidence.",
            "For grid/DCA, prefer async basket close and persistent state recovery.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Review contract blueprint before build.")
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    bp = read_json(args.blueprint)
    report = review_blueprint(bp)
    write_json(args.out, report)
    print(__import__("json").dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
