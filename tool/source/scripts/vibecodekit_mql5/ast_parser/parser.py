"""Token-stream structure scanner for MQL5.

This is **not** a full recursive-descent parser — it walks the token
stream and emits two flat collections that the .D retrofitted
detectors (AP-1, AP-2, AP-7) consume:

* ``VarDecl`` for declarations of the shape
  ``[qualifier]* TYPE IDENT (= INIT)? ;``.
* ``MethodCall`` for expressions of the shape ``obj.method(args)``.

It also records the set of ``CSafeTradeManager`` instance names (AP-1
needs them to know the SL argument index shifts left by one) and a
boolean flag ``uses_magic_registry`` that mirrors the regex
detector's fast-path (AP-7 is silenced when ``MagicRegistry`` appears
anywhere in source).

When a real tree-sitter grammar lands, this module can be replaced by
``ScanResult.from_tree(tree)`` without breaking the detector
contract.
"""

from __future__ import annotations

from .nodes import MethodCall, ScanResult, Token, VarDecl
from .tokenizer import tokenize

# Qualifiers that may precede a variable declaration. We accept zero
# or more in any order before the type token.
_QUALIFIERS: frozenset[str] = frozenset({
    "input", "extern", "static", "const", "public", "private",
    "protected", "virtual", "register", "volatile",
})

# Primitive + reserved type names. Used to disambiguate ``foo bar = 1;``
# (could be ``[type=foo, name=bar]``) from arbitrary expression / call
# statements — we only accept declarations whose type is in this set
# **or** whose qualifier is a known storage-class qualifier.
_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "void", "bool", "char", "uchar", "short", "ushort", "int", "uint",
    "long", "ulong", "float", "double", "color", "datetime", "string",
})


def _is_qualifier(tok: Token) -> bool:
    return tok.kind == "KEYWORD" and tok.text in _QUALIFIERS


def _is_type(tok: Token) -> bool:
    """A type position can be either a primitive keyword (``int``,
    ``double``, ...) or a user identifier (e.g. ``CTrade``).
    """
    if tok.kind == "KEYWORD" and tok.text in _PRIMITIVE_TYPES:
        return True
    if tok.kind == "IDENT":
        return True
    return False


def _is_op(tok: Token, text: str) -> bool:
    return tok.kind == "OP" and tok.text == text


def _scan_args(tokens: list[Token], lparen_idx: int) -> tuple[tuple[str, ...], int]:
    """Read a parenthesised arg-list starting at ``tokens[lparen_idx]``
    (which must be ``(``). Returns ``(args, idx_after_rparen)``.

    ``args`` is a tuple of arg-strings, comma-split at the OUTERMOST
    paren depth so ``f(g(1, 2), 3)`` yields two args (``g(1, 2)``,
    ``3``). Whitespace-normalised to a single space between tokens.
    """

    if not _is_op(tokens[lparen_idx], "("):
        return tuple(), lparen_idx
    depth = 1
    i = lparen_idx + 1
    current: list[str] = []
    args: list[str] = []
    while i < len(tokens):
        tok = tokens[i]
        if tok.kind == "EOF":
            break
        if _is_op(tok, "("):
            depth += 1
            current.append(tok.text)
        elif _is_op(tok, ")"):
            depth -= 1
            if depth == 0:
                if current:
                    args.append(" ".join(current).strip())
                return tuple(args), i + 1
            current.append(tok.text)
        elif _is_op(tok, ",") and depth == 1:
            args.append(" ".join(current).strip())
            current = []
        else:
            current.append(tok.text)
        i += 1
    # Unterminated paren — fall through to the original idx + 1.
    return tuple(args), lparen_idx + 1


