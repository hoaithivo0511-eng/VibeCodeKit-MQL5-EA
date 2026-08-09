r"""mql5-compile — thin wrapper around MetaEditor's CLI compile mode.

Invokes:
    metaeditor64.exe /compile:<mq5> /log:<log>

…then parses the (UTF-16-LE encoded) log to a structured result dict.
On Linux, prepends ``xvfb-run -a wine`` so it Just Works under the
same Wine prefix the environment setup created at $WINEPREFIX (default
``/home/ubuntu/.wine-mql5``).

The MQL5 docs say that the editor uses the Wine drive Z: mapping for
non-C: paths; we translate any host path that starts with ``/`` to its
``Z:\`` Wine equivalent before passing it in.

Exit codes:
    0 — compile succeeded (0 errors)
    1 — compile produced errors
    2 — invocation error (bad path, MetaEditor not found, etc.)
"""
from __future__ import annotations

from .env_paths import resolve_metaeditor_path

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_METAEDITOR_LINUX = (
    "/home/ubuntu/.wine-mql5/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe"
)


@dataclass
class CompileResult:
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ex5_path: str | None = None
    raw_log: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _to_wine_path(p: Path) -> str:
    """Translate a host filesystem path to its Z:\\ Wine equivalent."""
    if sys.platform.startswith("win"):
        return str(p)
    posix = p.resolve().as_posix()
    return "Z:" + posix.replace("/", "\\")


def _decode_log(log: Path) -> str:
    if not log.exists():
        return ""
    raw = log.read_bytes()
    # MetaEditor writes UTF-16-LE with a BOM under standard configs; fall back
    # progressively to other encodings. `errors='replace'` would make the loop
    # dead code (decode never raises), so we let UnicodeDecodeError bubble.
    for enc in ("utf-16-le", "utf-16", "utf-8"):
        try:
            return raw.decode(enc).lstrip("\ufeff")
        except UnicodeDecodeError:
            continue
    # Last resort — latin-1 cannot fail, decodes byte-for-byte.
    return raw.decode("latin-1", errors="replace")


def parse_log(text: str) -> CompileResult:
    """Pure log parser — no filesystem side-effects. Easy to unit-test."""
    errors: list[str] = []
    warnings: list[str] = []
    result_line = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("result:"):
            result_line = line
            continue
        if ": error " in low:
            errors.append(line)
        elif ": warning " in low:
            warnings.append(line)

    success = False
    if result_line:
        # MetaEditor prints `Result: <N> errors, <M> warnings, ...`.
        # Match on `\b0 errors?\b` so `10 errors` / `20 errors` / `100 errors`
        # are not falsely classified as successful builds.
        if re.search(r"\b0 errors?\b", result_line.lower()):
            success = True
    else:
        # No ``Result:`` line means MetaEditor never finished (empty log,
        # missing binary, sandbox crash, wrong $METAEDITOR_PATH, etc.).
        # Previously the parser fell through to ``success = True`` when no
        # error lines were present, producing a false positive where the
        # build stage reported OK but no ``.ex5`` was actually produced.
        # Surface the missing summary as a hard failure with an explicit
        # error so upstream stages can react.
        errors.append(
            "compile: MetaEditor log has no 'Result:' summary line "
            "(binary may not have run — check METAEDITOR_PATH and Wine)"
        )
    return CompileResult(success=success, errors=errors, warnings=warnings, raw_log=text)


def compile_mq5(
    mq5_path: Path,
    metaeditor: str | None = None,
    log_path: Path | None = None,
    timeout: int = 180,
) -> CompileResult:
    if not mq5_path.exists():
        return CompileResult(success=False, errors=[f"file not found: {mq5_path}"])

    log_path = log_path or mq5_path.with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    me = resolve_metaeditor_path(metaeditor) or DEFAULT_METAEDITOR_LINUX

    if sys.platform.startswith("linux"):
        mq5_arg = f"/compile:{_to_wine_path(mq5_path)}"
        log_arg = f"/log:{_to_wine_path(log_path)}"
        wine = shutil.which("wine") or "wine"
        xvfb = shutil.which("xvfb-run")
        cmd = [xvfb, "-a", wine, me, mq5_arg, log_arg] if xvfb else [wine, me, mq5_arg, log_arg]
    else:
        cmd = [me, f"/compile:{mq5_path}", f"/log:{log_path}"]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CompileResult(success=False, errors=[f"compile timed out after {timeout}s"])
    except FileNotFoundError as exc:
        return CompileResult(success=False, errors=[f"MetaEditor not invocable: {exc}"])

    result = parse_log(_decode_log(log_path))
    ex5 = mq5_path.with_suffix(".ex5")
    if result.success and ex5.exists():
        result.ex5_path = str(ex5)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-compile", description=__doc__.splitlines()[0])
    p.add_argument("mq5", help="path to .mq5 source")
    p.add_argument("--metaeditor", default=None,
                   help="override MetaEditor64.exe path (else $METAEDITOR_PATH or default)")
    p.add_argument("--log", default=None, help="output log file (defaults to <mq5>.log)")
    p.add_argument("--json", action="store_true", help="emit structured JSON to stdout")
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args(argv)

    mq5 = Path(args.mq5)
    log = Path(args.log) if args.log else None
    result = compile_mq5(mq5, args.metaeditor, log, args.timeout)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        for w in result.warnings:
            print("WARN:", w, file=sys.stderr)
        for e in result.errors:
            print("ERROR:", e, file=sys.stderr)
        if result.success:
            print(f"OK: {result.ex5_path or '(no .ex5)'}")
        else:
            print("FAIL", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
