"""Static enforcement of the kit's stdout/stderr I/O contract.

Contract
--------
``stdout`` is the *machine channel*: a tool prints there only its primary
payload — a single JSON envelope (``_agent_io.emit``), a SARIF document, or
the intended human report. EVERY diagnostic line — errors, warnings,
progress, deprecation notices, "unknown X" guards — must go to ``stderr``
(use :func:`_agent_io.error` / ``warn`` / ``info`` / ``diag`` or
``print(..., file=sys.stderr)``). That way an agent that pipes ``stdout``
never has its JSON polluted by log noise, and ``tool > out.json`` captures
only the payload.

This module statically scans every package module for the load-bearing
violation: a **diagnostic string printed to stdout**. A ``print()`` with no
``file=`` keyword whose first argument is a string / f-string literal that
reads like a diagnostic (``error``, ``warning``, ``unknown``, ``failed`` …)
is flagged. Pure ``usage:``/help banners are exempt because argparse-style
help legitimately goes to stdout when explicitly requested.

The check is intentionally conservative — it reports only high-confidence
leaks so it can run as a hard CI gate (``mql5-doctor --check-io-contract``)
without false positives blocking the build.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = Path(__file__).resolve().parent

# A first-argument literal matching this pattern is treated as a diagnostic
# that belongs on stderr. Case-insensitive, word-ish boundaries.
_DIAGNOSTIC = re.compile(
    r"(?i)(\berror\b|err:|\bwarn(ing)?\b|\bunknown\b|\bcannot\b|can't"
    r"|\bfailed\b|fail:|not found|no such|\bmissing\b|\binvalid\b"
    r"|traceback|deprecat)"
)
# Literals that look like help/usage banners are allowed on stdout.
_ALLOWED_PREFIX = re.compile(r"(?i)^\s*(usage:|help:)")


@dataclass(frozen=True)
class Violation:
    path: str  # repo-relative
    line: int
    snippet: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: diagnostic on stdout: {self.snippet!r}"


def _literal_text(node: ast.AST) -> str | None:
    """Return the static string content of a str / f-string node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [
            v.value
            for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        ]
        return "".join(parts) if parts else ""
    return None


def _print_goes_to_stdout(call: ast.Call) -> bool:
    """True when this ``print(...)`` call targets stdout (no ``file=`` kw)."""
    for kw in call.keywords:
        if kw.arg == "file":
            return False  # explicit file= (stderr or elsewhere)
    return True


def scan_source(source: str, rel_path: str) -> list[Violation]:
    """Return diagnostic-to-stdout violations in one module's source."""
    violations: list[Violation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.args
        ):
            continue
        if not _print_goes_to_stdout(node):
            continue
        text = _literal_text(node.args[0])
        if text is None:
            continue  # dynamic content - not statically a diagnostic
        if _ALLOWED_PREFIX.search(text):
            continue
        if _DIAGNOSTIC.search(text):
            violations.append(
                Violation(rel_path, node.lineno, text.strip()[:80])
            )
    return violations


def scan_package(package_dir: Path | None = None, repo_root: Path | None = None) -> list[Violation]:
    """Scan every ``.py`` module under the package for violations."""
    package_dir = package_dir or PACKAGE_DIR
    repo_root = repo_root or REPO_ROOT
    found: list[Violation] = []
    for path in sorted(package_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        found.extend(scan_source(path.read_text(encoding="utf-8"), rel))
    return found
