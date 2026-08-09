"""Per-input semantic library + scaffold flow narrative loader.

This module enriches the post-build EA documentation so end users
receive an operator manual rather than a raw input dump. It loads two
artifact families:

1. ``docs/input-semantics.yaml`` — hand-authored library that maps
   each common ``input`` name (``InpMagic``, ``InpRiskMoney`` ...) to
   a meaning / unit / formula / sensible-range tuple. The library is
   *additive*: an input not present in the library simply renders
   with its source-side tooltip (legacy behaviour).

2. ``scaffolds/<preset>/<stack>/FLOW-vi.md`` — narrative description
   of how the rendered EA executes (OnInit / OnTick / OnDeinit), one
   per archetype. Placeholders like ``{spec.name}``,
   ``{spec.symbol}``, ``{spec.risk.daily_loss_pct}`` are substituted
   with values from the validated ``EaSpec`` before the renderer
   embeds the narrative in ``.docs.html`` / ``.docs.md``.

The initial library (Vietnamese-only) covers the ``trend/netting`` and
``portfolio-basket/{netting,hedging}`` scaffolds plus ~20 common
input names. Later updates backfill the remaining 20+ archetypes.

This module is intentionally LLM-free: every semantic comes from a
checked-in YAML library, every narrative comes from a checked-in
markdown file. No model is invoked, ever (the kit spec §3 anti-pattern).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .ea_docs_inputs import InputDecl

__all__ = [
    "InputSemantic",
    "EnrichedParamRow",
    "load_input_semantics",
    "load_flow_narrative",
    "enrich_param_rows",
    "substitute_placeholders",
    "DEFAULT_SEMANTICS_PATH",
    "DEFAULT_SCAFFOLDS_ROOT",
]


# Repo-rooted defaults so callers don't have to plumb paths. Tests can
# override these by passing explicit ``path`` / ``scaffolds_root`` args.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SEMANTICS_PATH = _REPO_ROOT / "docs" / "input-semantics.yaml"
DEFAULT_SCAFFOLDS_ROOT = _REPO_ROOT / "scaffolds"


@dataclass(frozen=True)
class InputSemantic:
    """Static documentation for a single ``input`` declaration name.

    Sourced from ``docs/input-semantics.yaml``. Every field is plain
    text; the renderer is responsible for HTML escaping.
    """

    name: str
    meaning: str
    unit: str
    formula: str
    depends_on: tuple[str, ...]
    used_by: str
    sensible_range: str
    gotchas: str


@dataclass(frozen=True)
class EnrichedParamRow:
    """Param-table row merged with its semantic-library entry, if any.

    ``semantic`` is ``None`` for inputs that don't have a library
    entry yet — the renderer falls back to source-side ``tooltip``
    only, matching the original behaviour.
    """

    group: str
    name: str
    type: str
    default: str
    tooltip: str
    semantic: "InputSemantic | None" = None


def load_input_semantics(path: Path | None = None) -> dict[str, InputSemantic]:
    """Load ``docs/input-semantics.yaml`` into a dict keyed by input name.

    Missing file or empty content returns ``{}``. PyYAML is a hard
    dependency of the kit (see ``pyproject.toml``) so the import is
    not guarded.
    """
    if path is None:
        path = DEFAULT_SEMANTICS_PATH
    if not path.is_file():
        return {}

    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"input-semantics.yaml root must be a mapping, got {type(raw).__name__}"
        )

    out: dict[str, InputSemantic] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"input-semantics.yaml entry for {name!r} must be a mapping"
            )
        out[name] = InputSemantic(
            name=name,
            meaning=str(entry.get("meaning_vi", "")).strip(),
            unit=str(entry.get("unit", "")).strip(),
            formula=str(entry.get("formula_vi", "")).strip(),
            depends_on=tuple(entry.get("depends_on") or ()),
            used_by=str(entry.get("used_by", "")).strip(),
            sensible_range=str(entry.get("sensible_range_vi", "")).strip(),
            gotchas=str(entry.get("gotchas_vi", "")).strip(),
        )
    return out


def load_flow_narrative(
    preset: str,
    stack: str,
    *,
    lang: str = "vi",
    scaffolds_root: Path | None = None,
) -> str | None:
    """Return the FLOW narrative for one ``preset/stack`` scaffold.

    Reads ``scaffolds/<preset>/<stack>/FLOW-<lang>.md`` if present.
    Returns ``None`` when the archetype hasn't been authored yet —
    the renderer simply omits the section (no error).
    """
    if scaffolds_root is None:
        scaffolds_root = DEFAULT_SCAFFOLDS_ROOT
    flow_path = scaffolds_root / preset / stack / f"FLOW-{lang}.md"
    if not flow_path.is_file():
        return None
    return flow_path.read_text(encoding="utf-8")


def enrich_param_rows(
    decls: Iterable[InputDecl],
    semantics: dict[str, InputSemantic] | None = None,
) -> list[EnrichedParamRow]:
    """Lift parsed ``InputDecl`` rows to ``EnrichedParamRow`` via the library.

    Inputs not covered by the library still produce a row — they just
    have ``semantic=None`` and the renderer downgrades the row to the
    original layout (group / name / type / default / tooltip).
    """
    if semantics is None:
        semantics = load_input_semantics()
    rows: list[EnrichedParamRow] = []
    for decl in decls:
        rows.append(
            EnrichedParamRow(
                group=decl.group,
                name=decl.name,
                type=decl.type,
                default=decl.default,
                tooltip=decl.tooltip,
                semantic=semantics.get(decl.name),
            )
        )
    return rows


# Match ``{spec.foo.bar:fmt}`` where ``fmt`` is optional. Crucially this
# does NOT match ``{InpXxx}`` so input identifiers can be handled by a
# separate pass that wraps them in backticks. ``\w`` here means ASCII
# word char so Vietnamese / accented characters in caption text are safe.
_SPEC_PLACEHOLDER_RE = re.compile(
    r"\{spec((?:\.[a-z_][a-z0-9_]*)+)(?::([a-z_]+))?\}"
)

# Match ``{InpXxx}`` — author-side shorthand for "this MQL5 input
# parameter goes here". The substitution replaces these with the bare
# backtick-wrapped name so the rendered narrative reads as code rather
# than as an unfilled template token. The leading ``Inp`` prefix is the
# kit's universal naming convention for ``input`` declarations.
_INPUT_PLACEHOLDER_RE = re.compile(r"\{(Inp[A-Z][A-Za-z0-9_]*)\}")


def _walk_attr(spec, dotted_path: str):
    """Traverse ``spec.foo.bar`` style paths. Returns ``None`` on miss."""
    cursor = spec
    for part in dotted_path.split(".")[1:]:  # leading "." → empty first slot
        if cursor is None:
            return None
        cursor = getattr(cursor, part, None)
    return cursor


def _format_value(value, hint: str | None) -> str:
    """Render a substituted value as a string.

    ``hint`` is the optional ``:fmt`` suffix on the placeholder. Supported:

    * ``pct``     — value is already a percentage (per ``EaSpec`` schema:
                    ``risk.daily_loss_pct = 5.0`` means 5 %, ``0.5`` means
                    0.5 %). The formatter just trims trailing zeros and
                    appends ``%``. Do NOT use this hint on fractions — wrap
                    them with ``frac_to_pct`` instead.
    * ``frac_to_pct`` — value is a fraction in [0, 1]; multiply by 100 and
                    append ``%``. Use for legacy raw fractions only.
    * ``int``     — round to nearest integer.
    * (no hint)   — ``str(value)``.
    """
    if value is None:
        return "—"
    if hint == "pct":
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)
        # Drop trailing zeros: 5.0 → "5", 4.5 → "4.5"
        text = f"{num:g}"
        return f"{text}%"
    if hint == "frac_to_pct":
        try:
            num = float(value) * 100.0
        except (TypeError, ValueError):
            return str(value)
        text = f"{num:g}"
        return f"{text}%"
    if hint == "int":
        try:
            return str(int(round(float(value))))
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def substitute_placeholders(text: str, spec) -> str:
    """Replace ``{spec.foo.bar}`` placeholders with values from ``spec``.

    ``{InpXxx}`` identifiers and any other ``{…}`` form that doesn't
    start with ``spec.`` are passed through untouched (they're EA input
    names that must appear verbatim in the rendered docs).

    Missing attributes resolve to ``"—"`` so a malformed placeholder
    can never crash the build pipeline. Authors should never see this
    in practice because the matching test suite asserts all
    placeholders in committed FLOW files resolve.
    """
    if not text:
        return text

    def _sub_spec(match: re.Match[str]) -> str:
        dotted = match.group(1)
        hint = match.group(2)
        value = _walk_attr(spec, dotted)
        return _format_value(value, hint)

    out = _SPEC_PLACEHOLDER_RE.sub(_sub_spec, text)
    out = _INPUT_PLACEHOLDER_RE.sub(lambda m: f"`{m.group(1)}`", out)
    return out
