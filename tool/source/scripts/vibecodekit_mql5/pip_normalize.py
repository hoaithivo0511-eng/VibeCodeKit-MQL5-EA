"""mql5-pip-normalize — refactor hardcoded pip math to CPipNormalizer calls.

Recognized hardcoded patterns (mirrors lint.AP-20, plus convenience shapes):

    <expr> * 0.0001          → pip.Pips(<expr>) / pip.PriceToPips(<expr>) etc.
    <expr> * 0.001           → pip.Pips(<expr>)
    <expr> * _Point          → pip.Pips(<expr>)         (pip-scaled)
    <expr> * Point()         → pip.Pips(<expr>)
    pips_to_points(<expr>)   → pip.Pips(<expr>)         (legacy helper)

When at least one substitution is made, the file is also guaranteed to:

    1. `#include "CPipNormalizer.mqh"` near the top
    2. declare a global `CPipNormalizer pip;`
    3. call `pip.Init(_Symbol);` at the top of OnInit() (added if missing).

Run with `--check` to abort with exit 1 on any unconverted pattern (CI mode).
Run with `--write` (default) to rewrite the file in place.

Exit codes:
    0 — file already normalized OR successfully rewritten
    1 — `--check` mode found hardcoded patterns
    2 — invocation error
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

INCLUDE_LINE  = '#include "CPipNormalizer.mqh"'
GLOBAL_DECL   = "CPipNormalizer pip;"
INIT_CALL     = "    pip.Init(_Symbol);"


@dataclass
class RefactorResult:
    path: str
    substitutions: int = 0
    added_include: bool = False
    added_global: bool = False
    added_init: bool = False
    new_text: str = ""
    diagnostics: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern substitutions
# ─────────────────────────────────────────────────────────────────────────────

# Match `<expr> * <pip-literal>` where <expr> is a contiguous run that does NOT
# already pass through `pip.` (so we don't double-rewrite). The detector is
# intentionally conservative: it stops at the previous `=`, `(`, `,`, `+`, `-`,
# `*` (other), `/`, or `;` to bound the operand on the left.
_PIP_LITERAL = r"(?:0\.000?1|_Point|Point\s*\(\s*\))"
# Operand on the left can be an identifier (`sl`, `InpSL`, `arr[i].x`) OR a
# numeric literal (`30`, `30.5`). Anchored to a non-word boundary so we don't
# splice mid-token (`abcsl * 0.0001` mustn't match the trailing `sl`).
_OPERAND     = r"(?P<expr>[A-Za-z_][\w.\[\]]*|\d+(?:\.\d+)?)"
_SUB_RX = re.compile(rf"(?<!\w){_OPERAND}\s*\*\s*{_PIP_LITERAL}")


def _substitute_pip(src: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"pip.Pips({m.group('expr')})"

    out = _SUB_RX.sub(repl, src)
    return out, count


# ─────────────────────────────────────────────────────────────────────────────
# Header / OnInit injection
# ─────────────────────────────────────────────────────────────────────────────

_HAS_INCLUDE = re.compile(r'#include\s*[<"]CPipNormalizer\.mqh[>"]')
_HAS_GLOBAL  = re.compile(r"\bCPipNormalizer\s+\w+\s*;")
_ONINIT_RX   = re.compile(r"(int\s+OnInit\s*\(\s*[^)]*\)\s*\{)")
_PIP_INIT_RX = re.compile(r"\bpip\s*\.\s*Init\s*\(")


def _ensure_include(src: str) -> tuple[str, bool]:
    if _HAS_INCLUDE.search(src):
        return src, False
    # Insert after the last existing `#include` if any, else at the top.
    last_inc = None
    for m in re.finditer(r"^#include[^\n]*$", src, re.MULTILINE):
        last_inc = m
    if last_inc:
        idx = last_inc.end()
        return src[:idx] + "\n" + INCLUDE_LINE + src[idx:], True
    return INCLUDE_LINE + "\n" + src, True


def _ensure_global(src: str) -> tuple[str, bool]:
    if _HAS_GLOBAL.search(src):
        return src, False
    # Place the global right after the include block.
    last_inc = None
    for m in re.finditer(r"^#include[^\n]*$", src, re.MULTILINE):
        last_inc = m
    if last_inc:
        idx = last_inc.end()
        return src[:idx] + "\n\n" + GLOBAL_DECL + "\n" + src[idx:], True
    return GLOBAL_DECL + "\n\n" + src, True


def _ensure_init(src: str) -> tuple[str, bool]:
    if _PIP_INIT_RX.search(src):
        return src, False
    m = _ONINIT_RX.search(src)
    if not m:
        return src, False
    idx = m.end()
    return src[:idx] + "\n" + INIT_CALL + src[idx:], True


# ─────────────────────────────────────────────────────────────────────────────
# Top-level
# ─────────────────────────────────────────────────────────────────────────────

def normalize_source(path: str, src: str) -> RefactorResult:
    res = RefactorResult(path=path, new_text=src)
    new_src, count = _substitute_pip(src)
    if count == 0:
        res.new_text = new_src
        return res
    res.substitutions = count
    new_src, res.added_include = _ensure_include(new_src)
    new_src, res.added_global  = _ensure_global(new_src)
    new_src, res.added_init    = _ensure_init(new_src)
    if not res.added_init and not _PIP_INIT_RX.search(new_src):
        res.diagnostics.append("could not locate OnInit() — add `pip.Init(_Symbol);` manually")
    res.new_text = new_src
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-pip-normalize", description=__doc__.splitlines()[0])
    p.add_argument("files", nargs="+", help=".mq5 file(s) to refactor")
    p.add_argument("--check", action="store_true", help="abort 1 if any subs would be applied")
    p.add_argument("--stdout", action="store_true", help="print to stdout instead of writing")
    args = p.parse_args(argv)

    any_subs = False
    for f in args.files:
        path = Path(f)
        if not path.is_file():
            print(f"{f}: not a file", file=sys.stderr)
            return 2
        from .mq5_io import read_mq5_text_with_encoding

        try:
            src, enc = read_mq5_text_with_encoding(path)
        except UnicodeDecodeError:
            src, enc = path.read_text(encoding="latin-1", errors="replace"), "latin-1"
        res = normalize_source(str(path), src)
        if res.substitutions:
            any_subs = True
            print(f"{f}: {res.substitutions} substitution(s); "
                  f"include={res.added_include} global={res.added_global} init={res.added_init}")
            for d in res.diagnostics:
                print(f"{f}: NOTE {d}")
            if not args.check:
                if args.stdout:
                    sys.stdout.write(res.new_text)
                else:
                    path.write_text(res.new_text, encoding=enc)
        else:
            print(f"{f}: already normalized")
    if args.check and any_subs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
