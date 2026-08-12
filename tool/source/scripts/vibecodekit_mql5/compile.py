r"""mql5-compile — canonical MetaEditor compile front end.

Native/Wine execution is kept here for backward compatibility; release-grade
orchestration may select other backends through the higher-level runner. All
MetaEditor log parsing and artifact policy is delegated to ``compile_core`` so
local, remote and GitHub paths cannot disagree about 0-error/0-warning success.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .compile_core import (
    CompileFailureCode,
    CompilePolicy,
    evaluate_compile_files,
    parse_metaeditor_log,
    read_metaeditor_log,
)
from .env_paths import resolve_metaeditor_path


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
    error_count: int = 0
    warning_count: int = 0
    result_summary: str | None = None
    failure_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_result(evaluation) -> CompileResult:
    return CompileResult(
        success=evaluation.success,
        errors=list(evaluation.errors),
        warnings=list(evaluation.warnings),
        ex5_path=evaluation.ex5_path,
        raw_log=evaluation.raw_log,
        error_count=evaluation.error_count,
        warning_count=evaluation.warning_count,
        result_summary=evaluation.result_summary,
        failure_codes=list(evaluation.failure_codes),
    )


def _to_wine_path(p: Path) -> str:
    if sys.platform.startswith("win"):
        return str(p)
    posix = p.resolve().as_posix()
    return "Z:" + posix.replace("/", "\\")


def _decode_log(log: Path) -> str:
    return read_metaeditor_log(log)


def parse_log(text: str, *, max_warnings: int = 0) -> CompileResult:
    """Pure compatibility parser using the canonical RC7 policy."""
    evaluation = parse_metaeditor_log(
        text,
        policy=CompilePolicy(max_warnings=max_warnings, require_ex5=False),
    )
    return _to_result(evaluation)


def compile_mq5(
    mq5_path: Path,
    metaeditor: str | None = None,
    log_path: Path | None = None,
    timeout: int = 180,
    *,
    max_warnings: int = 0,
) -> CompileResult:
    if not mq5_path.exists():
        return CompileResult(
            success=False,
            errors=[f"file not found: {mq5_path}"],
            failure_codes=[CompileFailureCode.SOURCE_STAGE_FAILED.value],
        )

    log_path = log_path or mq5_path.with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    ex5 = mq5_path.with_suffix(".ex5")
    if ex5.exists():
        ex5.unlink()

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
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            errors=[f"compile timed out after {timeout}s"],
            failure_codes=[CompileFailureCode.TIMEOUT.value],
        )
    except FileNotFoundError as exc:
        return CompileResult(
            success=False,
            errors=[f"MetaEditor not invocable: {exc}"],
            failure_codes=[CompileFailureCode.INVOCATION_FAILED.value],
        )

    evaluation = evaluate_compile_files(
        log_path,
        ex5,
        policy=CompilePolicy(max_warnings=max_warnings),
    )
    return _to_result(evaluation)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-compile", description=__doc__.splitlines()[0])
    p.add_argument("mq5", help="path to .mq5 source")
    p.add_argument(
        "--metaeditor",
        default=None,
        help="override MetaEditor64.exe path (else $METAEDITOR_PATH or default)",
    )
    p.add_argument("--log", default=None, help="output log file (defaults to <mq5>.log)")
    p.add_argument("--json", action="store_true", help="emit structured JSON to stdout")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument(
        "--max-warnings",
        type=int,
        default=0,
        help="maximum MetaEditor warnings allowed; RC7 house policy defaults to 0",
    )
    args = p.parse_args(argv)

    mq5 = Path(args.mq5)
    log = Path(args.log) if args.log else None
    result = compile_mq5(
        mq5,
        args.metaeditor,
        log,
        args.timeout,
        max_warnings=max(0, args.max_warnings),
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        for w in result.warnings:
            print("WARN:", w, file=sys.stderr)
        for e in result.errors:
            print("ERROR:", e, file=sys.stderr)
        if result.success:
            print(f"OK: {result.ex5_path}")
        else:
            if result.failure_codes:
                print("FAIL:", ",".join(result.failure_codes), file=sys.stderr)
            else:
                print("FAIL", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
