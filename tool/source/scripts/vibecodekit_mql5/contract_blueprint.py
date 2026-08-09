"""Contract blueprint generator/validator.

Transforms owner interview into a contractor blueprint with architecture profile,
required modules, risk contract, assumptions, and acceptance criteria.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .contract_utils import read_json, write_json, validation_report, now_iso, sha256_file


REQUIRED_BLUEPRINT_PATHS = [
    "artifact_type",
    "source_interview_sha256",
    "architecture_profile",
    "required_modules",
    "risk_contract.max_dd_percent",
    "risk_contract.freeze_dd_percent",
    "acceptance_criteria",
]


def get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def make_blueprint(interview_path: str | Path) -> dict[str, Any]:
    ip = Path(interview_path)
    interview = read_json(ip)
    profile = "grid-safe" if interview.get("strategy", {}).get("allows_grid") else "default"

    modules = [
        "AsyncTradeExecutor",
        "BasketCloseEngine",
        "GridRiskGuard",
        "PersistentStateStore",
        "StructuredLogger",
    ] if profile == "grid-safe" else ["StructuredLogger", "PersistentStateStore"]

    validation = interview.get("validation_required", {})
    acceptance = [
        "owner_interview_valid",
        "blueprint_tip_no_critical",
        "owner_approval_valid",
        "architecture_check_ok",
        "ap_policy_ok",
        "ea_docs_generated",
        "ea_docs_verified",
    ]
    if validation.get("compile"):
        acceptance.append("compile_ok")
    if validation.get("backtest"):
        acceptance.append("backtest_ok")
    if validation.get("multi_broker"):
        acceptance.append("multi_broker_ok")
    if validation.get("walk_forward"):
        acceptance.append("walk_forward_ok")
    if validation.get("evidence_manifest"):
        acceptance.append("evidence_manifest_release_eligible")

    return {
        "schema_version": "1.0",
        "artifact_type": "contract_blueprint",
        "created_at": now_iso(),
        "source_interview": str(ip),
        "source_interview_sha256": sha256_file(ip),
        "architecture_profile": profile,
        "strategy_summary": interview.get("strategy", {}),
        "required_modules": modules,
        "required_hooks": ["OnTradeTransaction"] if profile == "grid-safe" else [],
        "risk_contract": {
            "max_dd_percent": interview.get("risk", {}).get("max_dd_percent"),
            "freeze_dd_percent": interview.get("risk", {}).get("freeze_dd_percent"),
            "max_levels": interview.get("risk", {}).get("max_levels"),
            "no_unbounded_martingale": interview.get("risk", {}).get("no_unbounded_martingale", False),
            "base_lot": interview.get("risk", {}).get("base_lot"),
            "lot_multiplier": interview.get("risk", {}).get("lot_multiplier"),
        },
        "broker_contract": interview.get("broker", {}),
        "acceptance_criteria": acceptance,
        "assumptions": [
            "Backtest and compile evidence must come from trusted local/remote worker sources.",
            "Grid/DCA behavior must remain bounded by max levels and DD freeze/stop.",
            "No marketing claim is accepted as evidence without manifest artifacts."
        ],
        "open_questions": interview.get("open_questions", []),
    }


def validate_blueprint(data: dict[str, Any]) -> dict[str, Any]:
    missing = [p for p in REQUIRED_BLUEPRINT_PATHS if get_path(data, p) in (None, "", [])]
    warnings = []
    rc = data.get("risk_contract", {})
    if rc.get("no_unbounded_martingale") is not True:
        missing.append("risk_contract.no_unbounded_martingale")
    if data.get("architecture_profile") == "grid-safe" and "AsyncTradeExecutor" not in data.get("required_modules", []):
        missing.append("required_modules.AsyncTradeExecutor")
    if "evidence_manifest_release_eligible" not in data.get("acceptance_criteria", []):
        warnings.append("acceptance_criteria does not require evidence manifest release eligibility")
    return validation_report(not missing, missing, warnings)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate or validate contract blueprint.")
    ap.add_argument("--interview", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if args.validate:
        data = read_json(out)
    else:
        data = make_blueprint(args.interview)
        write_json(out, data)
    report = validate_blueprint(data)
    report["artifact"] = str(out)
    print(__import__("json").dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
