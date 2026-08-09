"""Deterministic, provably-safe source patches for the compile-repair loop.

The loop must never fabricate a compile success, so automated source mutation is
restricted to a single, mechanically-safe class: inserting a missing statement
terminator (``;``) at the exact ``file:line`` MetaEditor reported, and only when
the target line has a sane insertion point. Every patch is:

* confined to ``source_root`` (path-containment check, no escaping the project),
* backed up before mutation (when ``backup_dir`` is given),
* recorded with a machine-readable reason (applied or why skipped).

After patching, the loop re-runs the *real* compiler; ``compile_ok`` still comes
only from MetaEditor evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Only this issue class is eligible for automatic mutation.
SAFE_PATCH_CODES = ("semicolon_expected",)


def _resolve_in_root(file_str: str, root: Path) -> Path | None:
    cand = Path(file_str)
    if not cand.is_absolute():
        cand = root / file_str
    try:
        cand = cand.resolve()
    except Exception:
        return None
    if cand == root or root in cand.parents:
        return cand
    return None


def _insert_semicolon(line: str) -> str | None:
    """Return the line with a ';' inserted before trailing whitespace/newline.

    Returns None when there is no safe insertion point (already terminated,
    opens/closes a block, ends in a comma/continuation, blank, or a comment).
    """
    newline = ""
    body = line
    if body.endswith("\r\n"):
        newline, body = "\r\n", body[:-2]
    elif body.endswith("\n"):
        newline, body = "\n", body[:-1]
    code = body.rstrip()
    trailing_ws = body[len(code):]
    if not code:
        return None
    stripped = code.lstrip()
    if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*") or stripped.startswith("/*"):
        return None
    if code.endswith((";", "{", "}", ",", "\\", ":", ")")) and not code.endswith("()"):
        # ')' alone is ambiguous (could be a control header); only refuse here.
        if code.endswith(")"):
            return None
        return None
    return code + ";" + trailing_ws + newline


def apply_safe_patches(
    hints: list[dict[str, Any]],
    *,
    source_root: str | Path,
    backup_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Apply the safe subset of repair hints; return one record per attempt."""
    root = Path(source_root).resolve()
    backup = Path(backup_dir) if backup_dir else None
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for h in hints:
        if not h.get("auto_patch_safe"):
            continue
        rec: dict[str, Any] = {
            "file": h.get("file"),
            "line": h.get("line"),
            "code": h.get("code"),
            "applied": False,
            "reason": "",
        }
        if h.get("code") not in SAFE_PATCH_CODES:
            rec["reason"] = "unsupported_safe_patch"
            results.append(rec)
            continue
        f, ln = h.get("file"), h.get("line")
        if not f or not isinstance(ln, int):
            rec["reason"] = "missing_file_or_line"
            results.append(rec)
            continue
        cand = _resolve_in_root(f, root)
        if cand is None:
            rec["reason"] = "outside_source_root"
            results.append(rec)
            continue
        if not cand.is_file():
            rec["reason"] = "file_not_found"
            results.append(rec)
            continue
        key = (str(cand), ln)
        if key in seen:
            rec["reason"] = "already_patched_this_pass"
            results.append(rec)
            continue
        lines = cand.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        if ln < 1 or ln > len(lines):
            rec["reason"] = "line_out_of_range"
            results.append(rec)
            continue
        patched = _insert_semicolon(lines[ln - 1])
        if patched is None:
            rec["reason"] = "no_safe_insertion_point"
            results.append(rec)
            continue
        if backup is not None:
            backup.mkdir(parents=True, exist_ok=True)
            safe_name = str(cand.relative_to(root)).replace("/", "__") if (cand == root or root in cand.parents) else cand.name
            dest = backup / f"{safe_name}.orig"
            if not dest.exists():
                dest.write_text("".join(lines), encoding="utf-8")
            rec["backup"] = str(dest)
        lines[ln - 1] = patched
        cand.write_text("".join(lines), encoding="utf-8")
        seen.add(key)
        rec["applied"] = True
        rec["reason"] = "semicolon_inserted"
        rec["new_line"] = patched.rstrip("\r\n")
        results.append(rec)

    return results


def any_applied(records: list[dict[str, Any]]) -> bool:
    return any(r.get("applied") for r in records)
