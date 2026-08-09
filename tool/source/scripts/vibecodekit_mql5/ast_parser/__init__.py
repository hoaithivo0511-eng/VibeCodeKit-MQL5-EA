"""MQL5 AST parser (proof of concept).

A lightweight, dependency-free MQL5 lexer + structure-scanner that
supplies AST-flavoured input to the lint detectors. Sits behind
``mql5-lint --use-ast`` (opt-in); the regex detectors remain the
default.

Scope (deliberately narrow for POC):

* Tokeniser strips comments + tracks ``(line, col)`` per token.
* Structure-scanner walks the token stream and emits two flat
  collections — ``VarDecl`` and ``MethodCall`` — that are the only
  shapes the three retrofitted detectors (AP-1, AP-2, AP-7) need.
* The detectors live in :mod:`vibecodekit_mql5.ast_parser.detectors`
  and produce :class:`vibecodekit_mql5.lint.Finding` objects so the
  rest of the lint pipeline (envelope JSON, SARIF, gate-report) is
  re-used unchanged.

This is **not** a full MQL5 grammar. It is the minimum surface needed
to demonstrate ``regex → AST`` parity on the 20 golden EA-bug
fixtures. A future iteration may swap the hand-written scanner for a
real tree-sitter grammar without changing the detectors' contract.
"""

from __future__ import annotations

from .detectors import (
    AST_DETECTORS,
    AST_RETROFIT_CODES,
    detect_ap1_ast,
    detect_ap2_ast,
    detect_ap7_ast,
    lint_source_ast,
)
from .nodes import MethodCall, ScanResult, Token, VarDecl
from .parser import scan_structure
from .tokenizer import tokenize

__all__ = [
    "AST_DETECTORS",
    "AST_RETROFIT_CODES",
    "MethodCall",
    "ScanResult",
    "Token",
    "VarDecl",
    "detect_ap1_ast",
    "detect_ap2_ast",
    "detect_ap7_ast",
    "lint_source_ast",
    "scan_structure",
    "tokenize",
]
