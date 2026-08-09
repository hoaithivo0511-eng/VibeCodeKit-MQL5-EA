"""Evidence Matrix v2: distinguish measured, heuristic, imported, and unknown cells."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal
import json
from pathlib import Path

EvidenceType = Literal["measured", "heuristic", "imported", "none", "unknown"]
Status = Literal["passed", "failed", "warning", "unknown", "not_applicable"]


@dataclass
class MatrixCell:
    dimension: str
    axis: str
    status: Status
    evidence_type: EvidenceType
    release_blocking: bool = False
    metric: dict[str, Any] | None = None
    source: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceMatrix:
    def __init__(self, cells: list[MatrixCell] | None = None) -> None:
        self.cells = cells or []

    def add(self, cell: MatrixCell) -> None:
        self.cells.append(cell)

    def summary(self) -> dict[str, Any]:
        total = len(self.cells)
        measured = sum(1 for c in self.cells if c.evidence_type == "measured")
        heuristic = sum(1 for c in self.cells if c.evidence_type == "heuristic")
        imported = sum(1 for c in self.cells if c.evidence_type == "imported")
        unknown = sum(1 for c in self.cells if c.status == "unknown" or c.evidence_type in {"none", "unknown"})
        failed_blocking = [c for c in self.cells if c.release_blocking and c.status == "failed"]
        unknown_blocking = [c for c in self.cells if c.release_blocking and (c.status == "unknown" or c.evidence_type in {"none", "unknown"})]
        ok = not failed_blocking and not unknown_blocking and total > 0
        return {
            "total_cells": total,
            "measured_cells": measured,
            "heuristic_cells": heuristic,
            "imported_cells": imported,
            "unknown_cells": unknown,
            "release_blocking_failed": len(failed_blocking),
            "release_blocking_unknown": len(unknown_blocking),
            "ok": ok,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.0",
            "summary": self.summary(),
            "cells": [c.to_dict() for c in self.cells],
        }

    def write(self, path: str | Path) -> dict[str, Any]:
        data = self.to_dict()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


def default_8x8_unknown_matrix() -> EvidenceMatrix:
    dimensions = [
        "strategy", "risk", "execution", "broker", "portfolio", "telemetry", "robustness", "operations"
    ]
    axes = ["static", "compile", "backtest", "walkforward", "montecarlo", "multibroker", "latency", "recovery"]
    matrix = EvidenceMatrix()
    for d in dimensions:
        for a in axes:
            matrix.add(MatrixCell(
                dimension=d,
                axis=a,
                status="unknown",
                evidence_type="unknown",
                release_blocking=a in {"compile", "backtest", "multibroker", "recovery"},
                reason="No measured evidence attached.",
            ))
    return matrix


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Create or summarize Evidence Matrix v2.")
    ap.add_argument("--init-8x8", action="store_true", help="Write default 8x8 unknown matrix")
    ap.add_argument("--out", default="evidence/matrix.json")
    args = ap.parse_args(argv)
    if args.init_8x8:
        data = default_8x8_unknown_matrix().write(args.out)
        print(json.dumps(data["summary"], indent=2, ensure_ascii=False))
        return 0
    ap.error("choose --init-8x8")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
