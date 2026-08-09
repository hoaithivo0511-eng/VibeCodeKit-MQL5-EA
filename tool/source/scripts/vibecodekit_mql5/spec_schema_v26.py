"""EA-SPEC v2.6 schema — the hardened contract spec behind ``vkmql-check``.

v2.5.x shipped a *build* spec (``spec_schema.EaSpec``: name/preset/stack/
symbol/timeframe + risk/signal blocks) used by ``mql5-auto-build`` to render
a scaffold. v2.6 introduces a *governance* spec — ``EA-SPEC.yaml`` — that the
contract checker, TIP graph, and release gate read to decide whether an EA is
allowed to claim release-eligibility.

The two schemas are deliberately separate documents with separate validators:
the build spec is unchanged (no migration, no breakage), and the v2.6 spec is
additive. ``contract_check`` and ``ai_build_contract`` route ALL EA-SPEC
validation through *this* module (anti-bloat rule #4: one schema, no
duplicated validators).

v2.6 EA-SPEC.yaml shape::

    project:
      name:    GuardEA
      version: 0.1.0
      status:  DRAFT-NOT-VALIDATED
    strategy:
      class:        trend-follow | breakout | mean-reversion | grid-safe | ml
      symbols:      [XAUUSD]
      timeframes:   [M5]
      entry_logic:  "..."
      exit_logic:   "..."
      forbidden_logic: [unbounded_martingale]
    risk:
      max_lot:            1.0
      risk_per_trade_pct: 0.5
      max_daily_loss_pct: 5.0
      max_drawdown_pct:   20.0
      max_positions:      3
      stop_loss_required: true
    execution:
      account_modes:       [netting, hedging]
      slippage_points_max: 30
      spread_points_max:   40
      magic_number_policy: required
    validation:
      compile_required:          true
      backtest_required:         true
      stress_required:           true
      evidence_manifest_required: true
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Statuses the kit recognises, ordered from least to most validated. Anything
# above DRAFT requires evidence; see release_gate_v26 / contract_check.
VALID_STATUSES: tuple[str, ...] = (
    "DRAFT-NOT-VALIDATED",
    "CONTRACT-PASSED",
    "COMPILE-PASSED",
    "BACKTEST-PASSED",
    "STRESS-PASSED",
    "REVIEW-PASSED",
    "RELEASE-CANDIDATE",
    "RELEASE-ELIGIBLE",
)

# Claims that may NEVER appear in a status/readme without full evidence.
FORBIDDEN_READY_CLAIMS: tuple[str, ...] = (
    "READY",
    "LIVE-READY",
    "LIVE READY",
    "PRODUCTION-READY",
    "PRODUCTION READY",
)

VALID_STRATEGY_CLASSES: frozenset[str] = frozenset(
    {"trend-follow", "breakout", "mean-reversion", "grid-safe", "ml", "hybrid"}
)
VALID_ACCOUNT_MODES: frozenset[str] = frozenset({"netting", "hedging"})
VALID_MAGIC_POLICIES: frozenset[str] = frozenset({"required", "optional"})
VALID_WORKFLOW_MODES: frozenset[str] = frozenset({"lite", "standard", "full"})
VALID_RELEASE_TARGETS: frozenset[str] = frozenset(
    {"draft", "backtest", "forward", "live"}
)
VALID_ENVIRONMENT_AUTHORITIES: frozenset[str] = frozenset(
    {"windows-native", "wine-development"}
)


class SpecV26ValidationError(ValueError):
    """Raised when an ``EA-SPEC.yaml`` v2.6 document is invalid."""


@dataclass
class SpecV26Result:
    """Outcome of validating an EA-SPEC v2.6 document."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    spec: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "spec": self.spec,
        }


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_block(errors: list[str], spec: dict, key: str) -> dict:
    blk = spec.get(key)
    if not isinstance(blk, dict):
        errors.append(f"spec.{key} block is missing or not a mapping")
        return {}
    return blk


