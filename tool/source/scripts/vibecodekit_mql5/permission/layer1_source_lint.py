"""Permission Layer 1 — SOURCE-LINT.

Pre-commit-style format / syntax pre-check on the .mq5 / .mqh source.
The kit runs this layer before invoking MetaEditor compile (which is
slow). Layer 1 is allowed to fail the entire pipeline; nothing downstream
should rely on a broken parse.

Checks performed:
  - file is UTF-8 / UTF-16-LE decodable (MetaEditor emits both)
  - tabs and trailing whitespace are not catastrophic
  - braces balance (very lightweight, comments stripped)
  - file ends with a newline

All checks are deliberately cheap so the layer can run as a git hook.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_COMMENT_LINE = re.compile(r"//.*$", flags=re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", flags=re.DOTALL)
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'")


def _decode(path: Path) -> str:
    """Decode a .mq5/.mqh source file. Delegates to :mod:`mq5_io`.

    Kept as a thin wrapper so existing callers that imported this name
    directly still work — the kit's canonical helper is now
    :func:`vibecodekit_mql5.mq5_io.read_mq5_text`.
    """
    from ..mq5_io import read_mq5_text

    return read_mq5_text(path)


def _strip_comments(src: str) -> str:
    src = _COMMENT_BLOCK.sub("", src)
    src = _COMMENT_LINE.sub("", src)
    return src


def _strip_literals(src: str) -> str:
    """Blank out string/char literal bodies so braces embedded inside them
    don't skew the lightweight brace-balance check.

    Complex EAs legitimately embed ``{``/``}`` in string literals — e.g.
    ``Print(\"grid level {\")`` or inline JSON payloads sent via
    ``WebRequest`` — which previously tripped a false ``braces
    unbalanced`` failure and blocked the whole build pipeline at Layer 1.
    """
    src = _STRING_LITERAL.sub('""', src)
    src = _CHAR_LITERAL.sub("''", src)
    return src


def lint_source(path: Path) -> dict:
    issues: list[str] = []
    try:
        text = _decode(path)
    except UnicodeDecodeError:
        return {"ok": False, "issues": ["cannot decode source file"], "path": str(path)}

    if not text.endswith("\n"):
        issues.append("file does not end with newline")

    stripped = _strip_literals(_strip_comments(text))
    if stripped.count("{") != stripped.count("}"):
        issues.append(
            f"braces unbalanced: open={stripped.count('{')} close={stripped.count('}')}"
        )

    if "\t" in text:
        issues.append("file contains hard tabs (prefer 3-space indent)")

    return {"ok": not issues, "issues": issues, "path": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer1")
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    result = lint_source(args.source)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
