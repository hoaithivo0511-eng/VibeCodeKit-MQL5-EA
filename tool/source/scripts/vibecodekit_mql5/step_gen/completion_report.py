"""Per-TIP Completion Report emitter.

The Builder (``tho-thi-cong``) runs ``mql5-completion-report`` once
they believe a TIP is done. The CLI takes:

* the per-TIP markdown file produced by ``mql5-task-graph-gen``
  (``tasks/TIP-NNN.md``) for the title / dependency / invariant
  metadata, and
* a directory of ``gate-report-*.json`` envelopes the Builder
  produced while executing the TIP (lint, trader-check, backtest,
  …).

It emits ``completion-NNN.md`` with a fixed shape so the
Contractor's ``mql5-verify-report`` can roll several completions up
into a single Verify Report:

* ``# Completion Report — TIP-NNN``
* ``STATUS:`` (READY / IN_PROGRESS / BLOCKED)
* ``## Files Changed`` — optional, populated from ``--file`` flags
  (operator passes the paths they modified)
* ``## Tests Added`` — optional, populated from ``--test`` flags
* ``## Issues Encountered`` — optional, populated from ``--issue``
  flags (one per blocker the Builder noted)
* ``## Gate Reports Referenced`` — auto-generated table of every
  envelope under ``--gate-reports``

Status derivation is deterministic:

* Any envelope with ``status=FAIL`` (or ``ok=False`` with no matrix
  override) and no ``--issue`` mitigation → ``BLOCKED``.
* Any ``--issue`` provided and at least one FAIL → ``BLOCKED``.
* Any WARN with no FAIL → ``IN_PROGRESS``.
* All PASS → ``READY``.

The CLI deliberately does *not* enforce the TIP file's ``status:``
field — that update is the Builder's manual decision after reading
the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)

TOOL = "mql5-completion-report"

_TIP_ID = re.compile(r"^tip_id:\s*(TIP-\d{3})\s*$", re.MULTILINE)
_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
_DEPENDS = re.compile(r"^depends_on:\s*\[(.*?)\]\s*$", re.MULTILINE)
_INV_BLOCK = re.compile(
    r"^invariant_refs:\s*\n((?:  -.*\n)+)", re.MULTILINE
)
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class TIPMeta:
    """Frontmatter parsed from a ``tasks/TIP-NNN.md`` file."""

    tip_id: str
    title: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    invariant_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompletionEvidence:
    """One row of the rendered ``## Gate Reports Referenced`` table."""

    path: Path
    tool: str
    status: str  # PASS / WARN / FAIL
    summary: str


@dataclass(frozen=True)
class CompletionFacts:
    """Bundle of everything the renderer needs."""

    tip: TIPMeta
    files: tuple[str, ...]
    tests: tuple[str, ...]
    issues: tuple[str, ...]
    evidence: tuple[CompletionEvidence, ...]
    status: str  # READY / IN_PROGRESS / BLOCKED
    tip_sha256: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_tip(path: Path) -> TIPMeta:
    """Parse the YAML-style frontmatter of a ``tasks/TIP-NNN.md`` file.

    We don't depend on PyYAML for this — the frontmatter is fixed
    shape (the ``mql5-task-graph-gen`` is the only
    legitimate emitter). Raises ``ValueError`` if the required
    ``tip_id`` / ``title`` fields are missing.
    """

    body = path.read_text(encoding="utf-8")
    fm = _FRONTMATTER.search(body)
    fm_body = fm.group(1) if fm else body  # tolerate missing fence

    tip_match = _TIP_ID.search(fm_body)
    title_match = _TITLE.search(fm_body)
    if tip_match is None or title_match is None:
        raise ValueError(
            f"{path}: TIP frontmatter must declare `tip_id:` and "
            "`title:` fields (`mql5-task-graph-gen` output)"
        )
    tip_id = tip_match.group(1)
    title = title_match.group(1).strip()

    depends_on: tuple[str, ...] = ()
    dep_match = _DEPENDS.search(fm_body)
    if dep_match is not None:
        raw = dep_match.group(1).strip()
        if raw:
            depends_on = tuple(part.strip() for part in raw.split(",") if part.strip())

    invariants: list[str] = []
    inv_match = _INV_BLOCK.search(fm_body + "\n")
    if inv_match is not None:
        for line in inv_match.group(1).splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            value = stripped[2:].strip()
            if value in {"[]", "()"}:
                continue
            if (value.startswith("'") and value.endswith("'")) or (
                value.startswith('"') and value.endswith('"')
            ):
                value = value[1:-1]
            if value:
                invariants.append(value)

    return TIPMeta(
        tip_id=tip_id,
        title=title,
        depends_on=depends_on,
        invariant_refs=tuple(invariants),
    )


