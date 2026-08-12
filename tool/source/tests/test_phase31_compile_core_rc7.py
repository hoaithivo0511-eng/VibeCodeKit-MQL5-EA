from pathlib import Path

from vibecodekit_mql5.compile_core import (
    CompileFailureCode,
    CompilePolicy,
    parse_metaeditor_log,
)
from vibecodekit_mql5.execution_sources import assess_compile_source


def _ex5(tmp_path: Path) -> Path:
    path = tmp_path / "EA.ex5"
    path.write_bytes(b"EX5")
    return path


def test_rc7_compile_house_policy_accepts_only_zero_zero_with_ex5(tmp_path):
    result = parse_metaeditor_log(
        "Result: 0 errors, 0 warnings, 12 msec elapsed",
        ex5_path=_ex5(tmp_path),
    )
    assert result.success is True
    assert result.error_count == 0
    assert result.warning_count == 0


def test_rc7_compile_house_policy_rejects_warning(tmp_path):
    result = parse_metaeditor_log(
        "Result: 0 errors, 1 warnings, 12 msec elapsed",
        ex5_path=_ex5(tmp_path),
    )
    assert result.success is False
    assert CompileFailureCode.COMPILE_WARNINGS.value in result.failure_codes


def test_rc7_compile_rejects_missing_result_even_without_diagnostic_lines(tmp_path):
    result = parse_metaeditor_log("MetaEditor started", ex5_path=_ex5(tmp_path))
    assert result.success is False
    assert CompileFailureCode.RESULT_MISSING.value in result.failure_codes


def test_rc7_compile_rejects_missing_ex5(tmp_path):
    result = parse_metaeditor_log(
        "Result: 0 errors, 0 warnings, 12 msec elapsed",
        ex5_path=tmp_path / "missing.ex5",
    )
    assert result.success is False
    assert CompileFailureCode.EX5_MISSING.value in result.failure_codes


def test_rc7_parser_never_reads_ten_errors_as_zero(tmp_path):
    result = parse_metaeditor_log(
        "Result: 10 errors, 0 warnings, 12 msec elapsed",
        ex5_path=_ex5(tmp_path),
    )
    assert result.success is False
    assert result.error_count == 10
    assert CompileFailureCode.COMPILE_ERRORS.value in result.failure_codes


def test_pure_parser_can_disable_artifact_gate_for_compatibility():
    result = parse_metaeditor_log(
        "Result: 0 errors, 0 warnings, 12 msec elapsed",
        policy=CompilePolicy(require_ex5=False),
    )
    assert result.success is True


def test_github_actions_source_requires_independent_provenance_verification():
    assert assess_compile_source("github_actions_metaeditor").trusted_for_release is False
    assert assess_compile_source(
        "github_actions_metaeditor", provenance_verified=True
    ).trusted_for_release is True
