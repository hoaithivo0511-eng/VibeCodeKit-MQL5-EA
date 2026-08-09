"""Completion Report parser + validator (v3 governance).

When an AI coding tool finishes a TIP it must hand back a **Completion
Report** — a markdown document the kit can parse *without an LLM* to decide
whether the work is real. This module turns that markdown into a structured
``CompletionReport`` and validates it against the originating TIP.

It is deliberately deterministic (anti-bloat rule #7: no LLM dependency):
plain regex / line scanning over a small, documented markdown convention.

Expected report convention (headings are case-insensitive)::

    # Completion Report
    TIP-ID: TIP-009
    STATUS: DONE        # DONE | PARTIAL | BLOCKED

    ## Files changed
    - Experts/MyEA.mq5
    - Include/CRiskGuard.mqh

    ## Tests
    - tests/test_myea.py::test_risk_guard  PASS

    ## Deviations
    - none

Public API::

    parse_completion_report(path) -> CompletionReport
    validate_completion_report(report, tip) -> ValidationResult
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_STATUSES: frozenset[str] = frozenset({"DONE", "PARTIAL", "BLOCKED"})

_TIP_ID_RE = re.compile(r"^\s*TIP[-_ ]?ID\s*[:=]\s*(.+?)\s*$", re.I | re.M)
_STATUS_RE = re.compile(r"^\s*STATUS\s*[:=]\s*([A-Za-z]+)\s*$", re.I | re.M)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
# Test result tokens inside a bullet line: "path::test  PASS" / "- test_x: FAIL".
_TEST_RESULT_RE = re.compile(r"\b(PASS|FAIL|SKIPPED|SKIP|ERROR)\b", re.I)


@dataclass
class CompletionReport:
    tip_id: str | None = None
    status: str | None = None
    files_changed: list[str] = field(default_factory=list)
    tests: list[dict[str, str]] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def has_test_evidence(self) -> bool:
        """True if at least one test line records a real PASS/FAIL/ERROR."""
        meaningful = [
            t for t in self.tests
            if t.get("result", "").upper() in {"PASS", "FAIL", "ERROR"}
            and t.get("name", "").strip().lower() not in {"", "none"}
        ]
        return bool(meaningful)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tip_id": self.tip_id,
            "status": self.status,
            "files_changed": list(self.files_changed),
            "tests": list(self.tests),
            "deviations": list(self.deviations),
            "has_test_evidence": self.has_test_evidence,
        }


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def _section_bullets(text: str, header_keywords: tuple[str, ...]) -> list[str]:
    """Return bullet lines under the first matching ``## <header>`` section."""
    out: list[str] = []
    in_section = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            in_section = any(k in heading for k in header_keywords)
            continue
        if not in_section:
            continue
        m = _BULLET_RE.match(raw)
        if m:
            out.append(m.group(1).strip())
    return out


def parse_completion_report_text(text: str) -> CompletionReport:
    """Parse Completion Report markdown text (no filesystem access)."""
    report = CompletionReport(raw=text)

    m = _TIP_ID_RE.search(text)
    if m:
        report.tip_id = m.group(1).strip()
    m = _STATUS_RE.search(text)
    if m:
        report.status = m.group(1).strip().upper()

    report.files_changed = [
        f for f in _section_bullets(text, ("files changed", "files", "changed"))
        if f.lower() != "none"
    ]

    for line in _section_bullets(text, ("tests", "test")):
        if line.lower() == "none":
            continue
        rm = _TEST_RESULT_RE.search(line)
        result = rm.group(1).upper() if rm else ""
        if result == "SKIPPED":
            result = "SKIP"
        name = _TEST_RESULT_RE.sub("", line).strip(" :-—\t")
        report.tests.append({"name": name, "result": result})

    report.deviations = [
        d for d in _section_bullets(text, ("deviations", "deviation"))
        if d.lower() != "none"
    ]
    return report


def parse_completion_report(path: Path | str) -> CompletionReport:
    """Parse a markdown Completion Report from a file path."""
    return parse_completion_report_text(Path(path).read_text(encoding="utf-8"))


