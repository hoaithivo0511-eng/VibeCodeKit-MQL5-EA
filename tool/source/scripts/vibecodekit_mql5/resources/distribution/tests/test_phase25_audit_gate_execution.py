import json
from pathlib import Path
from types import SimpleNamespace

from vibecodekit_mql5 import check_all, release_policy
from vibecodekit_mql5.check_all import StageResult
from vibecodekit_mql5.release_policy import compute_release_eligible


def _write_ea(project: Path, source: str) -> None:
    path = project / "Experts" / "AuditEA" / "AuditEA.mq5"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def test_check_all_lint_stage_executes_real_detectors(tmp_path: Path):
    project = tmp_path / "project"
    _write_ea(
        project,
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "void OnTick(){trade.Buy(0.1,_Symbol,0,0,0);}\n",
    )

    result = check_all._stage_lint(project)

    assert result.status == "FAIL"
    assert "AP-1" in result.detail


def test_check_all_lint_missing_source_is_a_failure(tmp_path: Path):
    result = check_all._stage_lint(tmp_path)

    assert result.status == "FAIL"
    assert "no .mq5/.mqh source" in result.detail


def test_review_executes_and_separates_static_from_evidence_blockers(
    tmp_path: Path, monkeypatch
):
    calls: list[Path] = []

    def fake_review(project: Path):
        calls.append(project)
        return {
            "issues": [
                {"category": "release", "severity": "critical", "title": "No compile"},
                {"category": "risk", "severity": "warn", "title": "Review risk"},
            ]
        }

    monkeypatch.setattr(
        "vibecodekit_mql5.ea_senior_review.review_project", fake_review
    )

    result = check_all._stage_review(tmp_path)

    assert calls == [tmp_path]
    assert result.status == "PASS"
    assert "1 evidence blocker(s)" in result.detail


def test_review_fails_on_real_static_blocker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "vibecodekit_mql5.ea_senior_review.review_project",
        lambda _project: {
            "issues": [
                {
                    "category": "execution",
                    "severity": "critical",
                    "title": "Unsafe execution",
                }
            ]
        },
    )

    result = check_all._stage_review(tmp_path)

    assert result.status == "FAIL"
    assert "Unsafe execution" in result.detail


def test_canonical_predicate_rejects_incomplete_mandatory_stages():
    assert not compute_release_eligible(
        compile_ok=True,
        gate_ok=True,
        backtest_ok=True,
        evidence_ok=True,
        mandatory_stages_ok=False,
    )


def test_check_all_exposes_quality_readiness_and_eligibility_separately(
    tmp_path: Path, monkeypatch
):
    def passed(name: str) -> StageResult:
        return StageResult(name, "PASS", "test")

    monkeypatch.setattr(check_all, "_stage_scan", lambda _project: passed("scan"))
    monkeypatch.setattr(check_all, "_stage_contract", lambda _project: passed("contract"))
    monkeypatch.setattr(check_all, "_stage_lint", lambda _project: StageResult("lint", "SKIPPED", "test"))
    monkeypatch.setattr(check_all, "_stage_env", lambda name, _project: passed(name))
    monkeypatch.setattr(check_all, "_stage_quality", lambda _project: passed("quality"))
    monkeypatch.setattr(check_all, "_stage_forward", lambda _project: passed("forward"))
    monkeypatch.setattr(check_all, "_stage_stress", lambda _project: passed("stress"))
    monkeypatch.setattr(check_all, "_stage_review", lambda _project: passed("review"))
    monkeypatch.setattr(check_all, "_stage_retro", lambda _project: passed("retro"))
    monkeypatch.setattr(check_all, "_stage_approval", lambda _project: passed("approval"))
    monkeypatch.setattr(check_all, "_stage_evidence", lambda _project: passed("evidence"))
    monkeypatch.setattr(check_all, "_release_target", lambda _project: "live")

    result = check_all.run_check_all(tmp_path)

    assert result.ok
    assert not result.code_quality_ok
    assert not result.release_ready
    assert not result.release_eligible
    assert result.to_dict()["code_quality_ok"] is False
    assert result.to_dict()["release_ready"] is False


