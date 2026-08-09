"""Stage-3 structure audit: complexity, nesting, hot-path and duplication.

Consumes a :class:`SymbolGraph` (Stage 0) plus raw source and emits
evidence-gated findings in the senior-review issue schema:
``{severity, category, title, evidence, recommendation}`` with an extra
``line`` field when a location is known. ``category`` is always
``code_quality`` so the orchestrator can group them.

All thresholds are conservative; the goal is signal, not noise.
"""
from __future__ import annotations

import re
from typing import Any

from .mq5_symbols import (
    FunctionInfo,
    SymbolGraph,
    build_symbol_graph,
    strip_comments_and_strings,
)

# Thresholds (per-function unless noted).
LOC_WARN = 80
LOC_ERROR = 200
COMPLEXITY_WARN = 12
NESTING_WARN = 5
ARG_WARN = 7
DUP_BLOCK_MIN_LINES = 6

# Tokens that each add one decision path (McCabe-ish).
_DECISION = re.compile(
    r"\b(if|for|while|case|catch)\b|&&|\|\||\?"
)

# Calls that are expensive / forbidden in the OnTick hot-path.
_HOTPATH_CALLS = {
    "Sleep": ("critical", "blocks the EA thread; never sleep in OnTick"),
    "iCustom": ("warn", "creates an indicator handle every tick; cache the handle in OnInit"),
    "FileOpen": ("warn", "file I/O on every tick is slow; move out of OnTick or throttle"),
    "WebRequest": ("critical", "network call on every tick freezes the terminal; throttle/async"),
    "Print": ("info", "logging every tick floods the journal; gate behind a debug flag"),
    "Comment": ("info", "Comment() every tick is costly; throttle UI updates"),
}
# Indicator constructors that should be handle-cached, not called per tick.
_INDICATOR_CTORS = ("iMA", "iRSI", "iMACD", "iStochastic", "iATR", "iBands",
                    "iADX", "iCCI", "iCustom", "iEnvelopes", "iSAR")


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


def cyclomatic_complexity(body: str) -> int:
    """Approximate McCabe complexity: 1 + number of decision tokens."""
    code = strip_comments_and_strings(body)
    return 1 + len(_DECISION.findall(code))


def max_nesting_depth(body: str) -> int:
    """Maximum brace nesting depth inside a function body."""
    code = strip_comments_and_strings(body)
    depth = 0
    peak = 0
    for ch in code:
        if ch == "{":
            depth += 1
            peak = max(peak, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return peak


def _analyse_function(fn: FunctionInfo) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    loc = fn.loc
    if loc >= LOC_ERROR:
        out.append(_issue("error", f"Very long function: {fn.name}()",
                          f"{fn.name} spans {loc} lines (>= {LOC_ERROR}).",
                          "Split into smaller, single-responsibility helpers.",
                          fn.start_line))
    elif loc >= LOC_WARN:
        out.append(_issue("warn", f"Long function: {fn.name}()",
                          f"{fn.name} spans {loc} lines (>= {LOC_WARN}).",
                          "Consider extracting helpers to reduce length.",
                          fn.start_line))

    cc = cyclomatic_complexity(fn.body)
    if cc >= COMPLEXITY_WARN:
        sev = "error" if cc >= COMPLEXITY_WARN * 2 else "warn"
        out.append(_issue(sev, f"High cyclomatic complexity: {fn.name}()",
                          f"{fn.name} has approx. complexity {cc} (>= {COMPLEXITY_WARN}).",
                          "Reduce branching; extract decision logic into helpers.",
                          fn.start_line))

    nd = max_nesting_depth(fn.body)
    if nd >= NESTING_WARN:
        out.append(_issue("warn", f"Deep nesting: {fn.name}()",
                          f"{fn.name} nests {nd} levels deep (>= {NESTING_WARN}).",
                          "Use early returns / guard clauses to flatten logic.",
                          fn.start_line))

    if fn.arg_count >= ARG_WARN:
        out.append(_issue("warn", f"Too many parameters: {fn.name}()",
                          f"{fn.name} takes {fn.arg_count} parameters (>= {ARG_WARN}).",
                          "Group related parameters into a struct/config object.",
                          fn.start_line))
    return out


def _ontick_hotpath(graph: SymbolGraph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ontick = next((f for f in graph.functions if f.name == "OnTick"), None)
    if ontick is None:
        return out
    code = strip_comments_and_strings(ontick.body)
    base = ontick.start_line
    for call, (sev, why) in _HOTPATH_CALLS.items():
        m = re.search(r"\b" + re.escape(call) + r"\s*\(", code)
        if m:
            line = base + code.count("\n", 0, m.start())
            out.append(_issue(sev, f"Hot-path call in OnTick: {call}()",
                              f"{call}() is invoked inside OnTick; {why}.",
                              "Move the work out of OnTick or throttle by time/bar.",
                              line))
    # Indicator handle created in OnTick instead of cached in OnInit.
    for ctor in _INDICATOR_CTORS:
        m = re.search(r"\b" + re.escape(ctor) + r"\s*\(", code)
        if m:
            line = base + code.count("\n", 0, m.start())
            out.append(_issue("warn", f"Indicator handle in OnTick: {ctor}()",
                              f"{ctor}() called inside OnTick recreates a handle every tick.",
                              "Create the handle once in OnInit and cache it; "
                              "call CopyBuffer in OnTick.",
                              line))
            break
    return out


def _duplication(text: str) -> list[dict[str, Any]]:
    """Cheap duplicate-block detector: identical >=N-line windows."""
    code = strip_comments_and_strings(text)
    lines = [ln.strip() for ln in code.splitlines()]
    seen: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    n = DUP_BLOCK_MIN_LINES
    reported = 0
    for i in range(len(lines) - n + 1):
        window = [ln for ln in lines[i:i + n]]
        if sum(1 for ln in window if ln) < n:  # skip blank-heavy windows
            continue
        if any(len(ln) < 8 for ln in window):  # skip trivial lines
            continue
        key = "\n".join(window)
        if key in seen and reported < 5:
            out.append(_issue("info", "Duplicated code block",
                              f"A {n}-line block at line {i + 1} duplicates "
                              f"the block at line {seen[key] + 1}.",
                              "Extract the repeated block into a shared helper.",
                              i + 1))
            reported += 1
        else:
            seen.setdefault(key, i)
    return out


def audit_structure(text: str, *, graph: SymbolGraph | None = None) -> dict[str, Any]:
    """Run the full structure audit over a source text."""
    if graph is None:
        graph = build_symbol_graph(text)
    issues: list[dict[str, Any]] = []
    for fn in graph.functions:
        issues.extend(_analyse_function(fn))
    issues.extend(_ontick_hotpath(graph))
    issues.extend(_duplication(text))

    metrics = {
        "function_count": len(graph.functions),
        "total_loc": sum(f.loc for f in graph.functions),
        "max_complexity": max((cyclomatic_complexity(f.body)
                               for f in graph.functions), default=0),
        "longest_function": max(
            ((f.name, f.loc) for f in graph.functions),
            key=lambda t: t[1], default=(None, 0))[0],
    }
    return {"issues": issues, "metrics": metrics}


__all__ = [
    "audit_structure",
    "cyclomatic_complexity",
    "max_nesting_depth",
    "LOC_WARN",
    "COMPLEXITY_WARN",
]
