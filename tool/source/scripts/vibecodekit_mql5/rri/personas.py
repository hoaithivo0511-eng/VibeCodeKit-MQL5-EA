"""mql5-rri-personas — load the 6 RRI personas from YAML and filter by mode.

the kit spec §9 lays out 6 personas (trader, risk-auditor, broker-engineer,
strategy-architect, devops, perf-analyst). Each persona owns 25 questions
spread across three audit modes:

    PERSONAL    — 5 questions / persona  → 30 total
    TEAM        — 12 questions / persona → 72 total
    ENTERPRISE  — 25 questions / persona → 150 total

Questions live in ``docs/rri-personas/<persona>.yaml`` and carry both a
``priority`` (critical / high / standard) and an ``applicable_modes`` list.
This module loads them, validates the schema, and exposes a small
filter API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

PERSONA_IDS: tuple[str, ...] = (
    "trader",
    "risk-auditor",
    "broker-engineer",
    "strategy-architect",
    "devops",
    "perf-analyst",
)

MODES: tuple[str, ...] = ("personal", "team", "enterprise")

QUESTIONS_PER_MODE: dict[str, int] = {"personal": 5, "team": 12, "enterprise": 25}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DIR = _REPO_ROOT / "docs" / "rri-personas"


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    priority: str
    applicable_steps: tuple[str, ...]
    applicable_modes: tuple[str, ...]


@dataclass(frozen=True)
class Persona:
    persona: str
    description: str
    questions: tuple[Question, ...]


def _question_from_dict(d: dict) -> Question:
    return Question(
        id=str(d["id"]),
        text=str(d["text"]),
        priority=str(d["priority"]),
        applicable_steps=tuple(d.get("applicable_steps", [])),
        applicable_modes=tuple(d.get("applicable_modes", [])),
    )


def load_persona(persona: str, base_dir: os.PathLike | str | None = None) -> Persona:
    """Load a single persona YAML by id."""
    if persona not in PERSONA_IDS:
        raise ValueError(f"unknown persona: {persona!r}")
    base = Path(base_dir) if base_dir else _DEFAULT_DIR
    path = base / f"{persona}.yaml"
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw.get("persona") != persona:
        raise ValueError(f"{path}: persona field mismatch")
    questions = tuple(_question_from_dict(q) for q in raw.get("questions", []))
    if len(questions) != 25:
        raise ValueError(f"{path}: expected 25 questions, got {len(questions)}")
    return Persona(persona=persona, description=raw.get("description", ""), questions=questions)


def load_all(base_dir: os.PathLike | str | None = None) -> dict[str, Persona]:
    return {pid: load_persona(pid, base_dir) for pid in PERSONA_IDS}


def filter_for_mode(persona: Persona, mode: str) -> tuple[Question, ...]:
    """Return the subset of questions that apply to the given mode."""
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}")
    matched = tuple(q for q in persona.questions if mode in q.applicable_modes)
    expected = QUESTIONS_PER_MODE[mode]
    if len(matched) != expected:
        raise ValueError(
            f"persona {persona.persona!r} mode {mode!r}: "
            f"expected {expected} questions, got {len(matched)}"
        )
    return matched


def total_for_mode(mode: str, base_dir: os.PathLike | str | None = None) -> int:
    personas = load_all(base_dir)
    return sum(len(filter_for_mode(p, mode)) for p in personas.values())


def iter_questions(mode: str, base_dir: os.PathLike | str | None = None) -> Iterable[tuple[str, Question]]:
    """Yield ``(persona_id, question)`` pairs in deterministic order."""
    for pid in PERSONA_IDS:
        persona = load_persona(pid, base_dir)
        for q in filter_for_mode(persona, mode):
            yield pid, q


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="mql5-rri-personas")
    ap.add_argument("--mode", choices=MODES, default="personal")
    ap.add_argument("--persona", choices=PERSONA_IDS, default=None)
    args = ap.parse_args()

    if args.persona:
        persona = load_persona(args.persona)
        subset = filter_for_mode(persona, args.mode)
        payload = {
            "persona": persona.persona,
            "mode": args.mode,
            "count": len(subset),
            "questions": [
                {"id": q.id, "text": q.text, "priority": q.priority} for q in subset
            ],
        }
    else:
        payload = {
            "mode": args.mode,
            "total": total_for_mode(args.mode),
            "personas": PERSONA_IDS,
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
