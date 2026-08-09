"""Lightweight MQL5 source parser + symbol graph (v2.4 code-quality layer).

This is the shared **Stage 0** for the deep-review pipeline. It performs a
cheap, dependency-free, regex/scan-based parse of MQL5 source and exposes:

* :class:`FunctionInfo` - every function definition with line span + body.
* :class:`SymbolGraph`  - declared functions/inputs/globals + def<->use map.

It is intentionally *heuristic* (MQL5 is C++-like; a full parser is out of
scope). Every downstream consumer (structure-audit, deadcode, symbol-graph,
line-review) treats results as WARN-level signals, never hard verdicts.

Reads go through :func:`read_mq5_text` so UTF-16-LE EAs (MetaEditor default)
parse correctly - this was the v2.3.1 lesson.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .mq5_io import read_mq5_text

# MQL5 reserved/event handlers that are invoked by the terminal, never by
# user code - excluded from "unused function" reporting.
EVENT_HANDLERS: frozenset[str] = frozenset({
    "OnInit", "OnDeinit", "OnTick", "OnTimer", "OnTrade", "OnTradeTransaction",
    "OnChartEvent", "OnBookEvent", "OnTester", "OnTesterInit", "OnTesterDeinit",
    "OnTesterPass", "OnStart", "OnCalculate",
})

# Keywords that can be followed by `(` but are NOT function definitions.
_CONTROL_KW: frozenset[str] = frozenset({
    "if", "for", "while", "switch", "return", "sizeof", "catch", "else",
    "do", "case", "new", "delete", "operator",
})

# C++/MQL5 builtin type words used to recognise declarations.
_TYPE_WORDS: frozenset[str] = frozenset({
    "void", "int", "uint", "long", "ulong", "short", "ushort", "char", "uchar",
    "bool", "double", "float", "string", "datetime", "color", "enum", "struct",
    "class", "char", "matrix", "vector", "complex",
})

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING_LIT = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LIT = re.compile(r"'(?:\\.|[^'\\])*'")


def strip_comments_and_strings(text: str) -> str:
    """Blank out comments and string/char literals, preserving newlines.

    Newlines inside removed spans are kept so line numbers stay stable.
    """
    def _blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = _BLOCK_COMMENT.sub(_blank, text)
    text = _LINE_COMMENT.sub(_blank, text)
    text = _STRING_LIT.sub(_blank, text)
    text = _CHAR_LIT.sub(_blank, text)
    return text


def line_of(text: str, pos: int) -> int:
    """1-based line number for a character offset."""
    return text.count("\n", 0, pos) + 1


@dataclass
class FunctionInfo:
    name: str
    return_type: str
    params_raw: str
    start_line: int
    end_line: int
    body: str = ""
    arg_count: int = 0

    @property
    def loc(self) -> int:
        return max(1, self.end_line - self.start_line + 1)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "return_type": self.return_type,
            "params": self.params_raw,
            "arg_count": self.arg_count,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "loc": self.loc,
        }


# A function definition header: <type> <name> ( ... ) {
# Captures return type, name, and param list. Requires an opening brace to
# distinguish definitions from prototypes/calls.
_FUNC_DEF = re.compile(
    r"(?P<ret>(?:[A-Za-z_][\w:]*\s*[\*&]?\s+)+)"  # return type (>=1 word)
    r"(?P<name>[A-Za-z_]\w*)\s*"
    r"\((?P<params>[^;{}]*)\)\s*"
    r"(?:const\s*)?"
    r"\{",
    re.M,
)


def _match_brace_block(code: str, open_idx: int) -> int:
    """Return index just past the matching close brace for code[open_idx]=='{'."""
    depth = 0
    i = open_idx
    n = len(code)
    while i < n:
        c = code[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _count_args(params_raw: str) -> int:
    s = params_raw.strip()
    if not s or s == "void":
        return 0
    # naive split on top-level commas (templates/arrays rare in EA sigs)
    depth = 0
    count = 1
    for ch in s:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


def parse_functions(text: str) -> list[FunctionInfo]:
    """Extract function definitions from source (comments/strings stripped)."""
    code = strip_comments_and_strings(text)
    funcs: list[FunctionInfo] = []
    for m in _FUNC_DEF.finditer(code):
        name = m.group("name")
        if name in _CONTROL_KW:
            continue
        ret = m.group("ret").strip()
        # Reject obvious non-functions: a `ret` that is a control keyword.
        first_word = ret.split()[0] if ret.split() else ""
        if first_word in _CONTROL_KW:
            continue
        open_brace = code.index("{", m.end() - 1)
        end = _match_brace_block(code, open_brace)
        fi = FunctionInfo(
            name=name,
            return_type=ret,
            params_raw=m.group("params").strip(),
            start_line=line_of(code, m.start()),
            end_line=line_of(code, end - 1),
            body=text[open_brace:end],
            arg_count=_count_args(m.group("params")),
        )
        funcs.append(fi)
    return funcs


_INPUT_DECL = re.compile(
    r"^\s*(?:input|sinput|extern)\s+(?:[A-Za-z_][\w:<>\s\*&]*?)\s+"
    r"([A-Za-z_]\w*)\s*(?:=|;)",
    re.M,
)

_INCLUDE = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.M)
_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")


@dataclass
class SymbolGraph:
    source: str
    functions: list[FunctionInfo] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    # name -> list of 1-based line numbers where it is *used* (called/read)
    uses: dict[str, list[int]] = field(default_factory=dict)

    def function_names(self) -> set[str]:
        return {f.name for f in self.functions}

    def call_count(self, name: str) -> int:
        return len(self.uses.get(name, []))

    def reference_count(self, name: str) -> int:
        """Uses of *name* excluding its own definition header(s).

        A function definition header ``foo(`` is itself matched by the call
        scanner, so a never-called function still has ``call_count == 1``.
        Subtract one self-reference per matching definition so callers can
        test ``reference_count(name) == 0`` for true dead functions.
        """
        defs = sum(1 for f in self.functions if f.name == name)
        return max(0, self.call_count(name) - defs)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "functions": [f.to_dict() for f in self.functions],
            "inputs": self.inputs,
            "includes": self.includes,
        }


def build_symbol_graph(text: str, *, source: str = "<text>") -> SymbolGraph:
    """Build a def<->use symbol graph from a single source text."""
    code = strip_comments_and_strings(text)
    funcs = parse_functions(text)
    inputs = _INPUT_DECL.findall(text)
    includes = _INCLUDE.findall(text)

    # Build call/use map: count identifier( occurrences, and bare identifier
    # token occurrences for inputs/globals.
    uses: dict[str, list[int]] = {}
    for m in _CALL.finditer(code):
        name = m.group(1)
        if name in _CONTROL_KW or name in _TYPE_WORDS:
            continue
        uses.setdefault(name, []).append(line_of(code, m.start()))

    # token uses (for input/global usage detection)
    for name in set(inputs):
        for m in re.finditer(r"\b" + re.escape(name) + r"\b", code):
            uses.setdefault(name, []).append(line_of(code, m.start()))

    return SymbolGraph(
        source=source,
        functions=funcs,
        inputs=list(dict.fromkeys(inputs)),
        includes=includes,
        uses=uses,
    )


def build_from_path(path: str | Path) -> SymbolGraph:
    text = read_mq5_text(path, errors="replace")
    return build_symbol_graph(text, source=str(path))


def merge_sources(files: dict[str, str]) -> str:
    """Join multiple project files with FILE markers (for whole-project scan)."""
    return "\n".join(f"\n// FILE: {k}\n{v}" for k, v in files.items())


__all__ = [
    "EVENT_HANDLERS",
    "FunctionInfo",
    "SymbolGraph",
    "strip_comments_and_strings",
    "line_of",
    "parse_functions",
    "build_symbol_graph",
    "build_from_path",
    "merge_sources",
]