def test_all_explicit_passes_reach_canonical_release_predicate(
    tmp_path: Path, monkeypatch
):
    def passed(name: str) -> StageResult:
        return StageResult(name, "PASS", "test")

    monkeypatch.setattr(check_all, "_stage_scan", lambda _project: passed("scan"))
    monkeypatch.setattr(check_all, "_stage_contract", lambda _project: passed("contract"))
    monkeypatch.setattr(check_all, "_stage_lint", lambda _project: passed("lint"))
    monkeypatch.setattr(check_all, "_stage_env", lambda name, _project: passed(name))
    monkeypatch.setattr(check_all, "_stage_quality", lambda _project: passed("quality"))
    monkeypatch.setattr(check_all, "_stage_forward", lambda _project: passed("forward"))
    monkeypatch.setattr(check_all, "_stage_stress", lambda _project: passed("stress"))
    monkeypatch.setattr(check_all, "_stage_review", lambda _project: passed("review"))
    monkeypatch.setattr(check_all, "_stage_retro", lambda _project: passed("retro"))
    monkeypatch.setattr(check_all, "_stage_approval", lambda _project: passed("approval"))
    monkeypatch.setattr(check_all, "_stage_evidence", lambda _project: passed("evidence"))
    monkeypatch.setattr(check_all, "_release_target", lambda _project: "live")

    result = check_all.run_check_all(tmp_path)

    assert result.ok
    assert result.code_quality_ok
    assert result.release_ready
    assert result.release_eligible


def test_scan_stage_covers_missing_high_clean_and_exception(tmp_path: Path, monkeypatch):
    assert check_all._stage_scan(tmp_path).status == "SKIPPED"
    _write_ea(tmp_path, "void OnTick(){}\n")

    from vibecodekit_mql5 import scan_ea

    monkeypatch.setattr(
        scan_ea,
        "analyze_source",
        lambda *_args, **_kwargs: SimpleNamespace(
            risk_flags=[{"severity": "high"}], behaviours=["trade"]
        ),
    )
    assert check_all._stage_scan(tmp_path).status == "FAIL"

    monkeypatch.setattr(
        scan_ea,
        "analyze_source",
        lambda *_args, **_kwargs: SimpleNamespace(risk_flags=[], behaviours=["tick"]),
    )
    assert check_all._stage_scan(tmp_path).status == "PASS"

    def broken(*_args, **_kwargs):
        raise RuntimeError("scan unavailable")

    monkeypatch.setattr(scan_ea, "analyze_source", broken)
    assert check_all._stage_scan(tmp_path).status == "UNTESTABLE"


def test_contract_and_stress_stage_branching(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        check_all.cc,
        "check_project_contract",
        lambda _project: SimpleNamespace(ok=False, errors=["broken contract"]),
    )
    assert check_all._stage_contract(tmp_path).status == "FAIL"

    report = tmp_path / check_all.sm.REPORT_SUBDIR / check_all.sm.REPORT_JSON
    report.parent.mkdir(parents=True)
    report.write_text("not-json", encoding="utf-8")
    assert check_all._prior_stress_counts(tmp_path) is None

    monkeypatch.setattr(
        check_all.sm,
        "run_stress_matrix",
        lambda *_args, **_kwargs: SimpleNamespace(counts={"FAIL": 1}),
    )
    assert check_all._stage_stress(tmp_path).status == "FAIL"

    report.write_text(json.dumps({"counts": {"PASS": 8}}), encoding="utf-8")
    assert check_all._stage_stress(tmp_path).status == "PASS"