def _derive_status_per_envelope(payload: dict) -> str:
    """Map a envelope to PASS / WARN / FAIL (kept local so this
    module never imports verify_report).
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


def load_evidence(report_dir: Path) -> list[CompletionEvidence]:
    """Walk ``report_dir`` and turn every envelope into a row."""

    if not report_dir.is_dir():
        return []
    out: list[CompletionEvidence] = []
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
            CompletionEvidence(
                path=path,
                tool=tool,
                status=_derive_status_per_envelope(payload),
                summary=str(payload.get("summary", "")).strip(),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Status logic
# ---------------------------------------------------------------------------


def derive_status(
    evidence: tuple[CompletionEvidence, ...],
    issues: tuple[str, ...],
) -> str:
    """Bucket the TIP into READY / IN_PROGRESS / BLOCKED.

    Deterministic — no LLM, no thresholds. The Builder still has to
    flip ``status:`` in the TIP file manually after reading the
    report.
    """

    has_fail = any(e.status == "FAIL" for e in evidence)
    has_warn = any(e.status == "WARN" for e in evidence)
    if has_fail:
        return "BLOCKED"
    if issues:
        return "BLOCKED"
    if has_warn:
        return "IN_PROGRESS"
    if not evidence:
        return "IN_PROGRESS"
    return "READY"


def build_facts(
    tip_path: Path,
    evidence_dir: Path | None,
    *,
    files: tuple[str, ...],
    tests: tuple[str, ...],
    issues: tuple[str, ...],
) -> CompletionFacts:
    tip = parse_tip(tip_path)
    tip_body = tip_path.read_text(encoding="utf-8")
    tip_sha = hashlib.sha256(tip_body.encode("utf-8")).hexdigest()
    evidence = tuple(load_evidence(evidence_dir)) if evidence_dir else ()
    status = derive_status(evidence, issues)
    return CompletionFacts(
        tip=tip,
        files=files,
        tests=tests,
        issues=issues,
        evidence=evidence,
        status=status,
        tip_sha256=tip_sha,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_completion(facts: CompletionFacts, *, tip_path: Path) -> str:
    """Render the ``completion-NNN.md`` body."""

    lines: list[str] = [
        f"# Completion Report — {facts.tip.tip_id}",
        "",
        f"**TITLE:** {facts.tip.title}",
        f"**STATUS:** {facts.status}",
        "**ACTOR:** tho-thi-cong",
        f"**TIP source:** `{tip_path.name}` "
        f"(sha256 prefix `{facts.tip_sha256[:12]}…`)",
        "",
        "## Files Changed",
        "",
    ]
    if facts.files:
        for entry in facts.files:
            lines.append(f"- `{entry}`")
    else:
        lines.append("_None declared. Pass `--file <path>` once per modified file._")

    lines += ["", "## Tests Added", ""]
    if facts.tests:
        for entry in facts.tests:
            lines.append(f"- `{entry}`")
    else:
        lines.append("_None declared. Pass `--test <path>` once per new test._")

    lines += ["", "## Issues Encountered", ""]
    if facts.issues:
        for entry in facts.issues:
            lines.append(f"- {entry}")
    else:
        lines.append(
            "_None declared. Pass `--issue \"<text>\"` once per blocker._"
        )

    lines += ["", "## Gate Reports Referenced", ""]
    if facts.evidence:
        lines.append("| Tool | Status | Summary | Path |")
        lines.append("|---|---|---|---|")
        for ev in facts.evidence:
            summary = ev.summary.replace("|", "\\|") or "_(no summary)_"
            lines.append(
                f"| `{ev.tool}` | `{ev.status}` | {summary} | `{ev.path}` |"
            )
    else:
        lines.append("_No gate reports loaded. Re-run with `--gate-reports <dir>`._")

    lines += ["", "## Invariants Referenced", ""]
    if facts.tip.invariant_refs:
        for inv in facts.tip.invariant_refs:
            lines.append(f"- {inv}")
    else:
        lines.append("_TIP frontmatter declared no invariant refs._")

    lines += [
        "",
        "## Next steps",
        "",
        (
            "- Builder: if `STATUS: READY`, update the TIP frontmatter "
            "`status:` to `DONE` and hand the report to the Contractor "
            "for inclusion in `mql5-verify-report`."
        ),
        (
            "- Builder: if `STATUS: BLOCKED`, run `mql5-escalation "
            "--from tho-thi-cong --to chu-thau --level 2 "
            "--reason \"<one-line>\"` () so the blocker is "
            "audited."
        ),
        "",
        f"_Tool: `{TOOL}` — emitted from `{tip_path.name}` "
        f"(sha256 prefix `{facts.tip_sha256[:12]}…`)._",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument(
        "--tip",
        type=Path,
        required=True,
        help="Path to the per-TIP markdown file under tasks/.",
    )
    parser.add_argument(
        "--gate-reports",
        type=Path,
        default=None,
        help="Optional directory of gate-report-*.json envelopes "
        "to aggregate into the Gate Reports Referenced table.",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="Path of a file changed for this TIP. Repeat for each path.",
    )
    parser.add_argument(
        "--test",
        dest="tests",
        action="append",
        default=[],
        help="Path of a test added/updated for this TIP. Repeat for each.",
    )
    parser.add_argument(
        "--issue",
        dest="issues",
        action="append",
        default=[],
        help="One-line description of an issue encountered. Repeat per issue.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the rendered completion report to this path "
        "(default: stdout).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite --out if it already exists.",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.tip.is_file():
        env = Envelope(
            tool=TOOL,
            ok=False,
            exit_code=2,
            summary=f"TIP file not found: {args.tip}",
            data={"tip": str(args.tip)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: file not found: {args.tip}\n")
        return 2

    if args.gate_reports is not None and not args.gate_reports.is_dir():
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

    try:
        facts = build_facts(
            args.tip,
            args.gate_reports,
            files=tuple(args.files),
            tests=tuple(args.tests),
            issues=tuple(args.issues),
        )
    except ValueError as exc:
        env = Envelope(
            tool=TOOL,
            ok=False,
            exit_code=2,
            summary=str(exc),
            data={"tip": str(args.tip)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: {exc}\n")
        return 2

    rendered = render_completion(facts, tip_path=args.tip)

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
                sys.stderr.write(
                    f"error: {args.out} exists (use --force)\n"
                )
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")

    if not args.emit_json:
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            sys.stderr.write(f"wrote {args.out}\n")

    evidence_payload = [
        {
            "path": str(ev.path),
            "tool": ev.tool,
            "status": ev.status,
            "summary": ev.summary,
        }
        for ev in facts.evidence
    ]

    env = Envelope(
        tool=TOOL,
        ok=facts.status != "BLOCKED",
        exit_code=0 if facts.status != "BLOCKED" else 1,
        summary=(
            f"{facts.tip.tip_id}: {facts.status} "
            f"({len(facts.evidence)} gate report(s), "
            f"{len(facts.files)} file(s), "
            f"{len(facts.tests)} test(s), "
            f"{len(facts.issues)} issue(s))"
        ),
        data={
            "tip_id": facts.tip.tip_id,
            "title": facts.tip.title,
            "status": facts.status,
            "depends_on": list(facts.tip.depends_on),
            "invariant_refs": list(facts.tip.invariant_refs),
            "files": list(facts.files),
            "tests": list(facts.tests),
            "issues": list(facts.issues),
            "evidence": evidence_payload,
            "tip_sha256_prefix": facts.tip_sha256[:12],
            "out": str(args.out) if args.out else None,
        },
        evidence=[str(args.tip)]
        + ([str(args.gate_reports)] if args.gate_reports else []),
    )
    maybe_emit(args, env)
    return env.exit_code


__all__ = [
    "CompletionEvidence",
    "CompletionFacts",
    "TIPMeta",
    "build_facts",
    "derive_status",
    "load_evidence",
    "main",
    "parse_tip",
    "render_completion",
]


if __name__ == "__main__":
    raise SystemExit(main())
