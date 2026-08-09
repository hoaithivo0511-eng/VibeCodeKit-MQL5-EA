"""AST node dataclasses for the MQL5 lightweight scanner.

These are intentionally narrow — they represent only the structures
the .D retrofitted detectors (AP-1, AP-2, AP-7) need. They are
NOT a full MQL5 AST. When a real tree-sitter grammar lands, these
dataclasses can be re-derived from the grammar's parse tree without
breaking the detector contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Token:
    """A single MQL5 lexeme.

    ``kind`` is one of:
        ``IDENT``   user identifier (e.g. ``trade``, ``sl_pips``, ``magic``)
        ``KEYWORD`` MQL5 reserved word (e.g. ``input``, ``int``, ``void``)
        ``INT``     integer literal (decimal or hex)
        ``FLOAT``   floating-point literal
        ``STRING``  string literal
        ``OP``      single- or multi-char operator / delimiter
        ``PREPROC`` ``#include`` / ``#property`` etc.
        ``EOF``     end-of-input sentinel
    """

    kind: str
    text: str
    line: int
    col: int


@dataclass(frozen=True)
class VarDecl:
    """A variable declaration discovered at any scope.

    Covers shapes like::

        input  int    sl_pips = 3;
        extern double risk    = 0.5;
        int           magic   = 12345;

    Position fields point at the IDENTIFIER token, not the qualifier /
    type, so detectors that need to report at the name (matching the
    regex behaviour) can do so directly.
    """

    qualifiers: tuple[str, ...]
    type_name: str
    name: str
    name_line: int
    name_col: int
    init_text: str | None
    init_kind: str | None  # 'INT' | 'FLOAT' | 'STRING' | 'IDENT' | None


@dataclass(frozen=True)
class MethodCall:
    """A method-call expression of the shape ``obj.method(arg, arg, ...)``.

    ``obj_line`` / ``obj_col`` mark the object identifier so detectors
    can report at the same position the regex would (the start of the
    object name, e.g. the ``t`` in ``trade.Buy(...)``).
    """

    obj_name: str
    obj_line: int
    obj_col: int
    method_name: str
    args: tuple[str, ...]  # raw arg text, comma-split at top level


@dataclass(frozen=True)
class ScanResult:
    """Output of :func:`vibecodekit_mql5.ast_parser.parser.scan_structure`.

    Only contains the structures the .D detectors consume.
    """

    var_decls: tuple[VarDecl, ...] = field(default_factory=tuple)
    method_calls: tuple[MethodCall, ...] = field(default_factory=tuple)
    safe_trade_objects: frozenset[str] = field(default_factory=frozenset)
    # Set to True when any token of the form ``MagicRegistry...`` appears,
    # so AP-7 can be silenced (mirrors the regex detector's fast-path).
    uses_magic_registry: bool = False
