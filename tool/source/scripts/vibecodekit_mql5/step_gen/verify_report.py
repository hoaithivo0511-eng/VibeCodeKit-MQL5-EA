"""mql5-verify-report — emit ``verify-report.md`` summary.

Aggregates the gate-report envelopes produced by the kit's gate
tools (``mql5-lint``, ``mql5-trader-check``, ``mql5-backtest``,
``mql5-walkforward``, ``mql5-monte-carlo``, ``mql5-permission``, etc.)
into a single human-readable Markdown report the Contractor presents to
the Homeowner at Step 7 of the methodology.

The report has six sections:

* ``OVERALL STATUS`` — ``READY`` / ``NEEDS_FIXES`` / ``MAJOR_ISSUES``.
* ``REQ COVERAGE`` — invariant ↔ test mapping (when the blueprint is
  supplied via ``--blueprint``).
* ``SCENARIO RESULTS`` — per gate-report PASS / WARN / FAIL summary.
* ``TECH HEALTH`` — lint / method-hiding / trader-check / permission.
* ``CRITICAL ISSUES`` — every FAIL surfaced from the envelopes.
* ``DECISIONS NEEDED`` — counts how many SUGGESTIONS come from
  Completion Reports, when ``--completion-dir`` is supplied.

The report is deterministic given the same inputs — no LLM, no random
ordering, no time-dependent string. Designed so the Contractor LLM
(Claude Chat) reads the report once and copy-pastes the four REFINE
options to the Homeowner.

Status semantics:

* ``READY`` — zero FAILs across gate reports AND every blueprint
  invariant has a matching item in any TIP file (when ``--tip-dir`` is
  supplied).
* ``NEEDS_FIXES`` — at least one WARN but no FAILs; the Builder can
  iterate without re-opening the contract.
* ``MAJOR_ISSUES`` — at least one FAIL. The Contractor presents a
  ``[A] Ship as-is / [B] Fix … / [C] Custom`` choice but the default
  recommendation must be "do not ship".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)

TOOL = "mql5-verify-report"

# Tools whose envelopes feed the "TECH HEALTH" section.
TECH_HEALTH_TOOLS = frozenset(
    {
        "mql5-lint",
        "mql5-method-hiding-check",
        "mql5-trader-check",
        "mql5-permission",
    }
)

# Tools whose envelopes feed the "SCENARIO RESULTS" section.
SCENARIO_TOOLS = frozenset(
    {
        "mql5-backtest",
        "mql5-walkforward",
        "mql5-monte-carlo",
        "mql5-multibroker",
        "mql5-overfit-check",
        "mql5-mfe-mae",
        "mql5-bt-sim",
        "mql5-forge-loop",
        "mql5-broker-safety",
        "mql5-fitness",
    }
)


@dataclass(frozen=True)
class GateReport:
    """Loaded view of a single gate-report-*.json envelope."""

    path: Path
    tool: str
    ok: bool
    exit_code: int
    summary: str
    status: str  # PASS / WARN / FAIL (derived)


def _derive_status(payload: dict) -> str:
    """Map a envelope to a PASS / WARN / FAIL status.

    The envelope can carry an explicit ``matrix.status`` field (annotation). When absent we infer:

    * ``ok=True`` + ``data.draft=True`` → WARN (draft mode downgraded a FAIL)
    * ``ok=True`` → PASS
    * ``ok=False`` → FAIL
    """

    matrix = payload.get("matrix")
    if isinstance(matrix, dict) and matrix.get("status") in {"PASS", "WARN", "FAIL"}:
        return matrix["status"]
    data = payload.get("data") or {}
    if payload.get("ok") and isinstance(data, dict) and data.get("draft"):
        return "WARN"
    if payload.get("ok"):
        return "PASS"
    return "FAIL"


def load_gate_reports(report_dir: Path) -> list[GateReport]:
    """Load every ``gate-report-*.json`` (or ``*.json``) under a directory.

    The kit's gate tools name their dumps ``gate-report-<tool>.json`` but
    we accept any ``*.json`` so this CLI also works on hand-curated
    folders (e.g. the operator stripped the prefix for readability).
    """

    if not report_dir.is_dir():
        return []
    out: list[GateReport] = []
    for path in sorted(report_dir.rglob("*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") != "1":
            continue
        tool = payload.get("tool")
        if not isinstance(tool, str):
            continue
        out.append(
            GateReport(
                path=path,
                tool=tool,
                ok=bool(payload.get("ok")),
                exit_code=int(payload.get("exit_code", 0)),
                summary=str(payload.get("summary", "")).strip(),
                status=_derive_status(payload),
            )
        )
    return out


_INVARIANT_HEADING = re.compile(r"^##\s+Invariants\s*$", re.MULTILINE)


def extract_invariants(blueprint_body: str) -> list[str]:
    """Return the list of invariant bullets under ``## Invariants``.

    Mirrors ``contract_gen._extract_section_items`` semantics (drops
    optional ``[ ]`` / ``[x]`` checkbox prefixes) but kept independent so
    this module never imports the contract module — they are siblings.
    """

    if not _INVARIANT_HEADING.search(blueprint_body):
        return []
    out: list[str] = []
    in_section = False
    for line in blueprint_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Invariants"
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            text = stripped[2:].strip()
            text = re.sub(r"^\[[ xX]\]\s*", "", text).strip()
            if text and not text.startswith("_") and not text.startswith("("):
                out.append(text)
    return out


def map_invariants_to_tips(invariants: list[str], tip_dir: Path) -> dict[str, list[str]]:
    """Greedy substring match — each invariant lists TIP files mentioning it.

    The mapping is intentionally lenient: an invariant counts as
    "covered" if any TIP body contains at least one keyword fragment
    (≥ 8 chars from the invariant after lower-casing). This is good
    enough for the Step-7 sanity check; the deeper coverage matrix
    lives in ``mql5-rri-matrix --collect``.
    """

    if not tip_dir.is_dir():
        return {inv: [] for inv in invariants}
    tip_bodies: dict[str, str] = {}
    for path in sorted(tip_dir.rglob("*.md")):
        if path.is_file():
            try:
                tip_bodies[path.name] = path.read_text(encoding="utf-8").lower()
            except OSError:
                continue
    mapping: dict[str, list[str]] = {}
    for inv in invariants:
        inv_lower = inv.lower()
        # Pull "interesting" tokens — drop short stop-words.
        tokens = [tok for tok in re.findall(r"[a-z][a-z0-9_]{4,}", inv_lower)
                  if tok not in {"every", "must", "with", "from", "should",
                                  "without", "across", "after", "before",
                                  "while", "between"}]
        if not tokens:
            mapping[inv] = []
            continue
        hits: list[str] = []
        for name, body in tip_bodies.items():
            if any(tok in body for tok in tokens):
                hits.append(name)
        mapping[inv] = sorted(hits)
    return mapping


@dataclass(frozen=True)
class CompletionFacts:
    """Light scrape of completions/completion-NNN.md files."""

    files: tuple[str, ...] = field(default_factory=tuple)
    statuses: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (filename, STATUS)
    suggestion_count: int = 0


def scrape_completions(dir_path: Path) -> CompletionFacts:
    """Best-effort scrape: read STATUS + count SUGGESTION lines.

    The Builder writes completion reports by hand for now (adds
    a generator), so we keep the parser lenient.
    """

    if not dir_path.is_dir():
        return CompletionFacts()
    files: list[str] = []
    statuses: list[tuple[str, str]] = []
    suggestion_count = 0
    status_re = re.compile(r"\*\*STATUS:\*\*\s*([A-Z]+)", re.IGNORECASE)
    for path in sorted(dir_path.rglob("*.md")):
        if not path.is_file():
            continue
        files.append(path.name)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = status_re.search(body)
        if match:
            statuses.append((path.name, match.group(1).upper()))
        # Count suggestion bullets — accept Vietnamese + English headers.
        in_suggestion = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                lowered = stripped.lower()
                in_suggestion = (
                    "suggestion" in lowered or "đề xuất" in lowered
                )
                continue
            if in_suggestion and stripped.startswith("- "):
                suggestion_count += 1
    return CompletionFacts(
        files=tuple(files),
        statuses=tuple(statuses),
        suggestion_count=suggestion_count,
    )


@dataclass(frozen=True)
class VerifyFacts:
    """Pre-render structure used by :func:`render_report`."""

    reports: tuple[GateReport, ...]
    tech_health: tuple[GateReport, ...]
    scenarios: tuple[GateReport, ...]
    other: tuple[GateReport, ...]
    failures: tuple[GateReport, ...]
    warnings: tuple[GateReport, ...]
    invariants: tuple[str, ...]
    invariant_coverage: dict[str, list[str]]
    completions: CompletionFacts
    overall_status: str  # READY | NEEDS_FIXES | MAJOR_ISSUES


def derive_overall_status(
    failures: int, warnings: int, uncovered_invariants: int,
) -> str:
    if failures > 0:
        return "MAJOR_ISSUES"
    if warnings > 0 or uncovered_invariants > 0:
        return "NEEDS_FIXES"
    return "READY"


def build_facts(
    reports: list[GateReport],
    *,
    invariants: list[str] | None = None,
    invariant_coverage: dict[str, list[str]] | None = None,
    completions: CompletionFacts | None = None,
) -> VerifyFacts:
    tech_health = tuple(r for r in reports if r.tool in TECH_HEALTH_TOOLS)
    scenarios = tuple(r for r in reports if r.tool in SCENARIO_TOOLS)
    used = {r.path for r in tech_health} | {r.path for r in scenarios}
    other = tuple(r for r in reports if r.path not in used)
    failures = tuple(r for r in reports if r.status == "FAIL")
    warnings = tuple(r for r in reports if r.status == "WARN")
    invariants = invariants or []
    invariant_coverage = invariant_coverage or {inv: [] for inv in invariants}
    uncovered = sum(1 for inv in invariants if not invariant_coverage.get(inv))
    return VerifyFacts(
        reports=tuple(reports),
        tech_health=tech_health,
        scenarios=scenarios,
        other=other,
        failures=failures,
        warnings=warnings,
        invariants=tuple(invariants),
        invariant_coverage=dict(invariant_coverage),
        completions=completions or CompletionFacts(),
        overall_status=derive_overall_status(
            len(failures), len(warnings), uncovered
        ),
    )


def _status_emoji(status: str) -> str:
    return {
        "PASS": "PASS",
        "WARN": "WARN",
        "FAIL": "FAIL",
        "READY": "READY",
        "NEEDS_FIXES": "NEEDS_FIXES",
        "MAJOR_ISSUES": "MAJOR_ISSUES",
    }.get(status, status)


def render_report(facts: VerifyFacts) -> str:
    lines: list[str] = [
        "# Verify Report — chu-thau → chu-nha ()",
        "",
        "_Emitted by `mql5-verify-report`. Read OVERALL STATUS first;_",
        "_critical issues drive the REFINE choice the Contractor presents._",
        "",
        "## OVERALL STATUS",
        "",
        f"**{_status_emoji(facts.overall_status)}**",
        "",
        f"- Gate reports parsed: {len(facts.reports)}",
        f"- Failures: {len(facts.failures)}",
        f"- Warnings: {len(facts.warnings)}",
        f"- Invariants tracked: {len(facts.invariants)}",
    ]
    if facts.invariants:
        uncovered = sum(
            1 for inv in facts.invariants if not facts.invariant_coverage.get(inv)
        )
        lines.append(f"- Invariants without TIP coverage: {uncovered}")
    lines += [
        "",
        "## REQ COVERAGE — blueprint invariants ↔ TIP files",
    ]
    if not facts.invariants:
        lines.append(
            "_No blueprint supplied (or no `## Invariants` section). "
            "Pass `--blueprint step-4-blueprint.md` for invariant ↔ TIP "
            "matching._"
        )
    else:
        lines.append("")
        lines.append("| # | Invariant | TIP files | Status |")
        lines.append("|---|---|---|---|")
        for idx, inv in enumerate(facts.invariants, start=1):
            tips = facts.invariant_coverage.get(inv) or []
            tip_text = ", ".join(tips) if tips else "_(no TIP match)_"
            status = "PASS" if tips else "FAIL"
            inv_short = inv if len(inv) <= 80 else inv[:77] + "…"
            lines.append(f"| {idx} | {inv_short} | {tip_text} | {status} |")

    lines += [
        "",
        "## SCENARIO RESULTS — backtest, walk-forward, Monte Carlo",
    ]
    if not facts.scenarios:
        lines.append(
            "_No scenario gate reports parsed. Ask the Builder to run_"
            "_`mql5-backtest`, `mql5-walkforward`, `mql5-monte-carlo` and_"
            "_persist their envelopes via `--gate-report <path>`._"
        )
    else:
        lines.append("")
        lines.append("| Tool | Status | Summary |")
        lines.append("|---|---|---|")
        for r in facts.scenarios:
            summary = r.summary if len(r.summary) <= 120 else r.summary[:117] + "…"
            lines.append(f"| `{r.tool}` | {r.status} | {summary} |")

    lines += [
        "",
        "## TECH HEALTH — lint, method-hiding, trader-check, permission",
    ]
    if not facts.tech_health:
        lines.append(
            "_No tech-health gate reports parsed. Ask the Builder to run_"
            "_`mql5-lint`, `mql5-method-hiding-check`, `mql5-trader-check`,_"
            "_`mql5-permission` with `--gate-report <path>`._"
        )
    else:
        lines.append("")
        lines.append("| Tool | Status | Summary |")
        lines.append("|---|---|---|")
        for r in facts.tech_health:
            summary = r.summary if len(r.summary) <= 120 else r.summary[:117] + "…"
            lines.append(f"| `{r.tool}` | {r.status} | {summary} |")

    if facts.other:
        lines += [
            "",
            "## OTHER GATE REPORTS",
            "",
            "| Tool | Status | Summary |",
            "|---|---|---|",
        ]
        for r in facts.other:
            summary = r.summary if len(r.summary) <= 120 else r.summary[:117] + "…"
            lines.append(f"| `{r.tool}` | {r.status} | {summary} |")

    lines += [
        "",
        "## CRITICAL ISSUES — every FAIL surfaced",
    ]
    if not facts.failures:
        lines.append("_None._")
    else:
        for r in facts.failures:
            lines.append(f"- `{r.tool}` ({r.path.name}): {r.summary}")

    if facts.completions.files:
        # Tally STATUS counts for the decisions table.
        status_counts: Counter[str] = Counter(s for _, s in facts.completions.statuses)
        lines += [
            "",
            "## DECISIONS NEEDED — Completion Report rollup",
            "",
            f"- Completion files parsed: {len(facts.completions.files)}",
            "- STATUS breakdown: " + ", ".join(
                f"{k}={v}" for k, v in sorted(status_counts.items())
            ) if status_counts else "- STATUS breakdown: (no STATUS lines found)",
            f"- Suggestions awaiting Contractor triage: "
            f"{facts.completions.suggestion_count}",
        ]

    lines += [
        "",
        "## REFINE OPTIONS — Contractor presents to Homeowner",
        "",
    ]
    if facts.overall_status == "READY":
        lines += [
            "- [A] **Ship as-is** — every gate PASS; the deliverables match",
            "      the contract. Proceed to Step 8 REFINE / packaging.",
            "- [B] Reopen Step 3 (VISION) only if the Homeowner wants new",
            "      scope; do NOT block on style polish.",
            "- [C] Custom (Homeowner declares).",
        ]
    elif facts.overall_status == "NEEDS_FIXES":
        lines += [
            "- [A] **Ship as-is** — accept the warnings; risk: each WARN",
            "      may become a Level-3 escalation later.",
            "- [B] **Fix warnings only** — re-run the failing tool(s)",
            "      after the Builder addresses each WARN.",
            "- [C] **Fix warnings + tighten coverage** — also generate a",
            "      refine TIP for every uncovered invariant.",
            "- [D] Custom (Homeowner declares).",
        ]
    else:  # MAJOR_ISSUES
        lines += [
            "- [A] **DO NOT SHIP** (default recommendation) — return the",
            "      build to the Builder with a refine TIP per FAIL.",
            "- [B] Reopen Step 3 (VISION) if the FAIL is architectural.",
            "- [C] Reopen Step 4 (BLUEPRINT) if the FAIL violates an",
            "      invariant the Contractor missed.",
            "- [D] Custom (Homeowner declares).",
        ]
    lines += [
        "",
        f"_Tool: `{TOOL}` — deterministic; same inputs ⇒ same report._",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument(
        "--gate-reports",
        type=Path,
        required=True,
        help="Directory containing gate-report-*.json envelopes "
        "(schema). Recursively scanned.",
    )
    parser.add_argument(
        "--blueprint",
        type=Path,
        default=None,
        help="Path to step-4-blueprint.md — when supplied, the report "
        "includes invariant ↔ TIP coverage.",
    )
    parser.add_argument(
        "--tip-dir",
        type=Path,
        default=None,
        help="Directory containing tasks/TIP-NNN.md files "
        "(will emit these; for now use --tip-dir <step-5-tip.md "
        "parent> or omit).",
    )
    parser.add_argument(
        "--completion-dir",
        type=Path,
        default=None,
        help="Directory containing completion-NNN.md files (one per TIP "
        "delivered by the Builder).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the report markdown to this path (default: stdout).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite --out if it already exists.",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.gate_reports.is_dir():
        env = Envelope(
            tool=TOOL,
            ok=False,
            exit_code=2,
            summary=f"--gate-reports directory not found: {args.gate_reports}",
            data={"gate_reports": str(args.gate_reports)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(
                f"error: directory not found: {args.gate_reports}\n"
            )
        return 2

    reports = load_gate_reports(args.gate_reports)

    invariants: list[str] = []
    invariant_coverage: dict[str, list[str]] = {}
    if args.blueprint is not None:
        if not args.blueprint.is_file():
            env = Envelope(
                tool=TOOL,
                ok=False,
                exit_code=2,
                summary=f"blueprint not found: {args.blueprint}",
                data={"blueprint": str(args.blueprint)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(
                    f"error: file not found: {args.blueprint}\n"
                )
            return 2
        body = args.blueprint.read_text(encoding="utf-8")
        invariants = extract_invariants(body)
        if args.tip_dir is not None:
            invariant_coverage = map_invariants_to_tips(
                invariants, args.tip_dir
            )
        else:
            invariant_coverage = {inv: [] for inv in invariants}

    completions = CompletionFacts()
    if args.completion_dir is not None:
        completions = scrape_completions(args.completion_dir)

    facts = build_facts(
        reports,
        invariants=invariants,
        invariant_coverage=invariant_coverage,
        completions=completions,
    )
    rendered = render_report(facts)

    if args.out is not None:
        if args.out.exists() and not args.force:
            env = Envelope(
                tool=TOOL,
                ok=False,
                exit_code=2,
                summary=f"refusing to overwrite {args.out} (use --force)",
                data={"out": str(args.out)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(f"error: {args.out} exists (use --force)\n")
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")

    if not args.emit_json:
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            sys.stderr.write(f"wrote {args.out}\n")

    # The verify report is a *summary*: it should succeed even when the
    # underlying build is in MAJOR_ISSUES. The envelope ok flag therefore
    # tracks "did we render a report?", and the OVERALL STATUS is in
    # data.overall_status for downstream consumers.
    evidence = [str(args.gate_reports)]
    if args.blueprint is not None:
        evidence.append(str(args.blueprint))
    if args.tip_dir is not None:
        evidence.append(str(args.tip_dir))
    if args.completion_dir is not None:
        evidence.append(str(args.completion_dir))

    env = Envelope(
        tool=TOOL,
        ok=True,
        exit_code=0,
        summary=(
            f"OVERALL STATUS={facts.overall_status}; "
            f"{len(facts.reports)} gate report(s), "
            f"{len(facts.failures)} fail / {len(facts.warnings)} warn; "
            f"{len(facts.invariants)} invariant(s) tracked"
        ),
        data={
            "overall_status": facts.overall_status,
            "reports": [
                {
                    "tool": r.tool,
                    "status": r.status,
                    "summary": r.summary,
                    "path": str(r.path),
                }
                for r in facts.reports
            ],
            "failures": [r.tool for r in facts.failures],
            "warnings": [r.tool for r in facts.warnings],
            "invariants": list(facts.invariants),
            "invariant_coverage": {
                inv: tips for inv, tips in facts.invariant_coverage.items()
            },
            "completion_files": list(facts.completions.files),
            "completion_statuses": [
                {"file": name, "status": status}
                for name, status in facts.completions.statuses
            ],
            "completion_suggestion_count": facts.completions.suggestion_count,
            "out": str(args.out) if args.out else None,
        },
        evidence=evidence,
    )
    maybe_emit(args, env)
    return 0


__all__ = [
    "CompletionFacts",
    "GateReport",
    "SCENARIO_TOOLS",
    "TECH_HEALTH_TOOLS",
    "VerifyFacts",
    "build_facts",
    "derive_overall_status",
    "extract_invariants",
    "load_gate_reports",
    "main",
    "map_invariants_to_tips",
    "render_report",
    "scrape_completions",
]


if __name__ == "__main__":
    raise SystemExit(main())
