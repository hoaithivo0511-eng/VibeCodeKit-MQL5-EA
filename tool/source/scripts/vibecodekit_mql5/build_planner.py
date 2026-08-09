"""Resolve EA-IR requirements into a dependency-ordered build plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .ea_ir import EAIR
from .feature_config import validate as validate_feature_config
from .feature_invariants import validate as validate_feature_invariants
from .feature_registry import FeatureCapability, get
from .runtime_input_contracts import validate_ir_values


@dataclass
class PlannedFeature:
    path: str
    maturity: str
    generator: str | None
    implementation: str | None
    tests: list[str]
    requirement_ids: list[str]


@dataclass
class BuildPlan:
    ir_sha256: str
    account_model: str | None
    features: list[PlannedFeature] = field(default_factory=list)
    blockers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "ir_sha256": self.ir_sha256,
            "account_model": self.account_model,
            "ok": self.ok,
            "features": [asdict(f) for f in self.features],
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def _toposort(paths: set[str]) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path in visited:
            return
        if path in visiting:
            raise ValueError(f"feature dependency cycle at {path}")
        visiting.add(path)
        for dep in get(path).dependencies:
            if dep in paths:
                visit(dep)
        visiting.remove(path)
        visited.add(path)
        ordered.append(path)

    for path in sorted(paths):
        visit(path)
    return ordered


def plan(ir: EAIR, *, allow_beta: bool = True) -> BuildPlan:
    result = BuildPlan(ir_sha256=ir.sha256(), account_model=ir.runtime.get("account_model"))
    result.blockers.extend(ir.blocking_issues)

    symbols = list(ir.runtime.get("symbols") or [])
    timeframes = list(ir.runtime.get("timeframes") or [])
    if len(symbols) > 1:
        result.blockers.append({
            "id": "MULTI-SYMBOL-CODEGEN-UNSUPPORTED",
            "path": "runtime.symbols",
            "values": symbols,
            "message": "The current generated runtime is single-symbol; symbol lists are preserved but not collapsed.",
        })
    if len(timeframes) > 1:
        result.blockers.append({
            "id": "MULTI-TIMEFRAME-CODEGEN-UNSUPPORTED",
            "path": "runtime.timeframes",
            "values": timeframes,
            "message": "The current generated runtime uses one signal timeframe; timeframe lists are preserved but not collapsed.",
        })
    signals = list(ir.strategy.get("signals") or [])
    signal_logic = ir.strategy.get("signal_logic")
    if len(signals) > 1 and signal_logic != "selectable":
        result.blockers.append({
            "id": "SIGNAL-COMPOSITION-UNSUPPORTED",
            "path": "strategy.signal_logic",
            "signals": signals,
            "value": signal_logic,
            "message": "Multiple signals require an explicit supported composition; current codegen supports selectable mode.",
        })

    requirement_map: dict[str, list[str]] = {}
    priorities: dict[str, set[str]] = {}
    for req in ir.requirements:
        requirement_map.setdefault(req.path, []).append(req.id)
        priorities.setdefault(req.path, set()).add(req.priority)

    requested = set(ir.strategy.get("features") or [])
    requested.update(ir.controls.get("features") or [])
    risk_capability_map = {
        "risk.max_spread_pips": "risk.max_spread",
        "risk.max_lot": "risk.max_lot",
        "risk.max_open_positions": "risk.max_positions",
        "risk.daily_loss_pct": "risk.daily_loss",
    }
    requested.update(
        risk_capability_map[path]
        for path in requirement_map
        if path in risk_capability_map
    )
    requested.update(f"strategy.entry.signals.{s}" for s in ir.strategy.get("signals") or [])

    # Validate operational values before generation. This prevents a schema-valid
    # request from silently becoming a materially different trading system.
    result.blockers.extend(validate_feature_config(ir, requested))
    result.blockers.extend(validate_feature_invariants(ir, requested))
    result.blockers.extend(validate_ir_values(ir))

    # Explicit dependencies must be included even when the source only names a
    # specialised mode such as step_multiplier.
    expanded = set(requested)
    changed = True
    while changed:
        changed = False
        for path in tuple(expanded):
            for dep in get(path).dependencies:
                if dep not in expanded:
                    expanded.add(dep)
                    changed = True

    for path in _toposort(expanded):
        cap: FeatureCapability = get(path)
        must = "must" in priorities.get(path, {"must"})
        if not cap.supported:
            issue = {
                "id": "UNSUPPORTED-FEATURE",
                "path": path,
                "maturity": cap.maturity,
                "message": cap.notes or "No generator is registered.",
                "requirement_ids": requirement_map.get(path, []),
            }
            (result.blockers if must else result.warnings).append(issue)
            continue
        if cap.maturity == "beta" and not allow_beta:
            result.blockers.append({
                "id": "BETA-FEATURE-BLOCKED", "path": path,
                "message": "Beta feature is not allowed in this build mode.",
            })
            continue
        account = result.account_model
        if account and account not in cap.account_modes:
            result.blockers.append({
                "id": "ACCOUNT-MODE-INCOMPATIBLE", "path": path,
                "account_model": account, "supported": list(cap.account_modes),
            })
            continue
        result.features.append(PlannedFeature(
            path=path, maturity=cap.maturity, generator=cap.generator,
            implementation=cap.implementation, tests=list(cap.tests),
            requirement_ids=requirement_map.get(path, []),
        ))
    return result
