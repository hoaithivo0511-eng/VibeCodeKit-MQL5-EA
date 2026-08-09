"""Step-output content validator.

The 8-step RRI methodology declares a step "done" when
``.rri-state/<step>.done`` exists, but the existing sentinel scheme is
file-touch-only: an operator (or LLM agent) can mark a step done without
filling in any of the template's ``## Activities`` checkboxes.

This module reads the rendered step output (``step-N-<name>.md`` next to
the sentinel, or supplied explicitly) and verifies:

* Every ``- [ ]`` checkbox under ``## Activities`` has been ticked
  (``- [x]`` / ``- [X]``), OR
* The operator has explicitly opted out via the ``mode``-based threshold
  defined here (e.g. personal mode accepts ≥ 50% ticked).

Hooked into Layer-5 (methodology) of the permission gate so a TEAM /
ENTERPRISE build cannot ship while ``.rri-state/<step>.done`` is a lie.

Default operating mode preserves the legacy ``.done``-only behaviour
(``activity_threshold=0``); the caller (layer-5) opts in via
``activity_threshold`` per mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import step_workflow as sw

_CHECKBOX = re.compile(r"^\s*-\s*\[([ xX])\]\s+(.*?)\s*$")


@dataclass(frozen=True)
class ActivityAudit:
    """Activity-checkbox audit for a single step output file."""

    step: str
    output_path: Path | None
    total: int
    ticked: int
    untouched: tuple[str, ...]

    @property
    def ratio(self) -> float:
        if self.total == 0:
            return 1.0
        return self.ticked / self.total

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "output_path": str(self.output_path) if self.output_path else None,
            "total_activities": self.total,
            "ticked": self.ticked,
            "ratio": round(self.ratio, 4),
            "untouched": list(self.untouched),
        }


def step_output_path(state_dir: Path, step: str) -> Path | None:
    """Return the markdown output expected next to the sentinel.

    Convention: ``<state_dir>/step-N-<step>.md`` mirrors the template
    name. If the operator instead places the file in the repo root we
    also look for ``./step-N-<step>.md`` as a fallback so the validator
    works for both flat layouts (small repos) and nested ones (the kit's
    own ``docs/rri-state/``).
    """

    desc = sw.descriptor(step)
    candidate = state_dir / f"step-{desc.number}-{step}.md"
    if candidate.is_file():
        return candidate
    flat = Path(f"step-{desc.number}-{step}.md")
    if flat.is_file():
        return flat
    return None


def audit_step_output(
    step: str,
    *,
    output_path: Path | None = None,
    state_dir: Path | None = None,
) -> ActivityAudit:
    """Audit a rendered step output for ticked ``## Activities`` checkboxes.

    One of ``output_path`` or ``state_dir`` MUST be supplied. If both
    are given, ``output_path`` wins.
    """

    if output_path is None:
        if state_dir is None:
            raise ValueError("audit_step_output requires output_path or state_dir")
        output_path = step_output_path(state_dir, step)

    if output_path is None or not output_path.is_file():
        return ActivityAudit(
            step=step, output_path=output_path,
            total=0, ticked=0, untouched=(),
        )

    body = output_path.read_text(encoding="utf-8")
    lines = body.splitlines()
    in_section = False
    total = 0
    ticked = 0
    untouched: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Activities"
            continue
        if not in_section:
            continue
        m = _CHECKBOX.match(line)
        if not m:
            continue
        flag = m.group(1)
        label = m.group(2).strip()
        total += 1
        if flag.lower() == "x":
            ticked += 1
        else:
            untouched.append(label)
    return ActivityAudit(
        step=step, output_path=output_path,
        total=total, ticked=ticked, untouched=tuple(untouched),
    )


# Default per-mode activity-completion thresholds (fraction of `[x]` vs total).
# Personal mode is lenient (lets quick iterations through); team raises the
# bar; enterprise demands every box.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "personal": 0.50,
    "team": 0.80,
    "enterprise": 1.00,
}


def passes_threshold(audit: ActivityAudit, threshold: float) -> bool:
    """Whether the audit meets a fractional threshold.

    Empty templates (``total == 0``) pass at every threshold so the
    validator is no-op for steps whose output file is missing or whose
    template has no activities yet — those failures show up under the
    legacy sentinel-existence check in
    :func:`step_workflow.completed_steps`.
    """

    if audit.total == 0:
        return True
    return audit.ratio >= threshold


__all__ = [
    "ActivityAudit",
    "DEFAULT_THRESHOLDS",
    "audit_step_output",
    "passes_threshold",
    "step_output_path",
]