def _allowed_paths_from_tip(tip: Any) -> list[str]:
    """Best-effort extraction of allowed paths from a TIP (dict or object)."""
    if tip is None:
        return []
    if isinstance(tip, dict):
        for key in ("allowed_paths", "allowedPaths", "paths"):
            val = tip.get(key)
            if isinstance(val, list):
                return [str(x) for x in val]
        return []
    return [str(x) for x in getattr(tip, "allowed_paths", []) or []]


def _tip_identifier(tip: Any) -> str | None:
    if tip is None:
        return None
    if isinstance(tip, dict):
        return tip.get("id") or tip.get("tip_id")
    return getattr(tip, "id", None) or getattr(tip, "tip_id", None)


def validate_completion_report(report: CompletionReport, tip: Any = None) -> ValidationResult:
    """Validate a parsed Completion Report against its originating TIP.

    Hard failures:
      - missing TIP-ID,
      - invalid / missing STATUS,
      - STATUS=DONE but no real test evidence,
      - TIP-ID does not match the given TIP (when ``tip`` is supplied).
    Warnings:
      - a changed file lives outside the TIP's allowed_paths.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not report.tip_id:
        errors.append("completion report is missing TIP-ID")
    if not report.status:
        errors.append("completion report is missing STATUS")
    elif report.status not in VALID_STATUSES:
        errors.append(
            f"completion report STATUS={report.status!r} not in {sorted(VALID_STATUSES)}"
        )

    if report.status == "DONE" and not report.has_test_evidence:
        errors.append("STATUS=DONE but the report has no test evidence (PASS/FAIL)")

    expected_id = _tip_identifier(tip)
    if expected_id and report.tip_id and report.tip_id != expected_id:
        errors.append(
            f"completion report TIP-ID={report.tip_id!r} does not match TIP {expected_id!r}"
        )

    allowed = _allowed_paths_from_tip(tip)
    if allowed:
        for changed in report.files_changed:
            if not any(changed.startswith(a.rstrip("*")) for a in allowed):
                warnings.append(
                    f"changed file {changed!r} is outside the TIP allowed_paths"
                )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


__all__ = [
    "VALID_STATUSES",
    "CompletionReport",
    "ValidationResult",
    "parse_completion_report",
    "parse_completion_report_text",
    "validate_completion_report",
]


def main(argv: list[str] | None = None) -> int:
    """CLI: parse a Completion Report markdown file and validate it."""
    import argparse
    import sys

    from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

    ap = argparse.ArgumentParser(
        prog="mql5-completion-report-parse",
        description="Parse + validate an AI Completion Report (no LLM).",
    )
    ap.add_argument("report", type=Path, help="Path to the Completion Report markdown.")
    ap.add_argument("--tip-id", default=None, help="Expected TIP-ID to validate against.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if not args.report.is_file():
        if not args.emit_json:
            sys.stderr.write(f"error: report not found: {args.report}\n")
        env = Envelope(tool="mql5-completion-report-parse", ok=False, exit_code=2,
                       summary=f"report not found: {args.report}")
        maybe_emit(args, env)
        return 2

    report = parse_completion_report(args.report)
    tip = {"id": args.tip_id} if args.tip_id else None
    res = validate_completion_report(report, tip)
    env = Envelope(
        tool="mql5-completion-report-parse", ok=res.ok, exit_code=0 if res.ok else 1,
        summary=(f"report TIP-ID={report.tip_id} STATUS={report.status}: "
                 + ("valid" if res.ok else f"INVALID ({len(res.errors)} error(s))")),
        data={"tip_id": report.tip_id, "status": report.status,
              "files_changed": report.files_changed,
              "errors": res.errors, "warnings": res.warnings},
        evidence=[str(args.report)],
        matrix_dim="governance", matrix_axis="completion-report",
        matrix_status="PASS" if res.ok else "FAIL",
    )
    if not args.emit_json:
        sys.stdout.write(("OK\n" if res.ok else "INVALID:\n" + "\n".join(res.errors) + "\n"))
    maybe_emit(args, env)
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
