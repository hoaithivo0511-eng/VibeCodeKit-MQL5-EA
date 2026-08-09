"""Parser for MQL5 ``input`` and ``input group`` declarations.

Used by the EA-docs renderer (PR-16) to populate the §4 "EA Inputs" table
with everything the user can tweak in the strategy tester / live chart.

Grammar supported (everything the kit's scaffolds actually emit):

    input  <type> <name> = <default>;
    input  <type> <name> = <default>;  // <inline tooltip>
    sinput <type> <name> = <default>;
    input  group "Group Label";

Comment-only lines, blank lines, and ``//+----...`` banners are ignored.
Declarations inside block comments are ignored as code, while comment markers
inside quoted defaults remain ordinary string data.
Enum types are kept as raw identifiers (e.g. ``ENUM_TIMEFRAMES``); the
renderer surfaces the type verbatim so the trader sees what the EA's
combobox accepts in the strategy tester.

The parser does **not** evaluate or sanity-check defaults — that's the
compiler's job. It only extracts the four columns of the inputs table.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = [
    "InputDecl",
    "parse_inputs",
]


# Match the code part of ``input <type> <name> = <default>;``.  Inline
# comments are separated by the small lexer below so ``https://`` and ``/*``
# inside a quoted string are never mistaken for comments.  The final
# semicolon is matched greedily, which also preserves semicolons inside a
# quoted string default.
_INPUT_RE = re.compile(
    r"""
    ^\s*                                # leading whitespace
    (?P<storage>s?input)\s+             # input | sinput
    (?P<type>[A-Za-z_][A-Za-z0-9_]*)\s+ # type
    (?!group\b)                         # not an input group
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)    # identifier
    \s*=\s*
    (?P<default>.+)                     # raw default; lexer removed comments
    \s*;\s*
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
    storage: str = "input"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "group": self.group,
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "tooltip": self.tooltip,
            "line_number": self.line_number,
            "storage": self.storage,
        }


@dataclass
class _ScanState:
    current_group: str = ""
    decls: list[InputDecl] = field(default_factory=list)


def parse_inputs(mq5_text: str) -> list[InputDecl]:
    """Extract every ``input`` declaration from raw ``.mq5`` source.

    Preserves source order so the rendered table reads top-to-bottom
    just like the strategy-tester sidebar.

    The scanner is deliberately line-oriented because MQL5 input declarations
    are single-line statements, but it still tracks block comments and quoted
    strings.  This keeps declaration counts exact without pretending to be a
    complete MQL5 parser.
    """
    if not mq5_text:
        return []

    state = _ScanState()
    in_block_comment = False
    for line_no, line in _iter_logical_lines(mq5_text):
        line, tooltip, in_block_comment = _strip_comments(line, in_block_comment)
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
            state.decls.append(
                InputDecl(
                    group=state.current_group,
                    name=m.group("name"),
                    type=m.group("type"),
                    default=default,
                    tooltip=tooltip,
                    line_number=line_no,
                    storage=m.group("storage"),
                )
            )

    return state.decls


def _strip_comments(line: str, in_block: bool) -> tuple[str, str, bool]:
    """Return code, trailing ``//`` tooltip, and block-comment state.

    Quote and escape handling is intentionally limited to what can occur in an
    MQL5 single-line input default.  Newlines are processed by the caller.
    """
    code: list[str] = []
    tooltip = ""
    quote = ""
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            code.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            code.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            code.append(" ")
            i += 2
            continue
        if ch == "/" and nxt == "/":
            tooltip = line[i + 2 :].strip()
            break
        code.append(ch)
        i += 1
    return "".join(code), tooltip, in_block


def _iter_logical_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(1-based-line-number, line)`` pairs.

    We deliberately don't try to join physical lines on backslash
    continuations — MQL5 inputs are always written on a single line,
    and the scaffolds the kit ships with hold to that.
    """
    yield from enumerate(text.splitlines(), start=1)
