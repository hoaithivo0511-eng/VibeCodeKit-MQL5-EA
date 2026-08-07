"""Requirements-to-code/test traceability artefact generation.

The matrix is generated from the canonical EA-IR and the capability plan.  A
caller may advance planned requirements to ``GENERATED`` or ``VERIFIED`` only
when the corresponding build/verification stage has actually completed.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from .build_planner import BuildPlan
from .ea_ir import EAIR

_VALID_IMPLEMENTED_STATES = {"PLANNED", "GENERATED", "VERIFIED"}


def rows(ir: EAIR, plan: BuildPlan, *, implemented_status: str = "PLANNED") -> list[dict[str, Any]]:
    if implemented_status not in _VALID_IMPLEMENTED_STATES:
        raise ValueError(
            f"implemented_status must be one of {sorted(_VALID_IMPLEMENTED_STATES)}, "
            f"got {implemented_status!r}"
        )
    planned = {f.path: f for f in plan.features}
    blockers_by_path: dict[str, list[dict[str, Any]]] = {}
    for blocker in plan.blockers:
        blockers_by_path.setdefault(str(blocker.get("path", "")), []).append(blocker)
    out: list[dict[str, Any]] = []
    for req in ir.requirements:
        feature = planned.get(req.path)
        blocked = blockers_by_path.get(req.path, [])
        if feature:
            status = implemented_status
            implementation = feature.implementation or ""
            tests = ";".join(feature.tests)
        elif blocked:
            status = "BLOCKED"
            implementation = ""
            tests = ""
        else:
            # Identity/runtime/parameter requirements can be emitted into
            # Config.mqh without owning a feature-registry entry.  Preserve
            # them as extracted rather than pretending code coverage.
            status = "EXTRACTED"
            implementation = ""
            tests = ""
        refs = ";".join(
            f"{r.source}:p{r.page or '-'}:{r.evidence}" for r in req.source_refs
        )
        out.append({
            "requirement_id": req.id,
            "priority": req.priority,
            "path": req.path,
            "value": req.value,
            "confidence": req.confidence,
            "source_refs": refs,
            "implementation": implementation,
            "tests": tests,
            "status": status,
        })
    return out


def to_csv(ir: EAIR, plan: BuildPlan, *, implemented_status: str = "PLANNED") -> str:
    data = rows(ir, plan, implemented_status=implemented_status)
    fields = ["requirement_id", "priority", "path", "value", "confidence",
              "source_refs", "implementation", "tests", "status"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(data)
    return buf.getvalue()
