from vibecodekit_mql5.execution_sources import assess_backtest_source, assess_compile_source
from vibecodekit_mql5.provenance import CORE_ARTIFACTS as PROVENANCE_CORE
from vibecodekit_mql5.runner_key import CORE_ARTIFACTS as SIGNED_CORE


def test_only_native_or_attested_metaeditor_is_release_trusted():
    assert assess_compile_source("actual_metaeditor").trusted_for_release is True
    assert assess_compile_source("remote_worker_metaeditor").trusted_for_release is True
    assert assess_compile_source("wine_metaeditor").trusted_for_release is False
    assert assess_compile_source("imported_log").trusted_for_release is False


def test_only_real_mt5_tester_backends_are_release_trusted(tmp_path):
    report = tmp_path / "report.xml"
    assert assess_backtest_source("actual_mt5_strategy_tester", report).trusted_for_release is True
    assert assess_backtest_source("remote_worker_strategy_tester", report).trusted_for_release is True
    assert assess_backtest_source("imported_report", report).trusted_for_release is False
    assert assess_backtest_source("sample_fixture", report).trusted_for_release is False


def test_runner_signature_covers_exact_provenance_core_artifacts():
    assert SIGNED_CORE == PROVENANCE_CORE
    assert "evidence/compile/compile-log.txt" in SIGNED_CORE
    assert "evidence/compile/ea.ex5" in SIGNED_CORE
    assert "evidence/backtest/report.xml" in SIGNED_CORE


def test_native_contract_includes_stress_and_review_artifacts():
    assert "evidence/stress/stress-matrix-report.json" in PROVENANCE_CORE
    assert "evidence/review/deep-review.json" in PROVENANCE_CORE
