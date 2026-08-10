"""Finalize real Windows MetaEditor/MT5 outputs into signed RC5 Task-10 evidence.

This command does not simulate MetaEditor, Strategy Tester, async fills or
restart recovery.  It accepts files already produced on the trusted native
runner, canonicalizes them, binds them to the exact Task-09 RC5 candidate,
signs the evidence manifest with the runner's pinned Ed25519 key, builds the
evidence hash-chain and finally runs the RC5 native gate.

A missing/mismatched artifact is a hard refusal; the command never manufactures
release-positive evidence from fixtures or imported placeholders.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_attestation import create_release_attestation
from .evidence_v2 import EvidenceManifestV2
from .rc5_native_gate import (
    ASYNC_REPORT,
    BACKTEST_REPORT,
    COMPILED_EX5,
    COMPILE_LOG,
    RESTART_REPORT,
    SOURCE_MQ5,
    compile_counts,
    expected_candidate_binding,
    validate_rc5_native_evidence,
)
from .release_policy import sha256_file
from . import runner_key

TOOL = "mql5-rc5-native-finalize"
STRESS_REPORT = Path("evidence/stress/stress-matrix-report.json")
REVIEW_REPORT = Path("evidence/review/deep-review.json")
TESTER_INI = Path("evidence/backtest/tester.ini")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_required(source: Path, dest: Path, label: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"{label} not found: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return data


def _record(project: Path, rel: Path, role: str, *, required: bool = True) -> dict[str, Any]:
    path = project / rel
    record: dict[str, Any] = {
        "role": role,
        "path": rel.as_posix(),
        "exists": path.is_file(),
        "fixture": False,
        "required": required,
    }
    if path.is_file():
        record["sha256"] = sha256_file(path)
        record["size_bytes"] = path.stat().st_size
    return record


def _public_b64_from_private(key_path: Path) -> str:
    private = runner_key._load_private(key_path)  # noqa: SLF001 - same-package security primitive
    raw = runner_key._public_raw(private)  # noqa: SLF001 - never exposes the private key
    return base64.b64encode(raw).decode("ascii")


def finalize_native_evidence(
    *,
    repo_root: Path,
    project_dir: Path,
    source_mq5: Path,
    compile_log: Path,
    compiled_ex5: Path,
    tester_report: Path,
    tester_ini: Path,
    stress_report: Path,
    review_report: Path,
    async_fill_report: Path,
    restart_report: Path,
    metaeditor_build: str,
    terminal_build: str,
    tester_symbol: str,
    tester_timeframe: str,
    tester_model: str,
    tester_from: str,
    tester_to: str,
    compile_command: str,
    tester_command: str,
    runner_key_path: Path,
    runner_key_id: str,
) -> dict[str, Any]:
    """Canonicalize, sign and validate one real Task-10 native evidence set."""
    if project_dir.resolve() == repo_root.resolve():
        raise ValueError("project_dir must be a dedicated release-evidence directory, not the repo root")
    if "docs" in {p.lower() for p in project_dir.parts}:
        raise ValueError("native evidence must not live under docs/; fixture-path policy would reject it")
    if not metaeditor_build.strip() or not terminal_build.strip():
        raise ValueError("MetaEditor and terminal build identifiers are mandatory")
    if not runner_key_id.strip():
        raise ValueError("runner_key_id is mandatory")
    if not (project_dir / "RELEASE-TRUST.yaml").is_file():
        raise FileNotFoundError(
            f"missing {project_dir / 'RELEASE-TRUST.yaml'}; pin the native runner key before finalizing"
        )

    binding = expected_candidate_binding(repo_root)
    project_dir.mkdir(parents=True, exist_ok=True)

    copies = (
        (source_mq5, project_dir / SOURCE_MQ5, "MQ5 source"),
        (compile_log, project_dir / COMPILE_LOG, "MetaEditor compile log"),
        (compiled_ex5, project_dir / COMPILED_EX5, "compiled EX5"),
        (tester_report, project_dir / BACKTEST_REPORT, "Strategy Tester XML report"),
        (tester_ini, project_dir / TESTER_INI, "tester.ini"),
        (stress_report, project_dir / STRESS_REPORT, "stress matrix report"),
        (review_report, project_dir / REVIEW_REPORT, "deep review report"),
        (async_fill_report, project_dir / ASYNC_REPORT, "async-fill native report"),
        (restart_report, project_dir / RESTART_REPORT, "restart-recovery native report"),
    )
    for source, dest, label in copies:
        _copy_required(source, dest, label)

    if (project_dir / COMPILED_EX5).stat().st_size < 32:
        raise ValueError("compiled EX5 is implausibly small; refusing fixture/stub binary")
    counts = compile_counts(project_dir / COMPILE_LOG)
    if counts is None:
        raise ValueError("compile log has no MetaEditor '<n> errors, <n> warnings' summary")
    errors, warnings = counts
    if errors:
        raise ValueError(f"MetaEditor compile reports {errors} error(s)")

    # Parse every structured input before any release-positive manifest is emitted.
    _load_json(project_dir / STRESS_REPORT, "stress report")
    _load_json(project_dir / REVIEW_REPORT, "deep review report")
    async_data = _load_json(project_dir / ASYNC_REPORT, "async-fill report")
    restart_data = _load_json(project_dir / RESTART_REPORT, "restart-recovery report")

    async_sha = sha256_file(project_dir / ASYNC_REPORT)
    restart_sha = sha256_file(project_dir / RESTART_REPORT)
    recorded = _utc_now()
    host = platform.node() or os.environ.get("COMPUTERNAME", "unknown-host")

    compile_block: dict[str, Any] = {
        "ok": True,
        "source": "actual_metaeditor",
        "command": compile_command,
        "tool_version": metaeditor_build.strip(),
        "host": host,
        "recorded_at_utc": recorded,
        "returncode": 0,
        "errors": errors,
        "warnings": warnings,
        "log_path": COMPILE_LOG.as_posix(),
        "source_mq5_path": SOURCE_MQ5.as_posix(),
        "compiled_ex5_path": COMPILED_EX5.as_posix(),
        "mq5_sha256": sha256_file(project_dir / SOURCE_MQ5),
        "ex5_sha256": sha256_file(project_dir / COMPILED_EX5),
        "candidate_binding": binding,
    }
    backtest_block: dict[str, Any] = {
        "ok": True,
        "source": "actual_mt5_strategy_tester",
        "command": tester_command,
        "tool_version": terminal_build.strip(),
        "host": host,
        "recorded_at_utc": recorded,
        "returncode": 0,
        "report_path": BACKTEST_REPORT.as_posix(),
        "tester": {
            "symbol": tester_symbol,
            "timeframe": tester_timeframe,
            "model": tester_model,
            "from_date": tester_from,
            "to_date": tester_to,
            "ini_path": TESTER_INI.as_posix(),
        },
        "candidate_binding": binding,
        "native_scenarios": {
            "async_fill": {
                "path": ASYNC_REPORT.as_posix(),
                "sha256": async_sha,
                "status": async_data.get("status"),
            },
            "restart_recovery": {
                "path": RESTART_REPORT.as_posix(),
                "sha256": restart_sha,
                "status": restart_data.get("status"),
            },
        },
    }

    artifact_defs = (
        (SOURCE_MQ5, "source_mq5"),
        (COMPILE_LOG, "compile_log"),
        (COMPILED_EX5, "compiled_ex5"),
        (BACKTEST_REPORT, "strategy_tester_report"),
        (TESTER_INI, "strategy_tester_ini"),
        (STRESS_REPORT, "stress_matrix_report"),
        (REVIEW_REPORT, "deep_review_report"),
        (ASYNC_REPORT, "async_fill_native_report"),
        (RESTART_REPORT, "restart_recovery_native_report"),
    )
    artifacts = [_record(project_dir, rel, role) for rel, role in artifact_defs]
    manifest = EvidenceManifestV2(
        compile=compile_block,
        backtest=backtest_block,
        gates={"ok": True, "native_task10": True},
        artifacts=artifacts,
        skipped_stages=[],
        unsafe_flags_used=[],
    ).to_dict()
    # Canonical provenance requires both top-level and summary eligibility to
    # assert the same release claim.  EvidenceManifestV2 historically only
    # emits the summary field, so the native finalizer mirrors it explicitly.
    manifest["release_eligible"] = manifest["summary"]["release_eligible"]
    if manifest["release_eligible"] is not True:
        raise ValueError("native evidence manifest did not satisfy canonical release predicate")

    manifest_path = project_dir / "evidence/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Sign on the native runner.  runner_key.sign independently checks that the
    # manifest's core artifact hashes still match the bytes before signing.
    sign_rc = runner_key.main([
        "sign",
        str(project_dir),
        "--key",
        str(runner_key_path),
        "--key-id",
        runner_key_id,
    ])
    if sign_rc != 0:
        raise ValueError("runner signing refused the evidence manifest")

    # Local verification uses the public half derived from the runner key. The
    # private half never leaves this process/machine. CI later receives only the
    # public key and independently checks its fingerprint against RELEASE-TRUST.
    old_public = os.environ.get("VCK_RUNNER_PUBLIC_KEY_B64")
    os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = _public_b64_from_private(runner_key_path)
    try:
        attestation = create_release_attestation(project_dir, release_eligible=True)
        native_gate = validate_rc5_native_evidence(repo_root, project_dir)
    finally:
        if old_public is None:
            os.environ.pop("VCK_RUNNER_PUBLIC_KEY_B64", None)
        else:
            os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = old_public

    if not attestation.release_eligible:
        raise ValueError("evidence attestation remained release-ineligible: " + "; ".join(attestation.errors))
    if native_gate.status != "PASS":
        raise ValueError(
            f"RC5 native gate returned {native_gate.status}: "
            + "; ".join(native_gate.errors + native_gate.missing)
        )
    return {
        "ok": True,
        "status": "PASS",
        "project_dir": str(project_dir),
        "candidate_binding": binding,
        "compile": {"errors": errors, "warnings": warnings},
        "runner_key_id": runner_key_id,
        "native_gate": native_gate.to_dict(),
        "chain_root": attestation.chain_root,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--project-dir", type=Path, required=True)
    p.add_argument("--source-mq5", type=Path, required=True)
    p.add_argument("--compile-log", type=Path, required=True)
    p.add_argument("--compiled-ex5", type=Path, required=True)
    p.add_argument("--tester-report", type=Path, required=True)
    p.add_argument("--tester-ini", type=Path, required=True)
    p.add_argument("--stress-report", type=Path, required=True)
    p.add_argument("--review-report", type=Path, required=True)
    p.add_argument("--async-fill-report", type=Path, required=True)
    p.add_argument("--restart-report", type=Path, required=True)
    p.add_argument("--metaeditor-build", required=True)
    p.add_argument("--terminal-build", required=True)
    p.add_argument("--tester-symbol", required=True)
    p.add_argument("--tester-timeframe", required=True)
    p.add_argument("--tester-model", required=True)
    p.add_argument("--tester-from", required=True)
    p.add_argument("--tester-to", required=True)
    p.add_argument("--compile-command", required=True)
    p.add_argument("--tester-command", required=True)
    p.add_argument("--runner-key", type=Path, required=True)
    p.add_argument("--runner-key-id", required=True)
    args = p.parse_args(argv)
    try:
        result = finalize_native_evidence(
            repo_root=args.repo_root,
            project_dir=args.project_dir,
            source_mq5=args.source_mq5,
            compile_log=args.compile_log,
            compiled_ex5=args.compiled_ex5,
            tester_report=args.tester_report,
            tester_ini=args.tester_ini,
            stress_report=args.stress_report,
            review_report=args.review_report,
            async_fill_report=args.async_fill_report,
            restart_report=args.restart_report,
            metaeditor_build=args.metaeditor_build,
            terminal_build=args.terminal_build,
            tester_symbol=args.tester_symbol,
            tester_timeframe=args.tester_timeframe,
            tester_model=args.tester_model,
            tester_from=args.tester_from,
            tester_to=args.tester_to,
            compile_command=args.compile_command,
            tester_command=args.tester_command,
            runner_key_path=args.runner_key,
            runner_key_id=args.runner_key_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "status": "FAIL", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
