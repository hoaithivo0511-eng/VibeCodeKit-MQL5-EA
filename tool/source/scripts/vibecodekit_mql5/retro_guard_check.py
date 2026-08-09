"""Verify project evidence for the Retro behavioral guards in its contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .ai_build_contract import CONTRACT_JSON
from . import retro_checker

REPORT_PATH = Path("evidence/retro/guards.yaml")
VALID_STATUSES = {"PASS", "FAIL", "UNTESTABLE", "WAIVED"}


@dataclass
class GuardCheckResult:
    status: str
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "errors": self.errors,
                "counts": self.counts}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside_project(project_dir: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(project_dir.resolve())
        return True
    except ValueError:
        return False


def _valid_waiver(record: dict[str, Any], guard: dict[str, Any]) -> str | None:
    if guard.get("class") == "hard" or guard.get("waiver_allowed") is False:
        return "hard guard cannot be waived"
    waiver = record.get("waiver")
    if not isinstance(waiver, dict):
        return "WAIVED guard has no waiver record"
    for key in ("owner", "reason", "scope", "expires"):
        if not isinstance(waiver.get(key), str) or not waiver.get(key, "").strip():
            return f"waiver.{key} is required"
    if waiver.get("risk_acknowledged") is not True:
        return "waiver.risk_acknowledged must be true"
    try:
        if date.fromisoformat(waiver["expires"]) < date.today():
            return "waiver has expired"
    except ValueError:
        return "waiver.expires must be YYYY-MM-DD"
    return None


def evaluate(project_dir: Path | str) -> GuardCheckResult:
    project_dir = Path(project_dir)
    contract_path = project_dir / CONTRACT_JSON
    report_path = project_dir / REPORT_PATH
    if not contract_path.is_file():
        return GuardCheckResult("FAIL", [f"missing {CONTRACT_JSON}"])
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return GuardCheckResult("FAIL", [f"invalid contract JSON: {exc}"])
    required = {
        str(item.get("id")).removeprefix("RETRO-").split("-", 1)[0]: item
        for item in contract.get("behavioral_guards", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not required:
        return GuardCheckResult("FAIL", ["contract has no behavioral guards"])
    if not report_path.is_file():
        return GuardCheckResult(
            "UNTESTABLE", [f"missing {REPORT_PATH.as_posix()}"],
            {"UNTESTABLE": len(required)},
        )
    try:
        import yaml  # type: ignore

        report = yaml.safe_load(report_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return GuardCheckResult("FAIL", [f"invalid Retro evidence yaml: {exc}"])
    records = report.get("guards", []) if isinstance(report, dict) else []
    if not isinstance(records, list):
        return GuardCheckResult("FAIL", ["guards evidence must be a list"])
    indexed = {
        str(r.get("id")).removeprefix("RETRO-").split("-", 1)[0]: r
        for r in records if isinstance(r, dict) and r.get("id")
    }
    errors: list[str] = []
    counts = {status: 0 for status in VALID_STATUSES}
    missing = 0
    for identifier, guard in required.items():
        record = indexed.get(identifier)
        if record is None:
            missing += 1
            continue
        status = str(record.get("status", "")).upper()
        if status not in VALID_STATUSES:
            errors.append(f"{identifier}: invalid status {status!r}")
            continue
        counts[status] += 1
        if status == "FAIL":
            errors.append(f"{identifier}: recorded FAIL")
        elif status == "WAIVED":
            waiver_error = _valid_waiver(record, guard)
            if waiver_error:
                errors.append(f"{identifier}: {waiver_error}")
        elif status == "PASS":
            artifacts = record.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                errors.append(f"{identifier}: PASS requires hashed artifacts")
                continue
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    errors.append(f"{identifier}: artifact must be a mapping")
                    continue
                rel = artifact.get("path")
                expected = artifact.get("sha256")
                path = project_dir / str(rel)
                if not rel or not _inside_project(project_dir, path):
                    errors.append(f"{identifier}: artifact path escapes project")
                elif not path.is_file():
                    errors.append(f"{identifier}: missing artifact {rel}")
                elif not isinstance(expected, str) or _sha256(path) != expected:
                    errors.append(f"{identifier}: hash mismatch for {rel}")
            # New v3 evidence may include a checker result.  Legacy evidence
            # without this field remains structurally compatible, but is not
            # treated as semantic proof by the new init template.
            checker_result = record.get("checker_result")
            if checker_result is not None:
                actual = retro_checker.run(identifier, project_dir, record)
                if not isinstance(checker_result, dict):
                    errors.append(f"{identifier}: checker_result must be a mapping")
                elif checker_result.get("status") != actual.get("status"):
                    errors.append(
                        f"{identifier}: checker_result status {checker_result.get('status')!r} "
                        f"does not match executable result {actual.get('status')!r}"
                    )
                if actual.get("status") == "FAIL":
                    errors.extend(f"{identifier}: {item}" for item in actual.get("findings", []))
        elif status == "UNTESTABLE":
            # Keep the distinction explicit; a checker may add findings for
            # operators, but UNTESTABLE is not a release pass.
            checker_result = record.get("checker_result")
            if checker_result is not None:
                actual = retro_checker.run(identifier, project_dir, record)
                if actual.get("status") == "FAIL":
                    errors.extend(f"{identifier}: {item}" for item in actual.get("findings", []))
    if missing:
        counts["UNTESTABLE"] += missing
    if errors:
        return GuardCheckResult("FAIL", errors, counts)
    if counts["UNTESTABLE"]:
        return GuardCheckResult("UNTESTABLE", [f"{counts['UNTESTABLE']} guard(s) unproven"], counts)
    return GuardCheckResult("PASS", counts=counts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-retro-check")
    ap.add_argument("project_dir", type=Path)
    args = ap.parse_args(argv)
    result = evaluate(args.project_dir)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.ok else (3 if result.status == "UNTESTABLE" else 1)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
