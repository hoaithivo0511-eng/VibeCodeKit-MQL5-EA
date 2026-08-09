"""MQL5 tokeniser — strips comments, tracks ``(line, col)`` per token.

The lexer is hand-written rather than relying on ``re.finditer`` over
the full source because we need accurate column tracking AFTER each
multi-line skip (block comment, multi-line preprocessor continuation,
string with embedded ``\\n``). A precompiled master regex is used to
pick the longest match at each position; we then advance the cursor
by the matched length and update ``(line, col)`` manually.

The kit's MQL5 dialect is a strict subset of C++ for our detection
purposes, so we mostly mirror C++ tokenisation with a small set of
MQL5-specific keywords (``input``, ``extern``, ``datetime`` etc.).
"""

from __future__ import annotations

import re

from .nodes import Token

# Single-line + block comments are stripped at the tokeniser layer —
# detectors should never see commented-out code, mirroring the
# behaviour of ``lint._strip_comments``.
_TOKEN_RE = re.compile(
    r"""
    (?P<COMMENT_BLOCK>/\*[\s\S]*?\*/)
    | (?P<COMMENT_LINE>//[^\n]*)
    | (?P<PREPROC>\#[A-Za-z_][A-Za-z_0-9]*(?:\\\r?\n|[^\n])*)
    | (?P<STRING>"(?:[^"\\\n]|\\.)*")
    | (?P<CHAR>'(?:[^'\\\n]|\\.)*')
    | (?P<FLOAT>\d+\.\d+(?:[eE][+\-]?\d+)?)
    | (?P<HEXINT>0[xX][0-9A-Fa-f]+)
    | (?P<INT>\d+)
    | (?P<IDENT>[A-Za-z_][A-Za-z_0-9]*)
    | (?P<OP>==|!=|<=|>=|<<=|>>=|<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=
              |&&|\|\||\+\+|--|->|::|[+\-*/%=<>!&|^~?:,;(){}\[\].])
    | (?P<WS>[ \t]+)
    | (?P<NEWLINE>\n)
    """,
    re.VERBOSE,
)


# MQL5 keywords (close to C++ plus MQL5 specifics like ``input``).
# Not all of these need recognition by the detectors, but flagging them
# as ``KEYWORD`` (rather than ``IDENT``) avoids spurious matches in the
# var-decl scanner — e.g. ``return x;`` must not be misread as
# ``[type=return, name=x]``.
KEYWORDS: frozenset[str] = frozenset({
    # Storage / visibility / qualifiers
    "input", "extern", "static", "const", "public", "private", "protected",
    "virtual", "override", "final", "sealed", "register", "volatile",
    # Primitive types (MQL5)
    "void", "bool", "char", "uchar", "short", "ushort", "int", "uint",
    "long", "ulong", "float", "double", "color", "datetime", "string",
    "enum", "struct", "class", "union",
    # Control flow
    "if", "else", "while", "for", "do", "switch", "case", "default",
    "break", "continue", "return", "goto",
    # Literals & misc reserved
    "true", "false", "NULL", "new", "delete", "sizeof", "this", "typename",
    "operator", "template", "namespace", "using", "typedef",
})


def tokenize(src: str) -> list[Token]:
    """Tokenise an MQL5 source string.

    Strips block + line comments and standalone whitespace. Returns a
    list of :class:`Token` ending with a synthetic ``EOF`` token whose
    position is the post-source ``(line, col)``.

    ``col`` is 1-indexed and aligns with the regex detectors'
    ``_line_col`` helper in ``lint.py``.
    """

    tokens: list[Token] = []
    pos = 0
    line = 1
    col = 1
    src_len = len(src)
    while pos < src_len:
        m = _TOKEN_RE.match(src, pos)
        if not m:
            # Skip a single un-matchable char to keep forward progress.
            ch = src[pos]
            pos += 1
            if ch == "\n":
                line += 1
                col = 1
            else:
                col += 1
            continue

        kind = m.lastgroup
        text = m.group()

        if kind in ("WS", "NEWLINE", "COMMENT_BLOCK", "COMMENT_LINE"):
            # Discard whitespace + comments; just advance position/line.
            pass
        elif kind == "PREPROC":
            tokens.append(Token("PREPROC", text, line, col))
        elif kind == "HEXINT":
            tokens.append(Token("INT", text, line, col))
        elif kind == "IDENT":
            t_kind = "KEYWORD" if text in KEYWORDS else "IDENT"
            tokens.append(Token(t_kind, text, line, col))
        else:
            # FLOAT / INT / STRING / OP
            tokens.append(Token(kind, text, line, col))

        # Advance position + (line, col) over the matched substring.
        newline_count = text.count("\n")
        if newline_count:
            line += newline_count
            col = len(text) - text.rfind("\n")
        else:
            col += len(text)
        pos = m.end()

    tokens.append(Token("EOF", "", line, col))
    return tokens