def test_evidence_stage_is_read_only_and_grades_all_outcomes(
    tmp_path: Path, monkeypatch
):
    fixture = tmp_path / "tests" / "fixture"
    fixture.mkdir(parents=True)
    assert check_all._writes_blocked(fixture)
    assert check_all._stage_evidence(fixture).status == "UNTESTABLE"

    build_calls: list[Path] = []
    monkeypatch.setattr(check_all, "_writes_blocked", lambda _project: False)
    monkeypatch.setattr(
        check_all.ea,
        "build_hash_chain",
        lambda project, write: build_calls.append(project),
    )
    monkeypatch.setattr(
        check_all.ea,
        "verify_hash_chain",
        lambda _project: SimpleNamespace(ok=False, errors=["hash mismatch"]),
    )
    assert check_all._stage_evidence(tmp_path).status == "FAIL"
    assert build_calls == [tmp_path]

    monkeypatch.setattr(
        check_all.ea,
        "verify_hash_chain",
        lambda _project: SimpleNamespace(ok=True, errors=[]),
    )
    for status, expected in (
        ("PASS", "PASS"),
        ("FAIL", "FAIL"),
        ("INCOMPLETE", "UNTESTABLE"),
    ):
        monkeypatch.setattr(
            check_all.ea,
            "evaluate_release_evidence",
            lambda _project, value=status: SimpleNamespace(
                status=value,
                errors=["provenance failed"] if value == "FAIL" else [],
                missing=["native evidence"] if value == "INCOMPLETE" else [],
            ),
        )
        assert check_all._stage_evidence(tmp_path).status == expected


def test_quality_and_forward_stages_grade_pass_warn_fail_and_errors(
    tmp_path: Path, monkeypatch
):
    assert check_all._stage_quality(tmp_path).status == "UNTESTABLE"
    assert check_all._stage_forward(tmp_path).status == "UNTESTABLE"

    backtest_report = tmp_path / "evidence" / "backtest" / "report.xml"
    backtest_report.parent.mkdir(parents=True)
    backtest_report.write_text("<report/>", encoding="utf-8")
    walkforward_dir = tmp_path / "evidence" / "walkforward"
    walkforward_dir.mkdir(parents=True)
    (walkforward_dir / "is_report.xml").write_text("<report/>", encoding="utf-8")
    (walkforward_dir / "oos_report.xml").write_text("<report/>", encoding="utf-8")

    from vibecodekit_mql5 import backtest, backtest_quality, walkforward

    monkeypatch.setattr(backtest, "parse_xml_report_file", lambda path: path)
    for verdict, expected in (
        ("PASS", "PASS"),
        ("WARN", "UNTESTABLE"),
        ("FAIL", "FAIL"),
    ):
        monkeypatch.setattr(
            backtest_quality,
            "evaluate",
            lambda *_args, value=verdict, **_kwargs: SimpleNamespace(
                verdict=value, r2=0.8, complex_criterion="ok"
            ),
        )
        assert check_all._stage_quality(tmp_path).status == expected

        monkeypatch.setattr(
            walkforward,
            "evaluate",
            lambda *_args, value=verdict: SimpleNamespace(verdict=value),
        )
        assert check_all._stage_forward(tmp_path).status == expected

    def parse_error(_path):
        raise ValueError("bad report")

    monkeypatch.setattr(backtest, "parse_xml_report_file", parse_error)
    assert check_all._stage_quality(tmp_path).status == "UNTESTABLE"
    assert check_all._stage_forward(tmp_path).status == "UNTESTABLE"


def test_environment_stage_requires_trusted_provenance(tmp_path: Path, monkeypatch):
    assert check_all._stage_env("compile", tmp_path).status == "UNTESTABLE"
    marker = tmp_path / "evidence" / "compile" / "compile-log.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("compile", encoding="utf-8")

    from vibecodekit_mql5 import provenance

    for status, expected in (
        ("PASS", "PASS"),
        ("FAIL", "FAIL"),
        ("INCOMPLETE", "UNTESTABLE"),
    ):
        monkeypatch.setattr(
            provenance,
            "validate_release_provenance",
            lambda _project, value=status: SimpleNamespace(
                status=value, errors=["untrusted"] if value == "FAIL" else []
            ),
        )
        assert check_all._stage_env("compile", tmp_path).status == expected


