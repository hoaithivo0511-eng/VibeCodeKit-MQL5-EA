"""Risk-scaled workflow mode routing for Lite, Standard and Full work."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODES = ("lite", "standard", "full")
FULL_FLAGS = ("risk_changed", "architecture_changed", "porting_changed")
BEHAVIOR_FLAGS = ("behavior_changed", "trading_logic_changed", *FULL_FLAGS)


@dataclass
class ModeResult:
    ok: bool
    requested: str
    effective: str
    reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "requested": self.requested,
            "effective": self.effective,
            "reasons": list(self.reasons),
            "errors": list(self.errors),
        }


def resolve_mode(spec: dict[str, Any]) -> ModeResult:
    governance = spec.get("governance", {})
    if not isinstance(governance, dict):
        return ModeResult(False, "standard", "standard", errors=["governance is not a mapping"])
    requested = str(governance.get("mode", "standard")).lower()
    if requested not in MODES:
        return ModeResult(False, requested, "standard", errors=[f"invalid mode: {requested}"])

    effective = requested
    reasons: list[str] = []
    target = governance.get("release_target", "draft")
    full_triggered = [flag for flag in FULL_FLAGS if governance.get(flag) is True]
    if target in {"forward", "live"}:
        full_triggered.append(f"release_target={target}")
    if full_triggered and effective != "full":
        effective = "full"
        reasons.append("Full required by " + ", ".join(full_triggered))
    elif effective == "lite":
        behavior = [flag for flag in BEHAVIOR_FLAGS if governance.get(flag) is True]
        if behavior:
            effective = "standard"
            reasons.append("Lite promoted because behavior may change: " + ", ".join(behavior))
    return ModeResult(True, requested, effective, reasons=reasons)


def backtest_required(spec: dict[str, Any]) -> bool:
    governance = spec.get("governance", {})
    validation = spec.get("validation", {})
    if not isinstance(governance, dict) or not isinstance(validation, dict):
        return True
    return bool(
        validation.get("backtest_required", True)
        and (
            any(governance.get(flag) is True for flag in BEHAVIOR_FLAGS)
            or governance.get("release_target") in {"forward", "live"}
        )
    )
