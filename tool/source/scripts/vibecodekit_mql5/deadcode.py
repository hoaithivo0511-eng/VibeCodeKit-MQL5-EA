"""Stage-4 dead-code / dead-logic detector.

Finds, with conservative heuristics so standard MQL5 idioms are not flagged:

* unused functions (defined, never referenced, not an event handler)
* unused ``input``/``sinput`` parameters
* unreachable statements after ``return``/``break``/``continue`` in a block
* always-constant branches (``if(false)`` / ``if(true)``)
* ``#include`` whose header symbols are never referenced (best-effort)

Emits senior-review issue dicts under category ``code_quality``.
"""
from __future__ import annotations

import re
from typing import Any

from .mq5_symbols import (
    EVENT_HANDLERS,
    SymbolGraph,
    build_symbol_graph,
    line_of,
    strip_comments_and_strings,
)

# Library headers whose usage is hard to attribute to a single symbol; never
# flag these as unused to avoid false positives.
_ALWAYS_USED_INCLUDES = re.compile(r"Trade|Object|Arrays|Indicators|Expert", re.I)


def _issue(severity: str, title: str, evidence: str, rec: str,
           line: int | None = None) -> dict[str, Any]:
    d = {
        "severity": severity,
        "category": "code_quality",
        "title": title,
        "evidence": evidence,
        "recommendation": rec,
    }
    if line is not None:
        d["line"] = line
    return d


def _unused_functions(graph: SymbolGraph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fn in graph.functions:
        if fn.name in EVENT_HANDLERS:
            continue
        # constructors/destructors and operator overloads are referenced
        # implicitly; skip names that look like them.
        if fn.name.startswith("~") or fn.return_type.endswith("::"):
            continue
        if graph.reference_count(fn.name) == 0:
            out.append(_issue("warn", f"Unused function: {fn.name}()",
                              f"{fn.name} is defined at line {fn.start_line} "
                              f"but never called.",
                              "Remove it or wire it into the call graph.",
                              fn.start_line))
    return out


def _unused_inputs(graph: SymbolGraph, text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    code = strip_comments_and_strings(text)
    for name in graph.inputs:
        # one occurrence == declaration only
        if graph.call_count(name) <= 1:
            m = re.search(r"\b" + re.escape(name) + r"\b", code)
            ln = line_of(code, m.start()) if m else None
            out.append(_issue("warn", f"Unused input: {name}",
                              f"input {name} appears only in its declaration.",
                              "Remove the input or connect it to logic/docs.",
                              ln))
    return out


# Matches a jump statement and captures the index right after its ';'.
_JUMP = re.compile(r"\b(return\b[^;{}]*|break|continue)\s*;")


def _unreachable_after_jump(graph: SymbolGraph) -> list[dict[str, Any]]:
    """Flag the first statement that follows a jump within the same block.

    Brace-aware: after a ``return/break/continue;`` the next meaningful
    character must close the block (``}``) or be a switch label; anything
    else is unreachable. Works for inline and multi-line bodies alike.
    """
    out: list[dict[str, Any]] = []
    for fn in graph.functions:
        code = strip_comments_and_strings(fn.body)
        for m in _JUMP.finditer(code):
            # Skip CONDITIONAL jumps: `if(...) return;`, `else return;`,
            # `do ... while` etc. Only a standalone jump statement makes the
            # following statement unreachable. Look at the char just before.
            head = code[:m.start()].rstrip()
            if head and head[-1] not in "{};:":
                continue  # preceded by `)`/`else`/expr -> conditional jump
            if re.search(r"\belse\s*$", head):
                continue
            tail = code[m.end():]
            stripped = tail.lstrip()
            if not stripped:
                continue
            ch = stripped[0]
            if ch in "}":
                continue  # jump ends its block - legitimate
            if re.match(r"(case\b|default\b|#)", stripped):
                continue  # switch label / preprocessor - legitimate
            abs_line = fn.start_line + code.count("\n", 0, m.end())
            out.append(_issue(
                "warn", f"Unreachable code in {fn.name}()",
                f"Statement after a return/break/continue near line "
                f"{abs_line} can never execute.",
                "Remove the dead statement or fix the control flow.",
                abs_line))
    return out


def _constant_branches(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    code = strip_comments_and_strings(text)
    for m in re.finditer(r"\bif\s*\(\s*(false|0)\s*\)", code):
        out.append(_issue("warn", "Dead branch: if(false)",
                          f"Always-false condition at line {line_of(code, m.start())}.",
                          "Remove the dead branch.",
                          line_of(code, m.start())))
    for m in re.finditer(r"\bif\s*\(\s*(true|1)\s*\)", code):
        out.append(_issue("info", "Constant branch: if(true)",
                          f"Always-true condition at line {line_of(code, m.start())}.",
                          "Drop the redundant condition.",
                          line_of(code, m.start())))
    return out


def _unused_includes(graph: SymbolGraph, text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    code = strip_comments_and_strings(text)
    for inc in graph.includes:
        if _ALWAYS_USED_INCLUDES.search(inc):
            continue
        # derive a likely symbol stem from the header file name
        stem = re.split(r"[\\/]", inc)[-1].rsplit(".", 1)[0]
        if not stem or len(stem) < 3:
            continue
        # count references to the stem outside the #include line
        refs = len(re.findall(r"\b" + re.escape(stem) + r"\b", code))
        if refs == 0:
            out.append(_issue("info", f"Possibly unused include: {inc}",
                              f"No reference to '{stem}' found outside the "
                              f"#include directive.",
                              "Remove the include if the header is unused "
                              "(verify manually for macro-only headers)."))
    return out


def find_dead_code(text: str, *, graph: SymbolGraph | None = None) -> dict[str, Any]:
    if graph is None:
        graph = build_symbol_graph(text)
    issues: list[dict[str, Any]] = []
    issues.extend(_unused_functions(graph))
    issues.extend(_unused_inputs(graph, text))
    issues.extend(_unreachable_after_jump(graph))
    issues.extend(_constant_branches(text))
    issues.extend(_unused_includes(graph, text))
    counts = {"dead_findings": len(issues)}
    return {"issues": issues, "metrics": counts}


__all__ = ["find_dead_code"]
