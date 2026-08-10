"""RC5 Task-10 native release-evidence gate (release tooling, not shipped kit source).

This validator binds real MetaEditor/MT5 evidence to the exact RC5 package
candidate produced by Task 09. It deliberately distinguishes BLOCKED (native
execution missing) from FAIL (evidence exists but is inconsistent/untrusted).
Only PASS is release-positive.

The generic shipped provenance validator remains the authority for trusted
execution source, canonical core artifact hashes and the pinned Ed25519 runner
key. This script adds only RC5 release-candidate binding and Task-10 lifecycle
semantics; keeping it outside tool/source preserves the Task-09 package bytes.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibecodekit_mql5.provenance import validate_release_provenance
from vibecodekit_mql5.release_policy import sha256_file

TOOL = "rc5-native-gate"
KIT_VERSION = "3.3.0rc5"
CANDIDATE_MANIFEST = Path("docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json")
ARTIFACT_HASHES = Path("docs/release/v3.3.0rc5/RC5-ARTIFACTS.sha256")
EVIDENCE_MANIFEST = Path("evidence/manifest.json")
ASYNC_REPORT = Path("evidence/native/async-fill.json")
RESTART_REPORT = Path("evidence/native/restart-recovery.json")
SOURCE_MQ5 = Path("evidence/compile/source.mq5")
COMPILE_LOG = Path("evidence/compile/compile-log.txt")
COMPILED_EX5 = Path("evidence/compile/ea.ex5")
BACKTEST_REPORT = Path("evidence/backtest/report.xml")

_BINDING_HASH_PATHS: dict[str, str] = {
    "source_zip_sha256": "tool/vibecodekit-mql5-v3.3.0rc5-source-full.zip",
    "source_manifest_sha256": "tool/vibecodekit-mql5-v3.3.0rc5-source-full.manifest.json",
    "wheel_sha256": "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl",
    "runtime_bundle_sha256": "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMPILE_COUNTS = re.compile(r"\b(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?\b", re.I)


@dataclass
class NativeGateResult:
    status: str  # PASS | BLOCKED | FAIL
    errors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    candidate_binding: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "errors": list(self.errors),
            "missing": list(self.missing),
            "checks": dict(self.checks),
            "candidate_binding": dict(self.candidate_binding),
            "provenance": dict(self.provenance),
        }


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _parse_hash_inventory(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not _HEX64.fullmatch(parts[0].lower()):
            raise ValueError(f"invalid SHA-256 inventory line {lineno} in {path}")
        hashes[parts[1].strip()] = parts[0].lower()
    return hashes


def expected_candidate_binding(repo_root: Path | str) -> dict[str, str]:
    """Return the immutable Task-09 identity that native evidence must sign."""
    root = Path(repo_root)
    candidate_path = root / CANDIDATE_MANIFEST
    hashes_path = root / ARTIFACT_HASHES
    if not candidate_path.is_file():
        raise FileNotFoundError(str(CANDIDATE_MANIFEST))
    if not hashes_path.is_file():
        raise FileNotFoundError(str(ARTIFACT_HASHES))
    candidate = _load_json(candidate_path)
    if candidate.get("kit_version") != KIT_VERSION:
        raise ValueError(
            f"candidate kit_version must be {KIT_VERSION}, got {candidate.get('kit_version')!r}"
        )
    source_tree = str(candidate.get("source_tree_sha") or "").strip()
    build_input = str(candidate.get("build_input_commit") or "").strip()
    if len(source_tree) != 40 or len(build_input) != 40:
        raise ValueError("candidate manifest lacks 40-char source_tree_sha/build_input_commit")
    inventory = _parse_hash_inventory(hashes_path)
    binding = {
        "kit_version": KIT_VERSION,
        "source_tree_sha": source_tree,
        "build_input_commit": build_input,
    }
    for field_name, rel in _BINDING_HASH_PATHS.items():
        digest = inventory.get(rel, "")
        if not _HEX64.fullmatch(digest):
            raise ValueError(f"artifact hash inventory lacks {rel}")
        binding[field_name] = digest
    return binding


def _check_binding(
    block: Any,
    expected: dict[str, str],
    label: str,
    *,
    missing: list[str],
    errors: list[str],
) -> None:
    if not isinstance(block, dict):
        missing.append(f"{label}.candidate_binding")
        return
    for key, expected_value in expected.items():
        if key not in block:
            missing.append(f"{label}.candidate_binding.{key}")
            continue
        if str(block.get(key)) != expected_value:
            errors.append(
                f"{label}.candidate_binding.{key} mismatch: expected {expected_value}, "
                f"got {block.get(key)!r}"
            )


def _hash_matches(project: Path, rel: Path, expected: Any, errors: list[str], missing: list[str]) -> None:
    path = project / rel
    if not path.is_file():
        missing.append(str(rel))
        return
    digest = str(expected or "").lower()
    if not _HEX64.fullmatch(digest):
        missing.append(f"sha256 declaration for {rel}")
        return
    actual = sha256_file(path)
    if actual != digest:
        errors.append(f"SHA-256 mismatch for {rel}: expected {digest}, got {actual}")


def compile_counts(log_path: Path) -> tuple[int, int] | None:
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    matches = list(_COMPILE_COUNTS.finditer(text))
    if not matches:
        return None
    last = matches[-1]
    return int(last.group(1)), int(last.group(2))


def _validate_compile(
    project: Path,
    compile_block: dict[str, Any],
    expected: dict[str, str],
    missing: list[str],
    errors: list[str],
) -> None:
    _check_binding(
        compile_block.get("candidate_binding"), expected, "compile", missing=missing, errors=errors
    )
    if not str(compile_block.get("tool_version") or "").strip():
        missing.append("compile.tool_version (MetaEditor build)")
    if compile_block.get("ok") is not True:
        errors.append("compile.ok must be true")
    _hash_matches(project, SOURCE_MQ5, compile_block.get("mq5_sha256"), errors, missing)
    _hash_matches(project, COMPILED_EX5, compile_block.get("ex5_sha256"), errors, missing)
    counts = compile_counts(project / COMPILE_LOG)
    if counts is None:
        errors.append("compile log has no MetaEditor '<n> errors, <n> warnings' summary")
    elif counts[0] != 0:
        errors.append(f"MetaEditor compile reports {counts[0]} error(s)")
    if compile_block.get("errors") not in (0, "0"):
        errors.append("compile.errors must be 0")


def _scenario_record(backtest: dict[str, Any], name: str) -> dict[str, Any] | None:
    native = backtest.get("native_scenarios")
    if not isinstance(native, dict):
        return None
    record = native.get(name)
    return record if isinstance(record, dict) else None


def _load_scenario(
    project: Path,
    rel: Path,
    signed_record: dict[str, Any] | None,
    name: str,
    missing: list[str],
    errors: list[str],
) -> dict[str, Any] | None:
    if signed_record is None:
        missing.append(f"backtest.native_scenarios.{name}")
        return None
    signed_path = str(signed_record.get("path") or "")
    if signed_path != rel.as_posix():
        errors.append(f"{name} signed path must be {rel.as_posix()}, got {signed_path!r}")
    _hash_matches(project, rel, signed_record.get("sha256"), errors, missing)
    path = project / rel
    if not path.is_file():
        return None
    try:
        return _load_json(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid {name} JSON: {exc}")
        return None


def _validate_async(data: dict[str, Any] | None, missing: list[str], errors: list[str]) -> None:
    if data is None:
        return
    if data.get("status") != "PASS":
        errors.append("async-fill status must be PASS")
    if data.get("source") not in {"actual_mt5_strategy_tester", "remote_worker_strategy_tester"}:
        errors.append("async-fill source is not trusted MT5 Strategy Tester execution")
    if data.get("partial_fill_observed") is not True:
        errors.append("async-fill evidence must observe a partial fill")
    if data.get("duplicate_order_count") != 0:
        errors.append("async-fill evidence reports duplicate orders")
    if data.get("intent_ids_unique") is not True:
        errors.append("async-fill evidence must prove unique intent ids")
    seq = data.get("state_sequence")
    if not isinstance(seq, list):
        missing.append("async-fill.state_sequence")
    else:
        normalized = [str(x).upper() for x in seq]
        for required in ("SUBMITTED", "PARTIAL", "COMPLETED"):
            if required not in normalized:
                errors.append(f"async-fill state_sequence lacks {required}")


def _validate_restart(data: dict[str, Any] | None, missing: list[str], errors: list[str]) -> None:
    if data is None:
        return
    if data.get("status") != "PASS":
        errors.append("restart-recovery status must be PASS")
    if data.get("source") not in {"actual_mt5_strategy_tester", "remote_worker_strategy_tester"}:
        errors.append("restart-recovery source is not trusted MT5 Strategy Tester execution")
    if data.get("interruption_observed") is not True:
        errors.append("restart-recovery must record an actual interruption/restart boundary")
    if data.get("persisted_intent_reloaded") is not True:
        errors.append("restart-recovery must prove persisted intent reload")
    if data.get("duplicate_order_count") != 0:
        errors.append("restart-recovery evidence reports duplicate orders")
    resolution = str(data.get("resolution") or "").upper()
    if resolution not in {"TERMINAL_PROOF", "OPERATOR_REQUIRED"}:
        errors.append("restart-recovery resolution must be TERMINAL_PROOF or OPERATOR_REQUIRED")


def validate_rc5_native_evidence(repo_root: Path | str, project_dir: Path | str) -> NativeGateResult:
    repo = Path(repo_root)
    project = Path(project_dir)
    result = NativeGateResult(status="BLOCKED")
    try:
        expected = expected_candidate_binding(repo)
    except FileNotFoundError as exc:
        result.missing.append(f"candidate contract: {exc}")
        return result
    except Exception as exc:  # noqa: BLE001
        result.status = "FAIL"
        result.errors.append(f"candidate contract invalid: {exc}")
        return result
    result.candidate_binding = expected

    manifest_path = project / EVIDENCE_MANIFEST
    if not manifest_path.is_file():
        result.missing.append(str(EVIDENCE_MANIFEST))
        return result
    try:
        manifest = _load_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        result.status = "FAIL"
        result.errors.append(f"invalid evidence manifest: {exc}")
        return result

    prov = validate_release_provenance(project)
    result.provenance = prov.to_dict()
    if prov.status == "FAIL":
        result.status = "FAIL"
        result.errors.extend(prov.errors)
        return result
    if prov.status != "PASS":
        result.missing.extend(prov.missing)

    compile_block = manifest.get("compile") if isinstance(manifest.get("compile"), dict) else {}
    backtest = manifest.get("backtest") if isinstance(manifest.get("backtest"), dict) else {}
    _validate_compile(project, compile_block, expected, result.missing, result.errors)
    _check_binding(
        backtest.get("candidate_binding"), expected, "backtest", missing=result.missing, errors=result.errors
    )
    if not str(backtest.get("tool_version") or "").strip():
        result.missing.append("backtest.tool_version (MT5 terminal build)")
    if backtest.get("ok") is not True:
        result.errors.append("backtest.ok must be true")
    tester = backtest.get("tester")
    if not isinstance(tester, dict):
        result.missing.append("backtest.tester")
    else:
        for key in ("symbol", "timeframe", "model", "from_date", "to_date"):
            if not str(tester.get(key) or "").strip():
                result.missing.append(f"backtest.tester.{key}")

    async_data = _load_scenario(
        project, ASYNC_REPORT, _scenario_record(backtest, "async_fill"),
        "async_fill", result.missing, result.errors,
    )
    restart_data = _load_scenario(
        project, RESTART_REPORT, _scenario_record(backtest, "restart_recovery"),
        "restart_recovery", result.missing, result.errors,
    )
    _validate_async(async_data, result.missing, result.errors)
    _validate_restart(restart_data, result.missing, result.errors)

    result.missing = list(dict.fromkeys(result.missing))
    result.errors = list(dict.fromkeys(result.errors))
    result.checks = {
        "candidate_bound": not any("candidate_binding" in e for e in result.errors + result.missing),
        "trusted_provenance": prov.status == "PASS",
        "compile_native": not any(e.startswith("compile") or "MetaEditor" in e for e in result.errors + result.missing),
        "async_fill": not any("async-fill" in e or "async_fill" in e for e in result.errors + result.missing),
        "restart_recovery": not any("restart-recovery" in e or "restart_recovery" in e for e in result.errors + result.missing),
    }
    if result.errors:
        result.status = "FAIL"
    elif result.missing:
        result.status = "BLOCKED"
    else:
        result.status = "PASS"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    result = validate_rc5_native_evidence(args.repo_root, args.project_dir)
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True)
    print(payload)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    if result.status == "PASS":
        return 0
    if result.status == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
