"""mql5-vision-gen — auto-emit ``step-3-vision.md`` from ``step-2-rri.md``.

Parses the Step-2 RRI artefact for two structured patterns:

1. ``## Constraints`` — lines starting with ``- `` after that header are
   treated as downstream constraints that must appear in the Vision
   scope.
2. ``- [x] <persona-id>::<question-id>`` — a "checked" RRI question.
   The generator collapses these into the active persona set so the
   Vision exit criterion ("Scope is acceptable to all RRI personas
   active in the chosen mode") can be checked mechanically.

The output is a self-contained ``step-3-vision.md`` skeleton with three
filled blocks (Scope, Constraints, Active Personas) and two ``TODO``
blocks (Timeline, Risk Register) that the operator still has to refine.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)
from ..rri import step_workflow as sw
from ..rri.personas import PERSONA_IDS

TOOL = "mql5-vision-gen"

# Match `- [x] persona-id::q-id` (or `[X]` — Markdown task-list syntax is
# case-insensitive in every major renderer) and capture both halves.
_CHECKED_Q = re.compile(
    r"^\s*-\s*\[[xX]\]\s+([A-Za-z][A-Za-z0-9_\-]+)\s*::\s*([A-Za-z0-9_\-]+)\s*(?:[—–\-:]\s*(.*))?$",
)


@dataclass(frozen=True)
class RRIParse:
    """Structured view of a Step-2 RRI artefact."""

    constraints: tuple[str, ...]
    active_personas: tuple[str, ...]
    checked_questions: int
    mode: str


def _extract_section_lines(body: str, header: str) -> list[str]:
    """Return non-empty list items under a ``## <header>`` section."""

    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == f"## {header}"
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            out.append(stripped[2:].strip())
    return out


def _detect_mode(body: str) -> str:
    r"""Guess the audit mode from the Step-2 header line.

    The Step-2 template has a line ``- Audit mode: \`{{mode}}\``` so a
    rendered file will read ``- Audit mode: \`enterprise\``` (or similar).
    Defaults to ``personal`` if nothing is matched.
    """

    match = re.search(r"Audit mode:\s*`([a-z]+)`", body)
    if match:
        mode = match.group(1)
        if mode in sw.MODE_REQUIRED_STEPS:
            return mode
    return "personal"


def parse_rri(body: str) -> RRIParse:
    """Parse the Step-2 RRI markdown into structured facts."""

    constraints_raw = _extract_section_lines(body, "Constraints")
    # Keep only non-TODO constraints so the generator can later detect
    # whether the parent step really filled anything.
    constraints = tuple(
        c for c in constraints_raw
        if c.lower() not in {"todo", "(todo)", "tbd", "(tbd)"}
    )

    personas: set[str] = set()
    checked = 0
    for line in body.splitlines():
        m = _CHECKED_Q.match(line)
        if not m:
            continue
        persona = m.group(1)
        if persona in PERSONA_IDS:
            personas.add(persona)
            checked += 1
    mode = _detect_mode(body)
    return RRIParse(
        constraints=constraints,
        active_personas=tuple(sorted(personas)),
        checked_questions=checked,
        mode=mode,
    )


def render_vision(parsed: RRIParse, *, source: Path | None = None) -> str:
    """Render a step-3-vision.md skeleton from an :class:`RRIParse`."""

    lines: list[str] = [
        "# Step 3 / 8 — VISION (Contractor proposal)",
        "",
        "Translate the RRI matrix into a scope + cost + timeline + risk register.",
        "",
        "## Inputs",
    ]
    if source is not None:
        lines.append(f"- `{source.name}` (mode: `{parsed.mode}`)")
    else:
        lines.append(f"- `step-2-rri.md` (mode: `{parsed.mode}`)")
    lines += [
        "",
        "## Active personas",
    ]
    if parsed.active_personas:
        lines += [f"- {pid}" for pid in parsed.active_personas]
    else:
        lines.append("- TODO: no `- [x] persona::q-id` lines found in Step-2 — fill manually")
    lines += [
        "",
        "## Scope",
        "_Generated from Step-2 constraints. Refine wording per persona review._",
        "",
    ]
    if parsed.constraints:
        lines += [f"- {c}" for c in parsed.constraints]
    else:
        lines.append("- TODO: no `## Constraints` section in Step-2 — fill manually")
    lines += [
        "",
        "## Timeline",
        "- TODO: estimate effort by file (S/M/L)",
        "",
        "## Risk register",
        "- TODO: enumerate risks; assign owner + mitigation",
        "",
        "## Exit criteria",
        f"- Scope is acceptable to **{len(parsed.active_personas)} active persona(s)**",
        f"  ({', '.join(parsed.active_personas) if parsed.active_personas else 'none detected'})",
        "- Risks above the personal-mode acceptance bar have explicit mitigations",
        "",
        f"> Generated by `{TOOL}` from {parsed.checked_questions} checked RRI question(s)."
        f" Activities below MUST be re-ticked after manual refinement.",
        "",
        "## Activities",
        "- [ ] Define the minimum viable change set (files in, files out)",
        "- [ ] Estimate effort by file (S/M/L)",
        "- [ ] Enumerate risks; assign owner + mitigation",
        "",
        "> Sentinel: `touch .rri-state/vision.done` (only after every activity is ticked).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument(
        "rri_file", type=Path,
        help="Path to the Step-2 RRI artefact (step-2-rri.md).",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Write the rendered VISION to this path instead of stdout.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite --out if it already exists (otherwise refuse).",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.rri_file.is_file():
        env = Envelope(
            tool=TOOL, ok=False, exit_code=2,
            summary=f"RRI input not found: {args.rri_file}",
            data={"input": str(args.rri_file)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: file not found: {args.rri_file}\n")
        return 2

    body = args.rri_file.read_text(encoding="utf-8")
    parsed = parse_rri(body)
    rendered = render_vision(parsed, source=args.rri_file)

    if args.out is not None:
        if args.out.exists() and not args.force:
            env = Envelope(
                tool=TOOL, ok=False, exit_code=2,
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

    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(
            f"rendered VISION from {parsed.checked_questions} RRI question(s) "
            f"+ {len(parsed.constraints)} constraint(s) "
            f"({len(parsed.active_personas)} active persona)"
        ),
        data={
            "mode": parsed.mode,
            "active_personas": list(parsed.active_personas),
            "constraints": list(parsed.constraints),
            "checked_questions": parsed.checked_questions,
            "out": str(args.out) if args.out else None,
        },
        evidence=[str(args.rri_file)],
    )
    maybe_emit(args, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
