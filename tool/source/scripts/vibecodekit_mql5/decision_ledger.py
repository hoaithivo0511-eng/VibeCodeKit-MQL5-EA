"""Structured owner Decision Ledger for Vibecode MQL5 v3.

The ledger stores semantic intent. It is deliberately separate from evidence
hashes and approval records: integrity, intent and identity are different
trust concerns.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_NAME = "DECISIONS.yaml"
LEDGER_SCHEMA_VERSION = "1.0"
DECISION_ID = re.compile(r"^DEC-[0-9]{3,}$")


@dataclass
class LedgerResult:
    ok: bool
    ledger: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ledger": self.ledger,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def default_ledger(project_name: str = "MyEA") -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "project": project_name,
        "policy": {
            "semantic_changes_require_owner_approval": True,
            "source_of_truth": True,
        },
        "decisions": [],
    }


def validate_ledger(data: Any) -> LedgerResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return LedgerResult(False, errors=["decision ledger must be a mapping"])
    if str(data.get("schema_version")) != LEDGER_SCHEMA_VERSION:
        errors.append(f"schema_version must be {LEDGER_SCHEMA_VERSION}")
    if not isinstance(data.get("project"), str) or not data.get("project", "").strip():
        errors.append("project must be a non-empty string")
    policy = data.get("policy")
    if not isinstance(policy, dict):
        errors.append("policy must be a mapping")
    elif policy.get("semantic_changes_require_owner_approval") is not True:
        errors.append("semantic changes must require owner approval")

    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        errors.append("decisions must be a list")
        decisions = []
    seen: set[str] = set()
    for index, item in enumerate(decisions):
        prefix = f"decisions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        decision_id = item.get("id")
        if not isinstance(decision_id, str) or not DECISION_ID.fullmatch(decision_id):
            errors.append(f"{prefix}.id must match DEC-NNN")
        elif decision_id in seen:
            errors.append(f"duplicate decision id: {decision_id}")
        else:
            seen.add(decision_id)
        for key in ("decided_at", "owner", "decision", "reason"):
            if not isinstance(item.get(key), str) or not item.get(key, "").strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        tests = item.get("tests", [])
        if not isinstance(tests, list) or not all(isinstance(x, str) and x for x in tests):
            errors.append(f"{prefix}.tests must be a list of strings")
        if item.get("confirmation_required_to_change") is not True:
            warnings.append(f"{prefix} is not locked against silent semantic changes")
    return LedgerResult(not errors, ledger=data, errors=errors, warnings=warnings)


def load_ledger(path: Path) -> LedgerResult:
    if not path.is_file():
        return LedgerResult(False, errors=[f"Decision Ledger not found: {path}"])
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return LedgerResult(False, errors=[f"invalid Decision Ledger yaml: {exc}"])
    return validate_ledger(data)


def ensure_ledger(project_dir: Path, project_name: str) -> Path:
    path = project_dir / LEDGER_NAME
    if path.is_file():
        return path
    import yaml  # type: ignore

    project_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(default_ledger(project_name), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def add_decision(data: dict[str, Any], *, owner: str, decision: str, reason: str,
                 tests: list[str] | None = None, example: Any = None) -> dict[str, Any]:
    decisions = list(data.get("decisions", []))
    numbers = [int(d["id"].split("-", 1)[1]) for d in decisions
               if isinstance(d, dict) and isinstance(d.get("id"), str)
               and DECISION_ID.fullmatch(d["id"])]
    decisions.append({
        "id": f"DEC-{(max(numbers, default=0) + 1):03d}",
        "decided_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner": owner,
        "decision": decision,
        "reason": reason,
        "example": example,
        "tests": list(tests or []),
        "supersedes": None,
        "confirmation_required_to_change": True,
    })
    updated = dict(data)
    updated["decisions"] = decisions
    return updated


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-decisions")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--project", default="MyEA")
    args = ap.parse_args(argv)
    path = args.project_dir / LEDGER_NAME
    if args.init or not path.exists():
        ensure_ledger(args.project_dir, args.project)
    result = load_ledger(path)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
