r"""mql5-compile — canonical multi-backend compile front end.

The CLI keeps the historical local/Wine path while adding GitHub Actions and
remote-worker execution behind one stable surface. All MetaEditor log parsing
uses ``compile_core``. ``auto`` prefers native local Windows, GitHub Actions,
configured remote worker, then Wine development compile; if none is available
the command reports UNTESTABLE instead of fabricating success.
"""
from __future__ import annotations

import argparse
import json
import os
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


def _configured_github(args) -> tuple[str, str, str | None]:
    repository = (
        args.github_repo
        or os.environ.get("VKMQL_GITHUB_REPOSITORY")
        or os.environ.get("GITHUB_REPOSITORY")
        or ""
    )
    ref = (
        args.github_ref
        or os.environ.get("VKMQL_GITHUB_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or ""
    )
    token = (
        args.github_token
        or os.environ.get("VKMQL_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    return repository, ref, token


def _select_backend(args) -> str | None:
    if args.backend != "auto":
        return args.backend
    metaeditor = resolve_metaeditor_path(args.metaeditor)
    if sys.platform.startswith("win") and metaeditor:
        return "local-metaeditor"
    repository, ref, token = _configured_github(args)
    if repository and ref and token:
        return "github-actions"
    worker_url = args.worker_url or os.environ.get("VKMQL_WORKER_URL") or os.environ.get("MQL5_WORKER_URL")
    if worker_url:
        return "remote-worker"
    if sys.platform.startswith("linux") and metaeditor and (shutil.which("wine") or shutil.which("wine64")):
        return "wine-metaeditor"
    return None


def _github_target(mq5: str, project_root: Path) -> str:
    raw = Path(mq5)
    if raw.is_absolute():
        candidate = raw.resolve()
    elif (project_root / raw).exists():
        candidate = (project_root / raw).resolve()
    else:
        candidate = raw.resolve()
    try:
        return candidate.relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("GitHub compile target must be inside --project-root") from exc


def _emit_unavailable(args, backend: str | None, reason: str) -> int:
    payload = {
        "success": False,
        "status": "UNTESTABLE" if backend is None or args.backend == "auto" else "FAIL",
        "backend": backend or "none",
        "reason": reason,
        "failure_codes": [CompileFailureCode.INVOCATION_FAILED.value],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{payload['status']}: {reason}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-compile", description=__doc__.splitlines()[0])
    p.add_argument("mq5", help="path to .mq5 source; GitHub backend requires repository-relative target")
    p.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "local-metaeditor", "github-actions", "remote-worker", "wine-metaeditor"],
        help="execution backend; auto prefers local native → GitHub → remote worker → Wine",
    )
    p.add_argument(
        "--metaeditor",
        default=None,
        help="override MetaEditor64.exe path (else $METAEDITOR_PATH or default)",
    )
    p.add_argument("--log", default=None, help="local/Wine output log file (defaults to <mq5>.log)")
    p.add_argument("--out", default="evidence/compile", help="remote/GitHub evidence output directory")
    p.add_argument("--project-root", default=".", help="project root for remote/GitHub source binding")
    p.add_argument("--worker-url", default=None, help="remote Windows worker URL")
    p.add_argument("--worker-token", default=None, help="remote Windows worker bearer token")
    p.add_argument("--github-repo", default=None, help="GitHub repository owner/name")
    p.add_argument("--github-ref", default=None, help="branch/tag ref dispatched by GitHub Actions backend")
    p.add_argument("--github-token", default=None, help="GitHub token; defaults to VKMQL_GITHUB_TOKEN/GITHUB_TOKEN/GH_TOKEN")
    p.add_argument("--github-commit", default=None, help="expected full source commit SHA")
    p.add_argument("--github-workflow", default="rc7-github-native-compile.yml")
    p.add_argument("--github-artifact", default=None, help="override expected workflow artifact name")
    p.add_argument("--json", action="store_true", help="emit structured JSON to stdout")
    p.add_argument("--timeout", type=int, default=180, help="local compile timeout seconds")
    p.add_argument("--backend-timeout", type=int, default=3600, help="remote/GitHub backend timeout seconds")
    p.add_argument(
        "--max-warnings",
        type=int,
        default=0,
        help="maximum MetaEditor warnings allowed; RC7 house policy defaults to 0",
    )
    args = p.parse_args(argv)

    backend = _select_backend(args)
    if backend is None:
        return _emit_unavailable(
            args,
            None,
            "no compile backend is configured; local MetaEditor, GitHub Actions, remote worker and Wine are unavailable",
        )

    if backend == "github-actions":
        repository, ref, token = _configured_github(args)
        if not repository or not ref or not token:
            return _emit_unavailable(
                args,
                backend,
                "GitHub backend requires repository, ref and token",
            )
        try:
            target = _github_target(args.mq5, Path(args.project_root))
        except ValueError as exc:
            return _emit_unavailable(args, backend, str(exc))
        from .github_compile_backend import run_github_actions_compile

        record = run_github_actions_compile(
            target,
            repository=repository,
            ref=ref,
            project_root=args.project_root,
            expected_commit=args.github_commit,
            workflow=args.github_workflow,
            artifact_name=args.github_artifact,
            evidence_dir=args.out,
            token=token,
            timeout_sec=max(1, args.backend_timeout),
        )
        if args.json:
            print(json.dumps(record, indent=2, ensure_ascii=False))
        elif record.get("ok"):
            print(
                f"OK: github-actions run={record.get('workflow_run_id')} ex5={Path(args.out) / 'ea.ex5'}"
            )
        else:
            print(f"FAIL: {record.get('reason', 'GitHub native compile failed')}", file=sys.stderr)
        return 0 if record.get("ok") else 2

    if backend == "remote-worker":
        worker_url = args.worker_url or os.environ.get("VKMQL_WORKER_URL") or os.environ.get("MQL5_WORKER_URL")
        worker_token = args.worker_token or os.environ.get("VKMQL_WORKER_TOKEN") or os.environ.get("MQL5_WORKER_TOKEN")
        if not worker_url:
            return _emit_unavailable(args, backend, "remote-worker backend requires --worker-url or VKMQL_WORKER_URL")
        from .compile_runner import main as runner_main

        runner_args = [
            "--ea",
            args.mq5,
            "--out",
            args.out,
            "--backend",
            "remote-worker",
            "--worker-url",
            worker_url,
            "--project-root",
            args.project_root,
            "--timeout-sec",
            str(max(1, args.backend_timeout)),
        ]
        if worker_token:
            runner_args.extend(["--worker-token", worker_token])
        return int(runner_main(runner_args) or 0)

    if backend == "local-metaeditor" and not sys.platform.startswith("win"):
        return _emit_unavailable(args, backend, "local-metaeditor requires native Windows")
    if backend == "wine-metaeditor" and sys.platform.startswith("win"):
        return _emit_unavailable(args, backend, "wine-metaeditor is a Linux development backend")
    configured_metaeditor = resolve_metaeditor_path(args.metaeditor)
    if not configured_metaeditor and args.backend in {"local-metaeditor", "wine-metaeditor"}:
        return _emit_unavailable(args, backend, "MetaEditor path is not configured")

    mq5 = Path(args.mq5)
    log = Path(args.log) if args.log else None
    result = compile_mq5(
        mq5,
        configured_metaeditor,
        log,
        args.timeout,
        max_warnings=max(0, args.max_warnings),
    )

    if args.json:
        payload = result.to_dict()
        payload["backend"] = backend
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for warning in result.warnings:
            print("WARN:", warning, file=sys.stderr)
        for error in result.errors:
            print("ERROR:", error, file=sys.stderr)
        if result.success:
            suffix = " (development-only)" if backend == "wine-metaeditor" else ""
            print(f"OK: {result.ex5_path}{suffix}")
        else:
            print(
                "FAIL:" + (" " + ",".join(result.failure_codes) if result.failure_codes else ""),
                file=sys.stderr,
            )
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
