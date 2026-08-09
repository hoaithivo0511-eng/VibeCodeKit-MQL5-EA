"""Canonical intermediate representation for EA requirements.

The IR is the single source of truth between intake, planning, code generation,
contracts and evidence. It deliberately separates extracted requirements from
legacy scaffold presets so a multi-engine EA is never collapsed into one label.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

IR_SCHEMA_VERSION = "3.1"


@dataclass(frozen=True)
class SourceRef:
    source: str
    page: int | None = None
    evidence: str = ""


@dataclass
class Requirement:
    id: str
    path: str
    value: Any
    confidence: float
    status: str = "extracted"  # extracted|inferred|confirmed|conflict|unresolved
    priority: str = "must"     # must|should|could
    source_refs: list[SourceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "value": self.value,
            "confidence": round(float(self.confidence), 4),
            "status": self.status,
            "priority": self.priority,
            "source_refs": [asdict(ref) for ref in self.source_refs],
        }


@dataclass
class EAIR:
    identity: dict[str, Any]
    runtime: dict[str, Any]
    strategy: dict[str, Any]
    risk: dict[str, Any] = field(default_factory=dict)
    controls: dict[str, Any] = field(default_factory=dict)
    requirements: list[Requirement] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = IR_SCHEMA_VERSION

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "identity": self.identity,
            "runtime": self.runtime,
            "strategy": self.strategy,
            "risk": self.risk,
            "controls": self.controls,
            "requirements": [r.to_dict() for r in self.requirements],
            "ambiguities": self.ambiguities,
            "conflicts": self.conflicts,
            "metadata": self.metadata,
        }
        if include_hash:
            out["ir_sha256"] = self.sha256()
        return out

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(include_hash=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def blocking_issues(self) -> list[dict[str, Any]]:
        unresolved = [a for a in self.ambiguities if a.get("severity") == "blocking"]
        return [*self.conflicts, *unresolved]

    @property
    def ready_for_planning(self) -> bool:
        return not self.blocking_issues


def from_dict(raw: dict[str, Any]) -> EAIR:
    if not isinstance(raw, dict):
        raise ValueError("EA-IR must be a mapping")  # noqa: TRY004
    if raw.get("schema_version") != IR_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported EA-IR schema_version={raw.get('schema_version')!r}; "
            f"expected {IR_SCHEMA_VERSION!r}"
        )
    legacy_keys = {"name", "preset", "stack", "symbol", "timeframe", "compatibility"}
    present_legacy = sorted(legacy_keys & set(raw))
    if present_legacy:
        raise ValueError(
            "legacy scaffold mapping cannot be relabelled as EA-IR; "
            f"unexpected top-level keys: {present_legacy}"
        )
    for section in ("identity", "runtime", "strategy"):
        if not isinstance(raw.get(section), dict):
            raise ValueError(f"EA-IR requires a {section!r} mapping")  # noqa: TRY004
    requirements: list[Requirement] = []
    for item in raw.get("requirements", []):
        if not isinstance(item, dict):
            raise ValueError(  # noqa: TRY004
                "EA-IR requirements entries must be mappings"
            )
        refs = [SourceRef(**r) for r in item.get("source_refs", [])]
        requirements.append(
            Requirement(
                id=str(item["id"]),
                path=str(item["path"]),
                value=item.get("value"),
                confidence=float(item.get("confidence", 0.0)),
                status=str(item.get("status", "extracted")),
                priority=str(item.get("priority", "must")),
                source_refs=refs,
            )
        )
    ir = EAIR(
        identity=dict(raw.get("identity") or {}),
        runtime=dict(raw.get("runtime") or {}),
        strategy=dict(raw.get("strategy") or {}),
        risk=dict(raw.get("risk") or {}),
        controls=dict(raw.get("controls") or {}),
        requirements=requirements,
        ambiguities=list(raw.get("ambiguities") or []),
        conflicts=list(raw.get("conflicts") or []),
        metadata=dict(raw.get("metadata") or {}),
    )
    claimed = raw.get("ir_sha256")
    if claimed and claimed != ir.sha256():
        raise ValueError("EA-IR ir_sha256 does not match canonical content")
    return ir
