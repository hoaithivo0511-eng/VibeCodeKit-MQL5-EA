"""mql5-step-workflow — 8-step methodology state machine.

The 8 steps (SCAN → RRI → VISION → BLUEPRINT → TIP → BUILD → VERIFY → REFINE)
form a directed sequence with a single permitted regression edge from REFINE
back to RRI when refine-envelope analysis demands re-scoping. This module
encodes the transition rules + the markdown template paths so other
permission/review tools can ask "has step N been completed?".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

STEPS: tuple[str, ...] = (
    "scan",
    "rri",
    "vision",
    "blueprint",
    "tip",
    "build",
    "verify",
    "refine",
)

STEP_NUMBERS: dict[str, int] = {name: idx + 1 for idx, name in enumerate(STEPS)}

# Modes that require each step. Personal mode skips the heavier audit/design
# steps; team adds RRI/blueprint; enterprise mandates all 8.
MODE_REQUIRED_STEPS: dict[str, tuple[str, ...]] = {
    "personal": ("scan", "build", "verify"),
    "team": ("scan", "rri", "vision", "build", "verify", "refine"),
    "enterprise": STEPS,
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_DIR = _REPO_ROOT / "docs" / "rri-templates"


@dataclass(frozen=True)
class StepDescriptor:
    name: str
    number: int
    template: Path


def descriptor(name: str) -> StepDescriptor:
    if name not in STEP_NUMBERS:
        raise ValueError(f"unknown step: {name!r}")
    n = STEP_NUMBERS[name]
    return StepDescriptor(name=name, number=n, template=_TEMPLATE_DIR / f"step-{n}-{name}.md.tmpl")


def is_valid_transition(current: str, target: str) -> bool:
    """Return True if going from ``current`` to ``target`` is legal."""
    if current not in STEP_NUMBERS or target not in STEP_NUMBERS:
        return False
    cur = STEP_NUMBERS[current]
    tgt = STEP_NUMBERS[target]
    if tgt == cur + 1:  # normal forward move
        return True
    if current == "refine" and target == "rri":  # the only legal backward jump
        return True
    return False


def required_steps(mode: str) -> tuple[str, ...]:
    if mode not in MODE_REQUIRED_STEPS:
        raise ValueError(f"unknown mode: {mode!r}")
    return MODE_REQUIRED_STEPS[mode]


def completed_steps(state_dir: Path) -> tuple[str, ...]:
    """A step counts as completed when ``state_dir/<step>.done`` exists."""
    return tuple(name for name in STEPS if (state_dir / f"{name}.done").exists())


def is_workflow_complete(state_dir: Path, mode: str) -> bool:
    """All steps required by ``mode`` have a ``.done`` sentinel in ``state_dir``."""
    done = set(completed_steps(state_dir))
    return all(s in done for s in required_steps(mode))


def render_template(step: str, substitutions: dict[str, str] | None = None) -> str:
    """Return the markdown template body with optional placeholder substitution."""
    body = descriptor(step).template.read_text(encoding="utf-8")
    if substitutions:
        for key, value in substitutions.items():
            body = body.replace("{{" + key + "}}", value)
    return body


def iter_templates() -> Iterable[Path]:
    for name in STEPS:
        yield descriptor(name).template


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="mql5-step-workflow")
    ap.add_argument("--mode", choices=tuple(MODE_REQUIRED_STEPS), default="personal")
    ap.add_argument("--state-dir", default=".rri-state",
                    help="directory containing <step>.done sentinels")
    ap.add_argument("--show", choices=STEPS, default=None,
                    help="print the markdown template for the given step")
    args = ap.parse_args()

    if args.show:
        print(render_template(args.show))
        return 0

    state = Path(args.state_dir)
    payload = {
        "mode": args.mode,
        "state_dir": str(state),
        "required_steps": list(required_steps(args.mode)),
        "completed_steps": list(completed_steps(state)) if state.exists() else [],
        "complete": is_workflow_complete(state, args.mode) if state.exists() else False,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
