"""Shared I/O helper for reading user-supplied MQL5 source files.

MetaEditor saves ``.mq5`` / ``.mqh`` files in either UTF-8 or
**UTF-16-LE** (the latter is in fact MetaEditor's *default* save mode
since build 5000+). When kit modules read those files with the
naive ``Path.read_text(encoding="utf-8", errors="replace")`` pattern
they silently turn every UTF-16 byte pair into ``\\ufffd`` runs, which
makes the regex-based lint / parser detectors fire **zero hits** on
otherwise-broken EAs. The user then ships an unverified bot.

This module is the single source of truth for "read an EA source
into text". Everything downstream — lint, anti-pattern detection,
``parse_inputs``, ``method_hiding_check``, ``trader_check``,
``docs_bundle``, ``auto_fix`` and friends — should call
:func:`read_mq5_text` instead of opening the file directly.

The fallback ladder matches what ``mql5-permission`` layer-1 already
uses (utf-8 → utf-16-le → utf-16 → latin-1) plus a BOM strip so
regex anchors at ``^`` keep working on UTF-16-LE files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

PathLike = Union[Path, str]

#: Tried in order. UTF-16-LE comes before UTF-16 (with BOM auto-detect)
#: because the latter accepts pure-UTF-8 ASCII too — wrong call would
#: misclassify a perfectly valid UTF-8 file.
_FALLBACK_ENCODINGS: tuple[str, ...] = ("utf-8", "utf-16-le", "utf-16", "latin-1")


def decode_mq5_bytes(raw: bytes) -> tuple[str, str]:
    """Decode raw .mq5/.mqh bytes, returning ``(text, encoding_used)``.

    The encoding string is informational: callers that re-write the
    file (e.g. :mod:`auto_fix`) can use it to preserve the on-disk
    encoding instead of silently transcoding the user's source.

    Raises :class:`UnicodeDecodeError` only if *every* fallback fails,
    which in practice means the file is binary garbage.
    """
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        # Honour explicit BOM first — `utf-16` decoder handles both
        # endians automatically and strips the BOM.
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    # BOM-less UTF-16-LE ASCII decodes 'successfully' as UTF-8 because the
    # interleaved NUL bytes are valid codepoints, returning garbage full of
    # \x00 that breaks every ^/\b regex anchor downstream. Sniff the NUL
    # signature and try the UTF-16 codecs first in that case.
    sniff = raw[:64]
    if sniff and sniff.count(b"\x00") * 4 >= len(sniff):
        for enc in ("utf-16-le", "utf-16"):
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue
            if text.startswith("\ufeff"):
                text = text[1:]
            return text, enc
    for enc in _FALLBACK_ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        # Reject a UTF-8 decode that still carries NUL runs (almost certainly
        # a mis-decoded UTF-16 stream) and fall through to the UTF-16 codecs.
        if enc == "utf-8" and "\x00" in text:
            continue
        # Strip a leftover BOM (UTF-8 BOM decodes to ``\ufeff`` and
        # would otherwise break regex anchors at the file start).
        if text.startswith("\ufeff"):
            text = text[1:]
        return text, enc
    raise UnicodeDecodeError(
        "mq5_io", raw, 0, 1, "could not decode file with any known encoding"
    )


def read_mq5_text(path: PathLike, *, errors: str = "strict") -> str:
    """Read an EA source file into a text string.

    Parameters
    ----------
    path
        Filesystem path to the ``.mq5`` / ``.mqh`` source.
    errors
        ``"strict"`` (default) re-raises :class:`UnicodeDecodeError`
        when every encoding fallback fails. Pass ``"replace"`` to
        fall back to ``latin-1`` byte-for-byte so the call **never**
        raises (some callers — e.g. ``auto_fix`` running on a corrupt
        EA — prefer noise over a hard crash).

    Returns
    -------
    str
        The decoded source. A leading BOM is stripped.
    """
    p = Path(path)
    raw = p.read_bytes()
    try:
        text, _ = decode_mq5_bytes(raw)
        return text
    except UnicodeDecodeError:
        if errors == "replace":
            return raw.decode("latin-1", errors="replace")
        raise


def read_mq5_text_with_encoding(path: PathLike) -> tuple[str, str]:
    """Variant that returns both text and the encoding used.

    Useful for modules that round-trip the file back to disk
    (:mod:`auto_fix`) — they can keep the file in its original
    on-disk encoding instead of transcoding the user's source.
    """
    raw = Path(path).read_bytes()
    return decode_mq5_bytes(raw)


__all__ = [
    "decode_mq5_bytes",
    "read_mq5_text",
    "read_mq5_text_with_encoding",
]
