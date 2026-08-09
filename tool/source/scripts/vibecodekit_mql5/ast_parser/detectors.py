"""AST-flavoured AP detectors (proof of concept).

Three of the regex detectors in ``lint.py`` / ``lint_best_practice.py``
are retrofitted here to operate on the structures emitted by
:func:`vibecodekit_mql5.ast_parser.parser.scan_structure`. The
remaining detectors still run as regex; the only entry-point that
exposes the AST variant is ``lint_source_ast`` (used by
``mql5-lint --use-ast``).

The detectors are written so that on the 20 golden EA-bug fixtures
they produce findings **byte-identical** to the regex versions —
same position, same severity, same message. This is pinned by
the bundled AST-parser tests.

Why AST and not regex?
  * Regex matches inside contexts the parser excludes (e.g. inside a
    string literal whose content happens to contain ``magic = 12345``).
  * Regex cannot reason about scope (e.g. silence AP-7 only when a
    given declaration's RHS calls into ``CMagicRegistry``).
  * The AST is the foundation a real tree-sitter grammar can plug
    into later; the detector contract is the same.
"""

from __future__ import annotations

from collections.abc import Callable

from ..lint import Finding
from .nodes import ScanResult
from .parser import scan_structure


def _ap1_sl_position(args: tuple[str, ...], is_safe_trade: bool) -> bool:
    """Return ``True`` iff the SL argument is non-zero / present."""
    sl_idx = 2 if is_safe_trade else 3
    if len(args) <= sl_idx:
        return False
    arg = args[sl_idx].strip()
    if arg in {"", "0", "0.0"}:
        return False
    return True


def detect_ap1_ast(path: str, _raw: str, structure: ScanResult) -> list[Finding]:
    """AP-1 No-SL: ``CTrade.Buy/Sell`` without a non-zero stop-loss arg.

    Position-equivalent to the regex detector — emits at the object
    identifier (``trade``), not the method name.
    """

    out: list[Finding] = []
    for call in structure.method_calls:
        if call.method_name not in {"Buy", "Sell"}:
            continue
        is_safe = call.obj_name in structure.safe_trade_objects
        if not _ap1_sl_position(call.args, is_safe):
            out.append(
                Finding(
                    path,
                    call.obj_line,
                    call.obj_col,
                    "ERROR",
                    "AP-1",
                    "CTrade.Buy/Sell without stop-loss",
                )
            )
    return out


_AP2_NAMES: frozenset[str] = frozenset({
    "sl_pips", "stop_loss_pips", "stop_pips",
})


def detect_ap2_ast(path: str, _raw: str, structure: ScanResult) -> list[Finding]:
    """AP-2 SL-too-tight: ``sl_pips = N`` with ``N in {1..5}``.

    Byte-identical position + message to the regex detector. Note the
    regex captured the digit class; the AST equivalent inspects the
    initialiser's ``INT`` token text.
    """

    out: list[Finding] = []
    for var in structure.var_decls:
        if var.name not in _AP2_NAMES:
            continue
        if var.init_kind != "INT":
            continue
        # Regex character class is [1-5] — we mirror it exactly.
        if var.init_text not in {"1", "2", "3", "4", "5"}:
            continue
        out.append(
            Finding(
                path,
                var.name_line,
                var.name_col,
                "WARN",
                "AP-2",
                f"SL too tight ({var.init_text} pips) — "
                f"validate against broker stops_level",
            )
        )
    return out


def detect_ap7_ast(path: str, _raw: str, structure: ScanResult) -> list[Finding]:
    """AP-7 Hardcoded-magic: ``magic[\\w]* = NNN`` (≥ 2 digits).

    Silenced when ``MagicRegistry`` appears anywhere in source —
    matches the regex detector's behaviour.
    """

    if structure.uses_magic_registry:
        return []
    out: list[Finding] = []
    for var in structure.var_decls:
        if not var.name.startswith("magic"):
            continue
        if var.init_kind != "INT":
            continue
        if var.init_text is None:
            continue
        # Regex requires ≥ 2 digits.
        if len(var.init_text) < 2:
            continue
        if not var.init_text.lstrip("0x").lstrip("0X").lstrip("-").isalnum():
            # Skip hex-flavoured init for byte-identical regex parity.
            continue
        if not var.init_text.isdigit():
            continue
        out.append(
            Finding(
                path,
                var.name_line,
                var.name_col,
                "WARN",
                "AP-7",
                f"Hardcoded magic {var.init_text} — "
                f"use CMagicRegistry.Reserve()",
            )
        )
    return out


# Public detector registry — keyed identically to ``lint._ALL_DETECTORS``.
AST_DETECTORS: list[tuple[str, Callable[[str, str, ScanResult], list[Finding]]]] = [
    ("AP-1", detect_ap1_ast),
    ("AP-2", detect_ap2_ast),
    ("AP-7", detect_ap7_ast),
]

# AP codes the AST path handles; everything else falls through to the
# regex pipeline via ``lint.lint_source``.
AST_RETROFIT_CODES: frozenset[str] = frozenset(c for c, _ in AST_DETECTORS)


def lint_source_ast(path: str, raw: str) -> list[Finding]:
    """Run the AST-retrofitted detectors PLUS the still-regex
    detectors over ``raw``.

    For the 3 retrofitted codes (AP-1, AP-2, AP-7) the AST output
    replaces the regex output. All other detectors come straight from
    ``lint.lint_source``.
    """

    # Late import to avoid circular module load.
    from ..lint import _strip_comments, lint_source

    src_no_comments = _strip_comments(raw)
    structure = scan_structure(src_no_comments)

    ast_findings: list[Finding] = []
    for _code, fn in AST_DETECTORS:
        ast_findings.extend(fn(path, raw, structure))

    regex_findings = [
        f for f in lint_source(path, raw) if f.code not in AST_RETROFIT_CODES
    ]

    out = ast_findings + regex_findings
    out.sort(key=lambda f: (f.line, f.col, f.code))
    return out
