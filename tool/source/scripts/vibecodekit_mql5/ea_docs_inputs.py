"""Parser for MQL5 ``input`` and ``input group`` declarations.

Used by the EA-docs renderer (PR-16) to populate the §4 "EA Inputs" table
with everything the user can tweak in the strategy tester / live chart.

Grammar supported (everything the kit's scaffolds actually emit):

    input  <type> <name> = <default>;
    input  <type> <name> = <default>;  // <inline tooltip>
    sinput <type> <name> = <default>;
    input  group "Group Label";

Comment-only lines, blank lines, and ``//+----...`` banners are ignored.
Enum types are kept as raw identifiers (e.g. ``ENUM_TIMEFRAMES``); the
renderer surfaces the type verbatim so the trader sees what the EA's
combobox accepts in the strategy tester.

The parser does **not** evaluate or sanity-check defaults — that's the
compiler's job. It only extracts the four columns of the inputs table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "InputDecl",
    "parse_inputs",
]


# Match ``input <type> <name> = <default>; [// tooltip]``.
#
# - Supports ``sinput`` (static input) by making the ``s`` prefix optional.
# - Skips ``input group "..."`` lines (handled separately).
# - ``<type>`` is one identifier (no namespace qualifier in MQL5 inputs).
# - ``<default>`` is everything up to the trailing ``;`` (greedy minus
#   the ``;`` itself). We don't try to parse out expressions like
#   ``2 * 60`` — store the raw text.
# - Trailing ``//`` comment is captured as the tooltip (whitespace
#   trimmed).
_INPUT_RE = re.compile(
    r"""
    ^\s*                                # leading whitespace
    s?input\s+                          # input | sinput
    (?P<type>[A-Za-z_][A-Za-z0-9_]*)\s+ # type
    (?!group\b)                         # not an input group
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)    # identifier
    \s*=\s*
    (?P<default>[^;/]+?)                # default — stop at ';' or '//'
    \s*;\s*
    (?://\s*(?P<tooltip>.*?))?          # optional inline comment
    \s*$
    """,
    re.MULTILINE | re.VERBOSE,
)

_GROUP_RE = re.compile(
    r'^\s*input\s+group\s+"(?P<label>[^"]+)"\s*;\s*(?://.*)?\s*$',
    re.MULTILINE,
)


@dataclass(frozen=True)
class InputDecl:
    """One parsed ``input`` declaration.

    ``group`` is the most-recently-seen ``input group "..."`` label
    above this declaration (empty string if none).
    """

    group: str
    name: str
    type: str
    default: str
    tooltip: str = ""
    line_number: int = 0  # 1-based, matches grep / editor jump-to-line

    def to_dict(self) -> dict[str, str | int]:
        return {
            "group": self.group,
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "tooltip": self.tooltip,
            "line_number": self.line_number,
        }


@dataclass
class _ScanState:
    current_group: str = ""
    decls: list[InputDecl] = field(default_factory=list)


def parse_inputs(mq5_text: str) -> list[InputDecl]:
    """Extract every ``input`` declaration from raw ``.mq5`` source.

    Preserves source order so the rendered table reads top-to-bottom
    just like the strategy-tester sidebar.

    Lines that look like declarations but live inside ``/* ... */``
    block comments are still picked up — that's a deliberate
    simplification (full lex of MQL5 source would be overkill for
    what is, in practice, never a real-world false positive). If a
    scaffold author commented out an ``input`` line they should
    delete it rather than wrap it.
    """
    if not mq5_text:
        return []

    state = _ScanState()
    for line_no, line in _iter_logical_lines(mq5_text):
        # Skip ``//`` line comments entirely (very common in MQL5
        # banner blocks) before any regex work.
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue

        if (m := _GROUP_RE.match(line)) is not None:
            state.current_group = m.group("label").strip()
            continue

        if (m := _INPUT_RE.match(line)) is not None:
            default = m.group("default").strip().rstrip(",")
            tooltip = (m.group("tooltip") or "").strip()
            state.decls.append(
                InputDecl(
                    group=state.current_group,
                    name=m.group("name"),
                    type=m.group("type"),
                    default=default,
                    tooltip=tooltip,
                    line_number=line_no,
                )
            )

    return state.decls


def _iter_logical_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(1-based-line-number, line)`` pairs.

    We deliberately don't try to join physical lines on backslash
    continuations — MQL5 inputs are always written on a single line,
    and the scaffolds the kit ships with hold to that.
    """
    for i, line in enumerate(text.splitlines(), start=1):
        yield i, line