def validate_spec_v26(spec: Any) -> SpecV26Result:
    """Validate a parsed EA-SPEC v2.6 dict. Never raises; collects everything.

    The single source of truth for what a hardened EA-SPEC must contain.
    Both ``contract_check`` and ``ai_build_contract`` call this.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(spec, dict):
        return SpecV26Result(
            ok=False, errors=[f"spec must be a mapping, got {type(spec).__name__}"]
        )

    schema_version = spec.get("schema_version")
    if schema_version is not None and str(schema_version) not in {"2.6", "3.0"}:
        errors.append("spec.schema_version must be '2.6' or '3.0'")

    # project ---------------------------------------------------------------
    project = _check_block(errors, spec, "project")
    if project:
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("spec.project.name must be a non-empty string")
        if not isinstance(project.get("version"), str):
            warnings.append("spec.project.version missing (recommended)")
        status = project.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            errors.append(
                f"spec.project.status={status!r} not in {list(VALID_STATUSES)}"
            )

    # strategy --------------------------------------------------------------
    strategy = _check_block(errors, spec, "strategy")
    if strategy:
        klass = strategy.get("class")
        if not isinstance(klass, str) or klass not in VALID_STRATEGY_CLASSES:
            errors.append(
                f"spec.strategy.class={klass!r} not in {sorted(VALID_STRATEGY_CLASSES)}"
            )
        for list_key in ("symbols", "timeframes"):
            val = strategy.get(list_key)
            if not isinstance(val, list) or not val:
                errors.append(f"spec.strategy.{list_key} must be a non-empty list")
        for txt_key in ("entry_logic", "exit_logic"):
            if not isinstance(strategy.get(txt_key), str) or not strategy.get(txt_key):
                warnings.append(f"spec.strategy.{txt_key} should describe the logic")
        forbidden = strategy.get("forbidden_logic", [])
        if forbidden and not isinstance(forbidden, list):
            errors.append("spec.strategy.forbidden_logic must be a list when present")

    # risk ------------------------------------------------------------------
    risk = _check_block(errors, spec, "risk")
    if risk:
        # max_drawdown_pct is the keystone risk bound the whole gate hinges on.
        if "max_drawdown_pct" not in risk:
            errors.append("spec.risk.max_drawdown_pct is required (max drawdown bound)")
        elif not _is_num(risk["max_drawdown_pct"]) or not (
            0 < float(risk["max_drawdown_pct"]) <= 100
        ):
            errors.append("spec.risk.max_drawdown_pct must be a number in (0, 100]")
        for k, (lo, hi) in {
            "risk_per_trade_pct": (0.0, 100.0),
            "max_daily_loss_pct": (0.0, 100.0),
            "max_lot": (0.0, 1000.0),
        }.items():
            if k in risk and (not _is_num(risk[k]) or not (lo < float(risk[k]) <= hi)):
                errors.append(f"spec.risk.{k} must be a number in ({lo}, {hi}]")
        if "max_positions" in risk and (
            not isinstance(risk["max_positions"], int)
            or isinstance(risk["max_positions"], bool)
            or risk["max_positions"] < 1
        ):
            errors.append("spec.risk.max_positions must be an integer >= 1")
        if risk.get("stop_loss_required") is not True:
            warnings.append(
                "spec.risk.stop_loss_required is not true — naked positions allowed"
            )

    # execution -------------------------------------------------------------
    execution = _check_block(errors, spec, "execution")
    if execution:
        modes = execution.get("account_modes")
        if not isinstance(modes, list) or not modes:
            errors.append("spec.execution.account_modes must be a non-empty list")
        else:
            bad = [m for m in modes if m not in VALID_ACCOUNT_MODES]
            if bad:
                errors.append(
                    f"spec.execution.account_modes has invalid entries {bad}; "
                    f"valid: {sorted(VALID_ACCOUNT_MODES)}"
                )
        policy = execution.get("magic_number_policy")
        if policy is not None and policy not in VALID_MAGIC_POLICIES:
            errors.append(
                f"spec.execution.magic_number_policy={policy!r} "
                f"not in {sorted(VALID_MAGIC_POLICIES)}"
            )
        for k in ("slippage_points_max", "spread_points_max"):
            if k in execution and not _is_num(execution[k]):
                errors.append(f"spec.execution.{k} must be a number")

    # validation ------------------------------------------------------------
    validation = _check_block(errors, spec, "validation")
    if validation:
        for flag in (
            "compile_required",
            "backtest_required",
            "stress_required",
            "evidence_manifest_required",
        ):
            if flag not in validation:
                warnings.append(f"spec.validation.{flag} missing (defaults to true)")
            elif not isinstance(validation[flag], bool):
                errors.append(f"spec.validation.{flag} must be a boolean")

    # v3 governance is additive so legacy v2.6 specs remain valid. A generated
    # v3 spec always includes this block, while imported v2.6 projects may add
    # it when they opt into mode routing and semantic approval protection.
    governance = spec.get("governance")
    if governance is not None:
        if not isinstance(governance, dict):
            errors.append("spec.governance must be a mapping when present")
        else:
            mode = governance.get("mode", "standard")
            if mode not in VALID_WORKFLOW_MODES:
                errors.append(
                    f"spec.governance.mode={mode!r} not in {sorted(VALID_WORKFLOW_MODES)}"
                )
            target = governance.get("release_target", "draft")
            if target not in VALID_RELEASE_TARGETS:
                errors.append(
                    "spec.governance.release_target="
                    f"{target!r} not in {sorted(VALID_RELEASE_TARGETS)}"
                )
            for flag in (
                "semantic_approved",
                "behavior_changed",
                "trading_logic_changed",
                "risk_changed",
                "architecture_changed",
                "porting_changed",
            ):
                if flag in governance and not isinstance(governance[flag], bool):
                    errors.append(f"spec.governance.{flag} must be a boolean")
            derived = governance.get("derived_fields", [])
            if not isinstance(derived, list) or not all(
                isinstance(item, str) and item for item in derived
            ):
                errors.append("spec.governance.derived_fields must be a list of strings")

            behavior_sensitive = any(
                governance.get(flag) is True
                for flag in (
                    "behavior_changed",
                    "trading_logic_changed",
                    "risk_changed",
                    "architecture_changed",
                    "porting_changed",
                )
            )
            if mode == "lite" and behavior_sensitive:
                errors.append(
                    "spec.governance.mode='lite' cannot be used for behavioral, "
                    "trading, risk, architecture, or porting changes"
                )
            if mode != "full" and (
                governance.get("risk_changed") is True
                or governance.get("architecture_changed") is True
                or governance.get("release_target") in {"forward", "live"}
            ):
                errors.append(
                    "risk/architecture changes and forward/live targets require full mode"
                )

    release = spec.get("release")
    if release is not None:
        if not isinstance(release, dict):
            errors.append("spec.release must be a mapping when present")
        else:
            authority = release.get("environment_authority", "windows-native")
            if authority not in VALID_ENVIRONMENT_AUTHORITIES:
                errors.append(
                    "spec.release.environment_authority="
                    f"{authority!r} not in {sorted(VALID_ENVIRONMENT_AUTHORITIES)}"
                )
            if release.get("owner_approval_required_for_live") is not True:
                warnings.append(
                    "spec.release.owner_approval_required_for_live is not true"
                )

    return SpecV26Result(ok=not errors, errors=errors, warnings=warnings, spec=spec)


def load_spec_v26(path: Path) -> SpecV26Result:
    """Load + validate an EA-SPEC.yaml file from disk."""
    if not path.is_file():
        return SpecV26Result(ok=False, errors=[f"EA-SPEC not found: {path}"])
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return SpecV26Result(ok=False, errors=[f"invalid EA-SPEC yaml: {exc}"])
    return validate_spec_v26(data)


def default_spec_v26(name: str = "MyEA", symbol: str = "XAUUSD", timeframe: str = "M5") -> dict:
    """Return a minimal, valid v2.6 spec dict (DRAFT status, safe defaults).

    Used by ``spec_from_prompt`` / ``vkmql-new spec`` so a fresh project starts
    with every required risk/execution/validation field present.
    """
    return {
        "schema_version": "3.0",
        "project": {"name": name, "version": "0.1.0", "status": "DRAFT-NOT-VALIDATED"},
        "strategy": {
            "class": "trend-follow",
            "symbols": [symbol],
            "timeframes": [timeframe],
            "entry_logic": "TODO: describe entry logic",
            "exit_logic": "TODO: describe exit logic",
            "forbidden_logic": ["unbounded_martingale"],
        },
        "risk": {
            "max_lot": 1.0,
            "risk_per_trade_pct": 0.5,
            "max_daily_loss_pct": 5.0,
            "max_drawdown_pct": 20.0,
            "max_positions": 3,
            "stop_loss_required": True,
        },
        "execution": {
            "account_modes": ["netting", "hedging"],
            "slippage_points_max": 30,
            "spread_points_max": 40,
            "magic_number_policy": "required",
        },
        "validation": {
            "compile_required": True,
            "backtest_required": True,
            "stress_required": True,
            "evidence_manifest_required": True,
        },
        "governance": {
            "mode": "full",
            "release_target": "draft",
            "semantic_approved": False,
            "behavior_changed": True,
            "trading_logic_changed": True,
            "risk_changed": False,
            "architecture_changed": False,
            "porting_changed": False,
            "derived_fields": [
                "project.generated_at_utc",
                "project.artifact_hashes",
            ],
        },
        "release": {
            "environment_authority": "windows-native",
            "wine_role": "development-ci-only",
            "owner_approval_required_for_live": True,
            "onnx_mode": "optional-plugin",
            "mcp_stability": "internal-experimental",
            "telemetry": "off",
            "evidence_store": "local",
        },
    }


__all__ = [
    "VALID_STATUSES",
    "FORBIDDEN_READY_CLAIMS",
    "VALID_STRATEGY_CLASSES",
    "VALID_WORKFLOW_MODES",
    "VALID_RELEASE_TARGETS",
    "VALID_ENVIRONMENT_AUTHORITIES",
    "SpecV26ValidationError",
    "SpecV26Result",
    "validate_spec_v26",
    "load_spec_v26",
    "default_spec_v26",
]
