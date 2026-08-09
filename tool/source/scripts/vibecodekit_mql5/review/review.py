"""mql5-review — unified review wrapper.

Replaces the original ``mql5-review`` + four siblings
(``mql5-eng-review``, ``mql5-ceo-review``, ``mql5-cso``,
``mql5-investigate``) with a single entry-point that can render either:

* A **single-persona** review (legacy default) using ``--persona``,
  ``--step``, ``--mode``. Backwards-compatible with the pre-CLI.

* A **named lens** — a preset bundle of personas + steps used by the
  four sibling CLIs:

      eng         broker-engineer + devops          steps: build, verify
      ceo         trader + strategy-architect       steps: vision, refine
      cso         risk-auditor                      steps: rri, verify
      investigate perf-analyst + strategy-architect steps: scan, rri
                  (adds a Hypotheses worksheet)

The four legacy console scripts now live as thin aliases that call
``review.main(['--lens', '<name>', ...])``; the body of each lens lives
here so the help, docs, and JSON envelope stay in one place. This
mirrors the ``--json`` consolidation: agents discover one tool,
one --help, and the alias just forwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from ..rri.personas import PERSONA_IDS, filter_for_mode, load_persona
from ..rri.step_workflow import STEPS, render_template


@dataclass(frozen=True)
class Lens:
    """A preset combination of personas and steps."""

    name: str
    title: str
    personas: tuple[str, ...]
    steps: tuple[str, ...]
    default_output: str
    extra_section: str = ""  # appended verbatim at the end (used by `investigate`).


LENSES: dict[str, Lens] = {
    "eng": Lens(
        name="eng",
        title="Engineering review",
        personas=("broker-engineer", "devops"),
        steps=("build", "verify"),
        default_output="eng-review.md",
    ),
    "ceo": Lens(
        name="ceo",
        title="CEO review",
        personas=("trader", "strategy-architect"),
        steps=("vision", "refine"),
        default_output="ceo-review.md",
    ),
    "cso": Lens(
        name="cso",
        title="Chief Safety Officer review",
        personas=("risk-auditor",),
        steps=("rri", "verify"),
        default_output="cso-review.md",
    ),
    "investigate": Lens(
        name="investigate",
        title="Investigation review",
        personas=("perf-analyst", "strategy-architect"),
        steps=("scan", "rri"),
        default_output="investigate.md",
        extra_section=(
            "## Hypotheses\n\n"
            "- [ ] Hypothesis 1: ...\n"
            "- [ ] Hypothesis 2: ...\n"
        ),
    ),
}

LENS_IDS: tuple[str, ...] = tuple(LENSES)


def render_single(persona_id: str, step: str, mode: str) -> str:
    """Render the legacy single-persona view (one persona × one step)."""

    persona = load_persona(persona_id)
    questions = filter_for_mode(persona, mode)
    header = (
        f"# Review — persona: {persona.persona} / step: {step} / mode: {mode}\n\n"
        f"_{persona.description}_\n\n"
        "## Questions\n\n"
    )
    q_lines = "\n".join(
        f"- [ ] **{q.id}** ({q.priority}) — {q.text}" for q in questions
    )
    body = render_template(step)
    return header + q_lines + "\n\n## Step template\n\n" + body


def render_lens(
    lens: Lens, mode: str, steps: tuple[str, ...] | None = None,
) -> str:
    """Render a multi-persona lens (preset).

    ``steps`` lets the in-process MCP bridge (``review.eng`` /
    ``review.cso`` / ``review.ceo`` / ``review.investigate``) override
    the default step bundle without changing the persona set. Pass
    ``None`` to use the lens's canonical steps.
    """

    effective_steps = lens.steps if steps is None else tuple(steps)

    out: list[str] = [f"# {lens.title}", ""]
    if lens.name == "investigate":
        out.append("_Goal: capture hypotheses + the evidence each needs._")
        out.append("")

    for pid in lens.personas:
        persona = load_persona(pid)
        out.append(f"## Persona: {persona.persona}")
        out.append(f"_{persona.description}_\n")
        for q in filter_for_mode(persona, mode):
            out.append(f"- [ ] **{q.id}** ({q.priority}) — {q.text}")
        out.append("")

    out.append("## Step templates\n")
    for step in effective_steps:
        out.append(f"### {step}\n")
        out.append(render_template(step))
        out.append("")

    if lens.extra_section:
        out.append(lens.extra_section)
    return "\n".join(out)


# Public so the legacy aliases (eng_review/ceo_review/cso/investigate) can
# call into the same code-path without re-implementing argparse.
def run_lens(lens_name: str, mode: str, output: Path | None) -> int:
    """Execute a lens by name and emit the JSON envelope used by every alias."""

    if lens_name not in LENSES:
        print(f"unknown lens: {lens_name!r}", file=sys.stderr, flush=True)
        return 2
    lens = LENSES[lens_name]
    out_path = Path(output) if output is not None else Path(lens.default_output)
    body = render_lens(lens, mode)
    out_path.write_text(body, encoding="utf-8")
    print(json.dumps({
        "lens": lens.name,
        "personas": list(lens.personas),
        "steps": list(lens.steps),
        "mode": mode,
        "output": str(out_path),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mql5-review",
        description=__doc__.splitlines()[0],
    )
    ap.add_argument(
        "--lens", choices=LENS_IDS, default=None,
        help="Multi-persona preset. When set, overrides --persona/--step "
             "and renders the named bundle (replaces the legacy "
             "mql5-eng-review / mql5-ceo-review / mql5-cso / "
             "mql5-investigate console scripts).",
    )
    ap.add_argument(
        "--persona", choices=PERSONA_IDS, default="trader",
        help="Single persona to render (ignored when --lens is set).",
    )
    ap.add_argument(
        "--step", choices=STEPS, default="verify",
        help="Step template to attach (ignored when --lens is set).",
    )
    ap.add_argument(
        "--mode", choices=("personal", "team", "enterprise"), default="personal",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Output markdown path. Defaults to review.md (single) or "
             "<lens>-review.md (lens).",
    )
    args = ap.parse_args(argv)

    if args.lens is not None:
        return run_lens(args.lens, args.mode, args.output)

    # Legacy single-persona path.
    output = args.output if args.output is not None else Path("review.md")
    body = render_single(args.persona, args.step, args.mode)
    output.write_text(body, encoding="utf-8")
    print(json.dumps({
        "persona": args.persona,
        "step": args.step,
        "mode": args.mode,
        "output": str(output),
    }, indent=2))
    return 0


# Back-compat with the pre-``render(persona, step, mode)`` import path
# used by the bundled step-workflow tests and any external
# scripts that import ``vibecodekit_mql5.review.review.render``.
render = render_single


if __name__ == "__main__":
    raise SystemExit(main())
