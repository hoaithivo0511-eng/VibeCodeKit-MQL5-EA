"""Conservative, executable checks for the v3 Retro A1-A12 guards.

These checks deliberately prove configuration and evidence boundaries, not the
full semantics of an MQL5 program.  Missing proof is ``UNTESTABLE`` rather
than a guessed PASS.  A Windows/MetaEditor run can attach stronger artifacts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from . import decision_ledger as dl
from . import retro_guards as rg

Status = str


def _result(status: Status, *findings: str, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"status": status, "findings": list(findings), "confidence": 0.9}
    data.update(extra)
    return data


def _yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import yaml  # type: ignore
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _spec(project_dir: Path) -> dict[str, Any]:
    spec = _yaml(project_dir / "EA-SPEC.yaml") or _yaml(project_dir / "ea-spec.yaml") or {}
    if "ui_contract" not in spec:
        ui = _yaml(project_dir / "UI-CONTRACT.yaml") or _yaml(project_dir / "ui-contract.yaml")
        if isinstance(ui, dict):
            spec["ui_contract"] = ui.get("ui_contract", ui)
    return spec


def _source(project_dir: Path) -> str:
    chunks: list[str] = []
    for path in project_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".mq5", ".mqh", ".mq4", ".pine", ".py"}:
            if any(part in {"evidence", ".git", "build", "dist"} for part in path.parts):
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(chunks).lower()


def _policy(spec: dict[str, Any], *names: str) -> Any:
    for block_name in ("governance", "execution", "validation", "risk"):
        block = spec.get(block_name)
        if isinstance(block, dict):
            for name in names:
                if name in block:
                    return block[name]
    return None


def _proof(record: dict[str, Any], *names: str) -> bool:
    evidence = record.get("evidence")
    if isinstance(evidence, dict):
        return all(evidence.get(name) not in (None, "", [], {}) for name in names)
    return False


def _a1(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    triggered = any(x in source for x in ("max_positions", "position_count", "order_count", "index"))
    if not triggered and not _proof(record, "numeric_example", "boundary_test"):
        return _result("PASS", "no count/order-state implementation trigger found", not_applicable=True)
    if _proof(record, "numeric_example", "boundary_test") or all(_policy(spec, x) is not None for x in ("numeric_examples", "boundary_tests")):
        return _result("PASS", "numeric semantics and boundaries are declared")
    return _result("UNTESTABLE", "count/order-state semantics need numeric examples and boundary-test evidence")


def _a2(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    policy = _policy(spec, "error_policy", "failure_policy", "runtime_error_policy")
    valid = {"fail_fast", "degrade_log", "retry_idempotent"}
    if policy is None:
        return _result("UNTESTABLE", "runtime error policy is not declared")
    if str(policy).lower() not in valid:
        return _result("FAIL", f"unsupported runtime error policy: {policy!r}")
    if not _proof(record, "negative_test"):
        return _result("UNTESTABLE", "error policy declared but negative-test evidence is missing")
    return _result("PASS", f"runtime policy {policy!r} has negative-test evidence")


def _a3(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    ledger_path = project_dir / dl.LEDGER_NAME
    ledger = dl.load_ledger(ledger_path)
    if not ledger.ok:
        return _result("UNTESTABLE", "Decision Ledger is missing or invalid", errors=ledger.errors)
    decisions = ledger.ledger.get("decisions", [])
    semantic = [d for d in decisions if isinstance(d, dict) and d.get("confirmation_required_to_change") is True]
    if semantic and not all(isinstance(d.get("tests"), list) and d.get("tests") for d in semantic):
        return _result("FAIL", "a locked semantic decision has no locking test")
    if semantic and not _proof(record, "locking_test"):
        return _result("UNTESTABLE", "Decision Ledger exists but locking-test evidence is missing")
    return _result("PASS", "Decision Ledger is valid and semantic decisions are locked")


def _a4(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    if not any(p.is_file() for p in project_dir.rglob("test*.py")) and not _source(project_dir):
        return _result("UNTESTABLE", "no test/source inventory for an independent oracle")
    if not _proof(record, "independent_expected_value"):
        return _result("UNTESTABLE", "independent expected-value evidence is missing")
    return _result("PASS", "independent expected-value evidence is declared")


def _a5(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    triggered = bool(re.search(r"\b(cache|cached|memo|stale|last_price|last_spread|last_pnl)\b", source))
    if not triggered:
        return _result("PASS", "no dynamic-cache implementation trigger found", not_applicable=True)
    policy = _policy(spec, "cache_policy", "freshness_policy")
    if policy is None:
        return _result("UNTESTABLE", "dynamic cache detected without freshness policy")
    if not _proof(record, "stale_value_test"):
        return _result("UNTESTABLE", "freshness policy declared but stale-value evidence is missing")
    return _result("PASS", "dynamic cache has a freshness policy and stale-value evidence")


def _a6(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    triggered = bool(re.search(r"ordersend|ordersendasync|positionopen|\.buy\s*\(|\.sell\s*\(|retry|async", source))
    if not triggered:
        return _result("PASS", "no order/async side-effect trigger found", not_applicable=True)
    policy = _policy(spec, "idempotency_policy", "idempotency", "async_policy")
    if policy is None:
        return _result("UNTESTABLE", "order/async side effect detected without idempotency policy")
    if str(policy).lower() in {"forbidden", "none", "disabled"}:
        return _result("FAIL", "side-effect path explicitly disables idempotency")
    if not _proof(record, "idempotency_key", "duplicate_retry_test"):
        return _result("UNTESTABLE", "idempotency policy declared but duplicate-retry evidence is missing")
    return _result("PASS", "idempotency policy and duplicate-retry evidence are present")


def _a7(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    if not any(x in source for x in ("fixture", "persist", "test_state", "sqlite")):
        return _result("PASS", "no persisted test-state trigger found", not_applicable=True)
    isolated = _policy(spec, "test_environment", "environment_policy")
    if not isinstance(isolated, dict) or isolated.get("isolated") is not True:
        return _result("UNTESTABLE", "persisted test state needs an isolated test-environment declaration")
    if not _proof(record, "reset_proof"):
        return _result("UNTESTABLE", "isolated environment declared but reset proof is missing")
    return _result("PASS", "test state isolation and reset evidence are present")


def _a8(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    if not any(x in source for x in ("retry", "event", "queue", "consume")):
        return _result("PASS", "no retry-event trigger found", not_applicable=True)
    if _policy(spec, "retry_event_policy", "event_persistence_policy") is None:
        return _result("UNTESTABLE", "retry/event path has no persist-until-consumed policy")
    if not _proof(record, "persist_until_consumed_test"):
        return _result("UNTESTABLE", "retry-event policy declared but consumption evidence is missing")
    return _result("PASS", "retry-event persistence policy and evidence are present")


def _a9(project_dir: Path, spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = _source(project_dir)
    if not re.search(r"\b(pips?|points?|lots?|scale|slippage|spread(?:[_a-z]*)?|timeframe)\b", source):
        return _result("PASS", "no unit/scale trigger found", not_applicable=True)
    table = _policy(spec, "unit_policy", "conversion_table", "unit_scale_policy")
    if table is None:
        return _result("UNTESTABLE", "unit/scale terms detected without a conversion policy/table")
    if not _proof(record, "conversion_test"):
        return _result("UNTESTABLE", "conversion policy declared but conversion-test evidence is missing")
    return _result("PASS", "single conversion policy and evidence are present")


def _evidence_guard(project_dir: Path, spec: dict[str, Any], record: dict[str, Any], key: str, policy_names: tuple[str, ...], message: str) -> dict[str, Any]:
    source = _source(project_dir)
    if not any(token in source for token in policy_names):
        return _result("PASS", f"no {message} trigger found", not_applicable=True)
    if _policy(spec, *policy_names) is None:
        return _result("UNTESTABLE", f"{message} trigger found without declared policy")
    if not _proof(record, key):
        return _result("UNTESTABLE", f"{message} policy declared but evidence is missing")
    return _result("PASS", f"{message} policy and evidence are present")


def _a10(p: Path, s: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    return _evidence_guard(p, s, r, "differential_test", ("port", "pine", "mql4", "netting", "hedging"), "port/broker parity")


def _a11(p: Path, s: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    return _evidence_guard(p, s, r, "anti_optimization_proof", ("benchmark", "performance", "latency", "optimize"), "benchmark")


def _a12(p: Path, s: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    changed = r.get("changed_files")
    if not changed:
        return _result("UNTESTABLE", "changed_files inventory is required for edit-target discipline")
    if not isinstance(changed, list) or not all(isinstance(x, str) and x for x in changed):
        return _result("FAIL", "changed_files must be a non-empty list of relative paths")
    return _result("PASS", "changed-files inventory is explicit", changed_files=changed)

def _a13(p: Path, s: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    ui = s.get("ui_contract") if isinstance(s.get("ui_contract"), dict) else None
    if not ui:
        return _result("PASS", "no UI contract; panel not in scope", not_applicable=True)
    rows = ui.get("rows", [])
    bad = [row.get("id", "?") for row in rows if not row.get("source") or not row.get("refresh")]
    if bad:
        return _result("FAIL", "UI claims lack source or refresh cadence", rows=bad)
    evidence = p / "evidence/ui/contract-conformance.json"
    claims = p / "evidence/ui/claims.json"
    if not evidence.is_file() or not claims.is_file():
        return _result("UNTESTABLE", "UI provenance evidence files are missing")
    try:
        ev, cl = json.loads(evidence.read_text()), json.loads(claims.read_text())
    except Exception as exc:
        return _result("FAIL", f"UI provenance evidence is invalid JSON: {exc}")
    if ev.get("status") != "PASS" or cl.get("status") != "PASS" or not cl.get("source") or not cl.get("recorded_at_utc"):
        return _result("FAIL", "UI provenance evidence lacks PASS/source/timestamp")
    return _result("PASS", "UI claim source, cadence and freshness are declared")

def _a14(p: Path, s: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    ui = s.get("ui_contract") if isinstance(s.get("ui_contract"), dict) else None
    if not ui:
        return _result("PASS", "no UI contract; panel not in scope", not_applicable=True)
    perf = ui.get("performance", {})
    if perf.get("dirty_only") is not True or perf.get("chart_redraw_policy") != "on_change_only":
        return _result("FAIL", "UI performance contract is not dirty-only/on-change-only")
    profile = p / "evidence/ui/performance-profile.json"
    if not profile.is_file():
        return _result("UNTESTABLE", "UI performance profile is missing")
    try:
        data = json.loads(profile.read_text())
    except Exception as exc:
        return _result("FAIL", f"UI performance profile is invalid JSON: {exc}")
    if data.get("status") != "PASS" or not data.get("source") or not data.get("recorded_at_utc"):
        return _result("FAIL", "UI performance profile lacks PASS/source/timestamp")
    return _result("PASS", "UI render is bounded and hot-path evidence is present")


CHECKERS: dict[str, Callable[[Path, dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "A1": _a1, "A2": _a2, "A3": _a3, "A4": _a4, "A5": _a5, "A6": _a6,
    "A7": _a7, "A8": _a8, "A9": _a9, "A10": _a10, "A11": _a11, "A12": _a12,
    "A13": _a13, "A14": _a14,
}


def run(identifier: str, project_dir: Path | str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    key = str(identifier).removeprefix("RETRO-").split("-", 1)[0].upper()
    checker = CHECKERS.get(key)
    if checker is None:
        return _result("FAIL", f"unknown Retro checker: {identifier}")
    return checker(Path(project_dir), _spec(Path(project_dir)), record or {})


def catalog_checkers() -> list[str]:
    return sorted(CHECKERS)