def test_lint_review_and_release_helpers_handle_nonhappy_paths(
    tmp_path: Path, monkeypatch
):
    _write_ea(tmp_path, "// digits-tested: 5,3\nvoid OnTick(){}\n")
    assert check_all._stage_lint(tmp_path).status == "PASS"

    monkeypatch.setattr(
        "vibecodekit_mql5.ea_doc_analyzer.read_reachable_mql_files",
        lambda _project: (_ for _ in ()).throw(RuntimeError("read failed")),
    )
    assert check_all._stage_lint(tmp_path).status == "UNTESTABLE"

    monkeypatch.setattr(
        "vibecodekit_mql5.ea_senior_review.review_project",
        lambda _project: (_ for _ in ()).throw(RuntimeError("review failed")),
    )
    assert check_all._stage_review(tmp_path).status == "UNTESTABLE"

    monkeypatch.setattr(
        check_all.sv,
        "load_spec_v26",
        lambda _path: SimpleNamespace(ok=False, spec={}),
    )
    assert check_all._release_target(tmp_path) == "draft"
    monkeypatch.setattr(
        check_all.sv,
        "load_spec_v26",
        lambda _path: SimpleNamespace(
            ok=True, spec={"governance": {"release_target": "live"}}
        ),
    )
    assert check_all._release_target(tmp_path) == "live"

    monkeypatch.setattr(
        check_all.rgc,
        "evaluate",
        lambda _project: SimpleNamespace(status="FAIL", errors=["guard"]),
    )
    assert check_all._stage_retro(tmp_path).status == "FAIL"
    monkeypatch.setattr(
        check_all.ra,
        "validate",
        lambda *_args: SimpleNamespace(status="NOT_REQUIRED", errors=[]),
    )
    assert check_all._stage_approval(tmp_path).status == "SKIPPED"
    monkeypatch.setattr(
        check_all.ra,
        "validate",
        lambda *_args: SimpleNamespace(status="PASS", errors=[]),
    )
    assert check_all._stage_approval(tmp_path).status == "PASS"


def test_missing_project_report_and_cli_outputs(tmp_path: Path, monkeypatch):
    missing = check_all.run_check_all(tmp_path / "missing")
    assert not missing.ok
    assert missing.stages[0].status == "FAIL"

    result = check_all.CheckAllResult(
        ok=True,
        code_quality_ok=True,
        release_ready=False,
        release_eligible=False,
        project_dir=str(tmp_path),
        stages=[StageResult("contract", "FAIL", "missing contract")],
    )
    markdown = check_all.render_report(result)
    assert "Code quality checks passed: **True**" in markdown
    assert "vkmql-new spec" in markdown

    monkeypatch.setattr(check_all, "run_check_all", lambda _project: result)
    monkeypatch.setattr(check_all, "maybe_emit", lambda *_args: None)
    out = tmp_path / "reports" / "gate.md"
    assert check_all.main([str(tmp_path), "--out", str(out)]) == 0
    assert out.is_file()
    assert check_all.main([str(tmp_path), "--require-release", "--json"]) == 1


def test_release_policy_manifest_adapter_and_validation(tmp_path: Path, monkeypatch):
    report = {
        "ok": True,
        "stages": [
            {"name": "build", "ok": True},
            {"name": "compile", "ok": True},
            {"name": "gate", "ok": True},
            {"name": "backtest", "ok": True},
        ],
        "evidence_manifest": {"ok": True},
    }
    assert release_policy.summarize(report, ["--draft"])["status"] == "draft"

    written = release_policy.write_evidence_manifest(tmp_path / "empty", report)
    assert written["release_eligible"] is False

    target = tmp_path / "validate"
    assert release_policy.validate_release_manifest(target)[0] is False
    manifest = target / "evidence" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("not-json", encoding="utf-8")
    assert "invalid" in release_policy.validate_release_manifest(target)[1]
    manifest.write_text(json.dumps({"release_eligible": False}), encoding="utf-8")
    assert "release_eligible=false" in release_policy.validate_release_manifest(target)[1]

    from vibecodekit_mql5 import provenance

    manifest.write_text(json.dumps({"release_eligible": True}), encoding="utf-8")
    monkeypatch.setattr(
        provenance,
        "validate_release_provenance",
        lambda _project: SimpleNamespace(
            status="INCOMPLETE", errors=[], missing=["signature"]
        ),
    )
    assert "signature" in release_policy.validate_release_manifest(target)[1]
    monkeypatch.setattr(
        provenance,
        "validate_release_provenance",
        lambda _project: SimpleNamespace(status="PASS", errors=[], missing=[]),
    )
    assert release_policy.validate_release_manifest(target) == (True, "ok")