def _read_init_value(
    tokens: list[Token], start: int
) -> tuple[str | None, str | None, int]:
    """Read a variable initialiser starting right after ``=``.

    Returns ``(init_text, init_kind, idx_after)``. ``init_kind`` is
    the kind of the FIRST token in the initialiser (e.g. ``INT`` for
    ``= 12345``, ``FLOAT`` for ``= 0.01``, ``IDENT`` for
    ``= some_fn(...)``). The .D detectors only need to look at
    the first token's kind + text to make their decision — anything
    more complex falls back to ``None``.
    """

    i = start
    parts: list[str] = []
    depth = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.kind == "EOF":
            break
        if depth == 0 and _is_op(tok, ";"):
            break
        if depth == 0 and _is_op(tok, ","):
            break
        if _is_op(tok, "(") or _is_op(tok, "{") or _is_op(tok, "["):
            depth += 1
        elif _is_op(tok, ")") or _is_op(tok, "}") or _is_op(tok, "]"):
            depth -= 1
            if depth < 0:
                break
        parts.append(tok.text)
        i += 1
    if not parts:
        return None, None, i
    first = tokens[start] if start < len(tokens) else None
    init_kind = first.kind if first is not None else None
    return " ".join(parts).strip(), init_kind, i


def scan_structure(src: str) -> ScanResult:
    """Tokenise ``src`` and walk the token stream once.

    Emits a :class:`ScanResult` with the two structure collections
    plus the auxiliary metadata the detectors need.
    """

    tokens = tokenize(src)
    n = len(tokens)

    # Pre-pass: scan all tokens for the ``MagicRegistry`` fast-path
    # flag. Doing this in the main loop misses identifiers that get
    # gobbled into a variable initialiser (e.g.
    # ``int magic = CMagicRegistry::Reserve(70001);``), so we need
    # a cheap upfront sweep that mirrors the regex detector's
    # full-source search.
    uses_magic_registry = any(
        tok.kind == "IDENT" and "MagicRegistry" in tok.text
        for tok in tokens
    )

    i = 0
    var_decls: list[VarDecl] = []
    method_calls: list[MethodCall] = []
    safe_trade_objects: set[str] = set()
    # ``at_stmt_start`` is True at file start and right after a
    # statement-terminating ``;`` or a block ``{`` / ``}``. Only at
    # that position do we accept ``IDENT IDENT`` (i.e. a user-type
    # declaration like ``CSafeTradeManager safe;``) as a var-decl
    # candidate. Inside expressions / arg lists the same shape would
    # be a false positive.
    at_stmt_start = True

    while i < n:
        tok = tokens[i]
        if tok.kind == "EOF":
            break

        # ── Method call: IDENT . IDENT ( ... ) ────────────────────
        # We do this BEFORE the var-decl probe because a leading
        # IDENT may match both shapes; method calls disambiguate via
        # the ``.`` operator immediately after the identifier.
        # The object may be a normal IDENT *or* the ``this`` keyword.
        # MQL5 class-wrapped EAs commonly call ``this.Buy(...)`` /
        # ``this.Sell(...)``; the tokenizer classifies ``this`` as a
        # KEYWORD, so without this branch the AST detector silently
        # missed those trades while the regex detector (whose ``\w+``
        # object group matches ``this``) flagged them — a real
        # divergence on complex, class-based expert advisors.
        if (
            (tok.kind == "IDENT" or (tok.kind == "KEYWORD" and tok.text == "this"))
            and i + 3 < n
            and _is_op(tokens[i + 1], ".")
            and tokens[i + 2].kind == "IDENT"
            and _is_op(tokens[i + 3], "(")
        ):
            obj_name = tok.text
            method_name = tokens[i + 2].text
            args, after = _scan_args(tokens, i + 3)
            method_calls.append(
                MethodCall(
                    obj_name=obj_name,
                    obj_line=tok.line,
                    obj_col=tok.col,
                    method_name=method_name,
                    args=args,
                )
            )
            at_stmt_start = False
            i = after
            continue

        # ── Variable declaration ──────────────────────────────────
        # Pattern: [QUAL]* TYPE IDENT (= INIT)? (, IDENT (= INIT)?)* ;
        # We accept ``QUAL TYPE IDENT`` OR ``TYPE IDENT`` where TYPE
        # must be a primitive keyword or a Capitalised identifier
        # (heuristic: starts with uppercase letter or 'C') — but we
        # also accept lowercase user identifiers IF they were
        # preceded by a known qualifier.
        qualifiers: list[str] = []
        probe = i
        while probe < n and _is_qualifier(tokens[probe]):
            qualifiers.append(tokens[probe].text)
            probe += 1
        if probe < n and _is_type(tokens[probe]):
            type_tok = tokens[probe]
            primitive = (
                type_tok.kind == "KEYWORD" and type_tok.text in _PRIMITIVE_TYPES
            )
            user_type_at_stmt_start = (
                type_tok.kind == "IDENT" and at_stmt_start
            )
            # Require either a known qualifier, a primitive type, or
            # a user IDENT immediately after a statement boundary to
            # anchor the declaration — this avoids treating
            # ``Foo bar(1);`` mid-expression as a var-decl.
            if qualifiers or primitive or user_type_at_stmt_start:
                # Detect CSafeTradeManager instances for AP-1 arg
                # index shift, mirroring lint._safe_trade_objects.
                is_safe_trade = (
                    type_tok.kind == "IDENT"
                    and type_tok.text == "CSafeTradeManager"
                )

                name_probe = probe + 1
                produced_any = False
                while name_probe < n:
                    name_tok = tokens[name_probe]
                    if name_tok.kind != "IDENT":
                        break
                    name_probe += 1
                    # Skip optional ``[size]`` array suffix.
                    if name_probe < n and _is_op(tokens[name_probe], "["):
                        bracket_depth = 1
                        name_probe += 1
                        while name_probe < n and bracket_depth > 0:
                            if _is_op(tokens[name_probe], "["):
                                bracket_depth += 1
                            elif _is_op(tokens[name_probe], "]"):
                                bracket_depth -= 1
                            name_probe += 1
                    init_text: str | None = None
                    init_kind: str | None = None
                    if name_probe < n and _is_op(tokens[name_probe], "="):
                        init_text, init_kind, name_probe = _read_init_value(
                            tokens, name_probe + 1
                        )
                    elif name_probe < n and _is_op(tokens[name_probe], "("):
                        # ``CTrade trade(args);`` — constructor-call
                        # syntax. Not a primitive init we care about;
                        # but we should NOT treat ``Foo bar();`` as a
                        # function PROTOTYPE either. Read past the
                        # parens and continue.
                        _, name_probe = _scan_args(tokens, name_probe)
                    # ``;`` or ``,`` terminates the declarator chain.
                    var_decls.append(
                        VarDecl(
                            qualifiers=tuple(qualifiers),
                            type_name=type_tok.text,
                            name=name_tok.text,
                            name_line=name_tok.line,
                            name_col=name_tok.col,
                            init_text=init_text,
                            init_kind=init_kind,
                        )
                    )
                    if is_safe_trade:
                        safe_trade_objects.add(name_tok.text)
                    produced_any = True
                    if name_probe < n and _is_op(tokens[name_probe], ","):
                        name_probe += 1
                        continue
                    break
                if produced_any:
                    # Advance past the terminating ``;`` if present.
                    # Do NOT fast-forward across ``{ ... }`` — function
                    # bodies must be scanned by the outer loop so the
                    # method-call detector sees ``obj.method(...)``
                    # calls inside them.
                    if name_probe < n and _is_op(tokens[name_probe], ";"):
                        at_stmt_start = True
                        name_probe += 1
                    else:
                        at_stmt_start = False
                    i = name_probe
                    continue

        # Track statement boundaries for the user-IDENT var-decl
        # heuristic above.
        if _is_op(tok, ";") or _is_op(tok, "{") or _is_op(tok, "}"):
            at_stmt_start = True
        elif tok.kind != "PREPROC":
            at_stmt_start = False

        i += 1

    return ScanResult(
        var_decls=tuple(var_decls),
        method_calls=tuple(method_calls),
        safe_trade_objects=frozenset(safe_trade_objects),
        uses_magic_registry=uses_magic_registry,
    )
