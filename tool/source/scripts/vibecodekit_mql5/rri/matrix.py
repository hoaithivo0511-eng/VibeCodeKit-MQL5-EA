"""mql5-rri-matrix — 8 quality dim × 8 axis = 64-cell audit matrix.

Each cell is one of PASS / WARN / FAIL / N/A. Per the kit spec §10:

    EA ships v1.0 when ≥ 56/64 PASS, 0 FAIL, ≤ 8 WARN.
    Enterprise compliance when ≥ 60/64 PASS, 0 FAIL, ≤ 4 WARN.

This module fills the matrix from a JSON inputs payload (so the same
populator is reusable by `rri_bt.py` and `layer6_quality_matrix.py`)
and emits an HTML report with color-coded cells.

cell coverage audit
------------------------------

`CELL_COVERAGE` labels each of the 64 cells with one of three classes:

    ``gate_auto``      — 6 cells with a discriminative auto-filler
                         (a gate-report tool whose
                         ``matrix_dim/matrix_axis`` lands the cell).
                         These are the only cells whose status carries
                         real per-(dim,axis) signal after running the
                         standard gate pipeline.
    ``rri_broadcast``  — cells filled by an RRI HTML review
                         (``mql5-rri bt|rr|chart``) which broadcasts a
                         single dim-level status across every axis
                         (no per-cell discrimination).  Useful for the
                         HTML report but should not be confused with
                         per-cell gating evidence.
    ``manual``         — cells with no automation at all (today: the
                         entire ``d_inference`` row).  Stay N/A unless
                         the operator hand-edits a ``--inputs`` JSON.

The legacy thresholds ``passes_personal`` / ``passes_enterprise``
assume *all 64 cells* are populated and therefore always fail in
practice because 58 of 64 cells have no gate-report auto-filler.  The
gate-only variants ``passes_personal_gate_only`` /
``passes_enterprise_gate_only`` recompute the verdict against the 6
cells the W1.4 collector can actually fill and are the recommended
verdict source for chat-driven build loops.  See ``--audit`` for a
standalone coverage report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

DIMS: tuple[str, ...] = (
    "d_correctness",
    "d_risk",
    "d_robustness",
    "d_perf",
    "d_maintainability",
    "d_observability",
    "d_broker_safety",
    "d_inference",
)

AXES: tuple[str, ...] = (
    "design",
    "implement",
    "unit_test",
    "integration",
    "backtest",
    "walk_forward",
    "multi_broker",
    "live_canary",
)

STATUSES: tuple[str, ...] = ("PASS", "WARN", "FAIL", "N/A")

# Precedence for merging multiple gate-report emitters that target the
# same (dim, axis) cell.  Higher value = more severe.  Any FAIL
# clobbers WARN/PASS/N/A; PASS only wins when every emitter for the
# cell agrees.  See ``merge_status`` below.
_STATUS_PRECEDENCE: dict[str, int] = {
    "N/A":  0,
    "PASS": 1,
    "WARN": 2,
    "FAIL": 3,
}

_STATUS_COLORS: dict[str, str] = {
    "PASS": "#2e7d32",
    "WARN": "#ed6c02",
    "FAIL": "#c62828",
    "N/A": "#9e9e9e",
}

COVERAGE_CLASSES: tuple[str, ...] = ("gate_auto", "rri_broadcast", "manual")

# Cells that a gate-report tool fills discriminatively.
# Each entry maps a (dim, axis) cell to the tools whose ``--gate-report``
# envelope's ``matrix.{dim,axis}`` block lands it.  Pinned by
# ``test_cell_coverage_matches_gate_report_tools``.
GATE_AUTO_CELLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("d_correctness", "implement"): (
        "mql5-lint", "mql5-method-hiding-check", "mql5-bt-sim",
    ),
    ("d_correctness", "integration"): ("mql5-permission",),
    ("d_risk", "design"): ("mql5-trader-check",),
    ("d_robustness", "backtest"): (
        "mql5-backtest", "mql5-monte-carlo", "mql5-mfe-mae",
        "mql5-forge-loop",
    ),
    ("d_robustness", "walk_forward"): (
        "mql5-walkforward", "mql5-overfit-check",
    ),
    ("d_broker_safety", "multi_broker"): (
        "mql5-broker-safety", "mql5-multibroker",
    ),
}

# Cells reachable by an RRI HTML review (broadcast).  Each tuple is
# (dim, axis) covered by one or more of ``rri-bt`` / ``rri-rr`` /
# ``rri-chart`` writing a uniform dim status across all 8 axes.
_RRI_BROADCAST_DIMS: tuple[str, ...] = (
    # rri_bt covers 7 dims (all except d_inference); rri_rr broadcasts
    # d_risk + d_robustness; rri_chart broadcasts d_correctness +
    # d_observability + d_perf.  Their union is exactly DIMS \\ d_inference.
    "d_correctness", "d_risk", "d_robustness", "d_perf",
    "d_maintainability", "d_observability", "d_broker_safety",
)


def _build_cell_coverage() -> dict[tuple[str, str], str]:
    coverage: dict[tuple[str, str], str] = {}
    for d in DIMS:
        for a in AXES:
            if (d, a) in GATE_AUTO_CELLS:
                coverage[(d, a)] = "gate_auto"
            elif d in _RRI_BROADCAST_DIMS:
                coverage[(d, a)] = "rri_broadcast"
            else:
                coverage[(d, a)] = "manual"
    return coverage


CELL_COVERAGE: dict[tuple[str, str], str] = _build_cell_coverage()

# Pre-computed coverage class counts so HTML rendering doesn't iterate
# the CELL_COVERAGE map three times.  Pinned alongside CELL_COVERAGE
# by ``test_cell_coverage_counts_match_audit_summary``.
COVERAGE_COUNTS: dict[str, int] = {
    cls: sum(1 for v in CELL_COVERAGE.values() if v == cls)
    for cls in COVERAGE_CLASSES
}


def merge_status(existing: str, incoming: str) -> str:
    """Combine two statuses for the same (dim, axis) cell.

    Used by :func:`populate_from_gate_reports` when more than one
    emitter targets the same cell — e.g. ``mql5-lint``,
    ``mql5-method-hiding-check`` and ``mql5-bt-sim`` all write to
    ``(d_correctness, implement)``.  Without merging, the
    alphabetically-last filename silently wins, which is a real
    correctness hazard: a FAIL from ``mql5-lint`` would be hidden by a
    PASS from ``mql5-bt-sim`` if ``rglob`` happened to enumerate them
    in that order.

    Precedence (highest wins): ``FAIL`` > ``WARN`` > ``PASS`` > ``N/A``.
    """
    if existing not in _STATUS_PRECEDENCE or incoming not in _STATUS_PRECEDENCE:
        raise ValueError(
            f"unknown status to merge: existing={existing!r} incoming={incoming!r}"
        )
    return existing if _STATUS_PRECEDENCE[existing] >= _STATUS_PRECEDENCE[incoming] else incoming


@dataclass(frozen=True)
class CellResult:
    dim: str
    axis: str
    status: str
    note: str = ""


@dataclass
class MatrixReport:
    cells: dict[tuple[str, str], CellResult] = field(default_factory=dict)

    def set(self, dim: str, axis: str, status: str, note: str = "") -> None:
        if dim not in DIMS:
            raise ValueError(f"unknown dim: {dim!r}")
        if axis not in AXES:
            raise ValueError(f"unknown axis: {axis!r}")
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status!r}")
        self.cells[(dim, axis)] = CellResult(dim, axis, status, note)

    def get(self, dim: str, axis: str) -> CellResult:
        return self.cells.get((dim, axis), CellResult(dim, axis, "N/A"))

    def counts(self) -> dict[str, int]:
        counts = {s: 0 for s in STATUSES}
        for d in DIMS:
            for a in AXES:
                counts[self.get(d, a).status] += 1
        return counts

    def counts_by_coverage(self) -> dict[str, dict[str, int]]:
        """Per-coverage-class status counts.

        Returns a mapping ``coverage_class → {status: count}`` so
        callers can ask "of the cells that *can* be auto-filled, how
        many actually came back PASS?" without conflating the
        discriminative gate-auto cells with the broadcast RRI cells
        or the strictly-manual d_inference row.
        """
        bucket: dict[str, dict[str, int]] = {
            cls: {s: 0 for s in STATUSES} for cls in COVERAGE_CLASSES
        }
        for d in DIMS:
            for a in AXES:
                bucket[CELL_COVERAGE[(d, a)]][self.get(d, a).status] += 1
        return bucket

    def passes_personal(self) -> bool:
        """Legacy threshold (the kit spec §10) over the full 64-cell matrix.

        Always fails in practice when filled solely from the W1.4
        collector because only 6 of 64 cells have a gate-report
        auto-filler. Kept for back-compat with existing matrix JSON
        consumers; prefer :meth:`passes_personal_gate_only` for the
        chat-driven build loop.
        """
        c = self.counts()
        return c["PASS"] >= 56 and c["FAIL"] == 0 and c["WARN"] <= 8

    def passes_enterprise(self) -> bool:
        """Legacy enterprise threshold (the kit spec §10) over the full 64-cell matrix.

        See :meth:`passes_personal` for the same caveat about real-world
        attainability; prefer :meth:`passes_enterprise_gate_only`.
        """
        c = self.counts()
        return c["PASS"] >= 60 and c["FAIL"] == 0 and c["WARN"] <= 4

    def passes_personal_gate_only(self) -> bool:
        """Personal-mode threshold over the 6 gate-auto cells only.

        fix: with W1.4's gate-report collector covering only
        6 discriminative cells, the legacy 56/64 threshold is
        unattainable. The gate-only variant requires every gate-auto
        cell PASS / WARN, 0 FAIL, and at most 1 WARN (≈ same proportion
        as the legacy ``≤8 WARN`` over 64).
        """
        bucket = self.counts_by_coverage()["gate_auto"]
        total = sum(bucket.values())
        return (
            bucket["FAIL"] == 0
            and bucket["WARN"] <= 1
            and bucket["PASS"] + bucket["WARN"] == total
        )

    def passes_enterprise_gate_only(self) -> bool:
        """Enterprise-mode threshold over the 6 gate-auto cells only.

        Stricter than :meth:`passes_personal_gate_only`: every
        gate-auto cell must PASS — zero WARN, zero FAIL, zero N/A.
        """
        bucket = self.counts_by_coverage()["gate_auto"]
        total = sum(bucket.values())
        return bucket["PASS"] == total


def populate_full(matrix: MatrixReport, status: str, note: str = "") -> MatrixReport:
    """Initialise every cell. Useful test helper."""
    for d in DIMS:
        for a in AXES:
            matrix.set(d, a, status, note)
    return matrix


def audit_coverage() -> dict[str, object]:
    """Standalone coverage audit — no inputs / no reports needed.

    Returns a JSON-serialisable payload describing how many cells fall
    into each coverage class plus the gate-auto cell → tool map.  This
    is what ``mql5-rri-matrix --audit`` prints.
    """
    by_class: dict[str, list[dict[str, str]]] = {
        cls: [] for cls in COVERAGE_CLASSES
    }
    for d in DIMS:
        for a in AXES:
            entry: dict[str, str] = {"dim": d, "axis": a}
            cls = CELL_COVERAGE[(d, a)]
            if cls == "gate_auto":
                entry["tools"] = ", ".join(GATE_AUTO_CELLS[(d, a)])
            by_class[cls].append(entry)
    return {
        "schema_version": "1",
        "total_cells": len(DIMS) * len(AXES),
        "counts": {cls: len(by_class[cls]) for cls in COVERAGE_CLASSES},
        "cells": by_class,
    }


def populate_from_inputs(inputs: dict) -> MatrixReport:
    """Build a matrix from a structured inputs JSON payload.

    The payload is a dict keyed by ``"<dim>/<axis>"`` with values
    ``{"status": "PASS|WARN|FAIL|N/A", "note": "..."}``. Missing cells stay
    N/A.
    """
    matrix = MatrixReport()
    for key, payload in inputs.items():
        if "/" not in key:
            raise ValueError(f"matrix key must be 'dim/axis', got {key!r}")
        dim, axis = key.split("/", 1)
        matrix.set(dim, axis, payload.get("status", "N/A"), payload.get("note", ""))
    return matrix


def populate_from_gate_reports(report_dir: Path) -> tuple[MatrixReport, list[str]]:
    """Build a matrix by scanning ``--gate-report`` envelopes in a directory.

    Every file matching ``gate-report-*.json`` is read and its top-level
    ``matrix`` block (``{dim, axis, status}``) determines which cell to
    fill. The optional ``summary`` from the envelope becomes the cell
    ``note`` so reviewers can hover-trace the verdict.

    Returns ``(matrix, evidence_paths)`` where ``evidence_paths`` is the
    sorted list of report files that contributed at least one cell.

    Files lacking a ``matrix`` block are silently ignored — they're
    typically tools whose output doesn't map to one of the 8 dimensions
    (e.g. ``mql5-doctor``).
    """

    matrix = MatrixReport()
    evidence: list[str] = []
    # Aggregate by (dim, axis): the worst status wins; notes are
    # concatenated so reviewers can see every contributing tool.
    notes: dict[tuple[str, str], list[str]] = {}
    for path in sorted(report_dir.rglob("gate-report-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cell = payload.get("matrix")
        if not isinstance(cell, dict):
            continue
        dim = cell.get("dim")
        axis = cell.get("axis")
        status = cell.get("status", "N/A")
        if not dim or not axis:
            continue
        if dim not in DIMS or axis not in AXES:
            continue
        if status not in STATUSES:
            continue
        existing = matrix.get(dim, axis).status
        merged = merge_status(existing, status)
        tool = str(payload.get("tool", path.stem)).strip() or path.stem
        note_summary = str(payload.get("summary", "")).strip()
        if note_summary:
            notes.setdefault((dim, axis), []).append(
                f"{tool}={status}: {note_summary}"
            )
        else:
            notes.setdefault((dim, axis), []).append(f"{tool}={status}")
        matrix.set(dim, axis, merged, "; ".join(notes[(dim, axis)]))
        evidence.append(str(path))
    return matrix, evidence


_COVERAGE_BORDER: dict[str, str] = {
    "gate_auto":      "3px solid #1565c0",
    "rri_broadcast": "1px dashed #6a1b9a",
    "manual":         "1px dotted #757575",
}


def render_html(matrix: MatrixReport) -> str:
    head_cells = "".join(f"<th>{escape(a)}</th>" for a in AXES)
    body_rows = []
    for d in DIMS:
        row_cells = [f"<th>{escape(d)}</th>"]
        for a in AXES:
            cell = matrix.get(d, a)
            color = _STATUS_COLORS[cell.status]
            cls = CELL_COVERAGE[(d, a)]
            border = _COVERAGE_BORDER[cls]
            opacity = "0.55" if cls == "manual" else "1.0"
            title = cell.note or f"coverage: {cls}"
            row_cells.append(
                f'<td style="background:{color};color:white;'
                f'border:{border};opacity:{opacity}" '
                f'data-coverage="{cls}" '
                f'title="{escape(title)}">'
                f"{escape(cell.status)}</td>"
            )
        body_rows.append("<tr>" + "".join(row_cells) + "</tr>")
    counts = matrix.counts()
    bucket = matrix.counts_by_coverage()
    summary = (
        f"PASS={counts['PASS']} WARN={counts['WARN']} "
        f"FAIL={counts['FAIL']} N/A={counts['N/A']}"
    )
    legend = (
        "<p style='font-size:12px'>Coverage: "
        f"<span style='border:{_COVERAGE_BORDER['gate_auto']};padding:2px 4px'>gate_auto={COVERAGE_COUNTS['gate_auto']}</span>&nbsp;"
        f"<span style='border:{_COVERAGE_BORDER['rri_broadcast']};padding:2px 4px'>rri_broadcast={COVERAGE_COUNTS['rri_broadcast']}</span>&nbsp;"
        f"<span style='border:{_COVERAGE_BORDER['manual']};padding:2px 4px;opacity:0.55'>manual={COVERAGE_COUNTS['manual']}</span>"
        f"<br>gate-auto PASS={bucket['gate_auto']['PASS']}/{sum(bucket['gate_auto'].values())} "
        f"(gate-only verdict: {'PASS' if matrix.passes_personal_gate_only() else 'FAIL'})</p>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>mql5 quality matrix</title>"
        "<style>table{border-collapse:collapse}th,td{border:1px solid #444;"
        "padding:6px;font-family:monospace;text-align:center}</style>"
        f"</head><body><h1>mql5 quality matrix</h1><p>{escape(summary)}</p>"
        f"{legend}"
        f"<table><thead><tr><th></th>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></body></html>"
    )


_OUTPUT_DEFAULT = Path("quality-matrix.html")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="mql5-rri-matrix")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--inputs", type=Path, default=None,
                     help="JSON file mapping 'dim/axis' to {status, note}")
    src.add_argument("--collect", type=Path, default=None,
                     help="Directory of gate-report-*.json envelopes; "
                          "each envelope's `matrix` block fills one cell.")
    src.add_argument("--audit", action="store_true",
                     help="Print the cell-coverage audit () and "
                          "exit — no inputs or reports needed.")
    ap.add_argument("--output", type=Path, default=_OUTPUT_DEFAULT)
    args = ap.parse_args(argv)

    if args.audit:
        if args.output != _OUTPUT_DEFAULT:
            print(
                "warning: --output is ignored when --audit is set "
                "(audit prints JSON to stdout).",
                file=sys.stderr,
            )
        print(json.dumps(audit_coverage(), indent=2))
        return 0

    evidence: list[str] = []
    if args.inputs and args.inputs.exists():
        payload = json.loads(args.inputs.read_text(encoding="utf-8"))
        matrix = populate_from_inputs(payload)
        evidence.append(str(args.inputs))
    elif args.collect and args.collect.exists():
        matrix, evidence = populate_from_gate_reports(args.collect)
    else:
        matrix = MatrixReport()  # all N/A
    args.output.write_text(render_html(matrix), encoding="utf-8")

    counts = matrix.counts()
    bucket = matrix.counts_by_coverage()
    print(json.dumps({
        "output": str(args.output),
        "counts": counts,
        "counts_by_coverage": bucket,
        "passes_personal": matrix.passes_personal(),
        "passes_enterprise": matrix.passes_enterprise(),
        "passes_personal_gate_only": matrix.passes_personal_gate_only(),
        "passes_enterprise_gate_only": matrix.passes_enterprise_gate_only(),
        "evidence": evidence,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
