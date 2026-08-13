"""Machine-readable Retro A1-A14 catalog and task-specific selector."""
from __future__ import annotations

import json
from typing import Any

CATALOG_VERSION = "1.2"


def _guard(identifier: str, name: str, severity: str, guard_class: str,
           trigger: list[str], evidence: list[str], checker: str,
           remediation: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "canonical_id": f"RETRO-{identifier}",
        "name": name,
        "severity": severity,
        "class": guard_class,
        "trigger": trigger,
        "required_evidence": evidence,
        "checker": checker,
        "remediation": remediation,
        "waiver_allowed": guard_class != "hard",
    }


GUARDS: tuple[dict[str, Any], ...] = (
    _guard("A1", "count-order-state-semantics", "P1", "waivable",
           ["count", "order", "index", "state", "max_positions"],
           ["numeric_example", "boundary_test"], "retro.count_semantics",
           "Restate semantics with numeric examples and boundary tests."),
    _guard("A2", "runtime-error-policy", "P0", "hard",
           ["error", "failure", "retry", "timeout", "broker"],
           ["failure_policy", "negative_test"], "retro.error_policy",
           "Choose fail-fast or explicit degradation with logging and tests."),
    _guard("A3", "owner-decision-lock", "P1", "waivable",
           ["decision", "approved", "semantic"],
           ["decision_entry", "locking_test"], "retro.owner_decision",
           "Record semantic intent and require approval before changing it."),
    _guard("A4", "independent-test-oracle", "P1", "waivable",
           ["test", "expected", "validation"],
           ["independent_expected_value"], "retro.expected_value",
           "Compute expected results independently from the implementation."),
    _guard("A5", "dynamic-cache-freshness", "P0", "hard",
           ["cache", "pnl", "spread", "price", "runtime_value"],
           ["freshness_policy", "stale_value_test"], "retro.dynamic_cache",
           "Fresh-read dynamic values or define and test bounded freshness."),
    _guard("A6", "async-idempotency", "P0", "hard",
           ["async", "side_effect", "order_send", "retry"],
           ["idempotency_key", "duplicate_retry_test"], "retro.async_idempotency",
           "Persist operation identity before side effects and reuse on retry."),
    _guard("A7", "test-environment-isolation", "P1", "waivable",
           ["test_state", "persist", "fixture", "environment"],
           ["isolated_state", "reset_proof"], "retro.environment_isolation",
           "Isolate and reset persisted state between tests."),
    _guard("A8", "retry-event-persistence", "P0", "hard",
           ["event", "retry", "consume", "queue"],
           ["persist_until_consumed_test"], "retro.retry_event",
           "Persist detected events until the retryable action consumes them."),
    _guard("A9", "single-unit-conversion", "P0", "hard",
           ["pip", "point", "lot", "scale", "timeframe", "slippage", "spread"],
           ["unit_table", "conversion_test"], "retro.unit_scale",
           "Use one conversion boundary and test broker digits and units."),
    _guard("A10", "port-parity", "P1", "waivable",
           ["port", "pine", "mql4", "broker", "netting", "hedging"],
           ["parity_table", "differential_test"], "retro.port_parity",
           "Build a parity table and compare behavior across platforms/profiles."),
    _guard("A11", "benchmark-integrity", "P1", "waivable",
           ["benchmark", "performance", "latency", "optimize"],
           ["anti_optimization_proof"], "retro.benchmark",
           "Prevent dead-code elimination and preserve benchmark inputs/outputs."),
    _guard("A12", "edit-target-discipline", "P1", "waivable",
           ["multi_file", "replace", "edit", "match"],
           ["target_inventory", "post_edit_validation"], "retro.tool_discipline",
           "Resolve exact targets and validate every changed file."),
    _guard("A13", "ui-claim-provenance", "P1", "waivable",
           ["panel", "ui_contract", "drawdown", "pnl", "stale", "refresh"],
           ["ui_contract", "source_resolution", "freshness_test"], "retro.ui_claim_provenance",
           "Bind every visible claim to a source, cadence, scope and bounded freshness."),
    _guard("A14", "ui-performance-integrity", "P0", "hard",
           ["panel", "canvas", "chartredraw", "onchartevent", "ontimer", "render"],
           ["performance_budget", "render_profile", "hotpath_isolation"], "retro.ui_performance",
           "Keep rendering bounded, dirty-only, and outside strategy/execution hot paths."),
)


def catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in GUARDS]


def select_guards(spec: dict[str, Any], explicit_ids: list[str] | None = None) -> list[dict[str, Any]]:
    explicit = {item.upper() for item in (explicit_ids or [])}
    text = json.dumps(spec, ensure_ascii=False).lower()
    governance = spec.get("governance", {})
    mode = governance.get("mode", "standard") if isinstance(governance, dict) else "standard"
    baseline = {"A3", "A4", "A12"}
    if mode in {"standard", "full"}:
        baseline.update({"A1", "A2", "A9"})
    selected: list[dict[str, Any]] = []
    for item in GUARDS:
        if item["id"] in explicit or item["id"] in baseline or any(
            keyword in text for keyword in item["trigger"]
        ):
            selected.append(dict(item))
    return selected


def validate_guard_list(guards: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(guards, list):
        return ["behavioral_guards must be a list"]
    known = {item["id"] for item in GUARDS}
    seen: set[str] = set()
    for index, item in enumerate(guards):
        if not isinstance(item, dict):
            errors.append(f"behavioral_guards[{index}] must be a mapping")
            continue
        identifier = item.get("id")
        if isinstance(identifier, str) and identifier.startswith("RETRO-"):
            identifier = identifier.removeprefix("RETRO-")
        if identifier not in known:
            errors.append(f"behavioral_guards[{index}].id is unknown: {identifier!r}")
        elif identifier in seen:
            errors.append(f"duplicate behavioral guard: {identifier}")
        else:
            seen.add(identifier)
        for key in ("severity", "class", "checker", "required_evidence"):
            if not item.get(key):
                errors.append(f"behavioral_guards[{index}].{key} is required")
    return errors
