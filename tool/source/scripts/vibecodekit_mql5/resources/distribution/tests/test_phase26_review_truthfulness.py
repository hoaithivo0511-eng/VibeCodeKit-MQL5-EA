import json
from pathlib import Path

from vibecodekit_mql5 import deep_review
from vibecodekit_mql5.ea_senior_review import detect_strategy, review_project


def _write_project(project: Path, source: str | None = None) -> Path:
    ea = project / "Experts" / "TruthEA" / "TruthEA.mq5"
    ea.parent.mkdir(parents=True)
    ea.write_text(
        source
        or (
            "// digits-tested: 5,3\n"
            "#property strict\n"
            "int OnInit(){return INIT_SUCCEEDED;}\n"
            "void OnTick(){}\n"
        ),
        encoding="utf-8",
    )
    return ea


def test_explicit_features_override_conflicting_source_heuristics():
    strategy = detect_strategy(
        "class CGridHedgeDCA { double LotMultiplier; };",
        explicit_features=["strategy.entry.breakout"],
        explicit_signals=["atr_break"],
        detection_source="ea-ir",
    )

    assert strategy["family"] == "breakout"
    assert strategy["signals"] == ["breakout", "atr_break"]
    assert strategy["detection_source"] == "ea-ir"


def test_project_review_prefers_ea_ir_and_avoids_disabled_library_noise(tmp_path: Path):
    project = tmp_path / "project"
    _write_project(
        project,
        "// digits-tested: 5,3\n"
        "// Generic library contains Grid Hedge DCA LotMultiplier names.\n"
        "void OnTick(){}\n",
    )
    (project / "EA-IR.json").write_text(
        json.dumps(
            {
                "strategy": {
                    "features": ["strategy.entry.breakout"],
                    "signals": ["atr_break"],
                }
            }
        ),
        encoding="utf-8",
    )

    report = review_project(project)

    assert report["strategy"]["family"] == "breakout"
    assert report["strategy"]["detection_source"] == "ea-ir"
    assert not any(
        issue["title"] == "Grid/DCA without max level evidence"
        for issue in report["issues"]
    )


def test_generated_feature_contract_beats_source_names_and_ignores_false_flags(
    tmp_path: Path,
):
    project = tmp_path / "generated"
    _write_project(
        project,
        "// digits-tested: 5,3\n"
        "// VCK-FEATURE:strategy.dca.enabled\n"
        "const bool VCK_USE_DCA=false;\n"
        "// Grid Hedge DCA LotMultiplier library names must not enable a strategy.\n"
        "void OnTick(){}\n",
    )

    report = review_project(project)

    assert report["strategy"]["family"] == "custom"
    assert report["strategy"]["explicit_features"] == []
    assert report["strategy"]["detection_source"] == "generated-feature-contract"


def test_invalid_ea_ir_falls_back_to_generated_enabled_features(tmp_path: Path):
    project = tmp_path / "generated"
    _write_project(
        project,
        "// digits-tested: 5,3\n"
        "// VCK-IMPLEMENTED:strategy.entry.mean_reversion\n"
        "void OnTick(){}\n",
    )
    (project / "EA-IR.json").write_text("not-json", encoding="utf-8")

    report = review_project(project)

    assert report["strategy"]["family"] == "mean-reversion"
    assert report["strategy"]["detection_source"] == "generated-feature-contract"


def test_plain_source_uses_labeled_heuristic_fallback():
    strategy = detect_strategy("void OnTick(){ /* grid hedge */ }")

    assert strategy["family"] == "grid-hedge"
    assert strategy["detection_source"] == "source-heuristic"
    assert strategy["explicit_features"] == []


def test_explicit_grid_hedge_review_runs_risk_and_execution_checks(tmp_path: Path):
    project = tmp_path / "risky"
    _write_project(
        project,
        "// digits-tested: 5,3\n"
        "CTrade trade; double LotMultiplier=2.0;\n"
        "void CloseAll(string Symbol){}\n"
        "void Inspect(){PositionGetSymbol(0);m_position.Magic();}\n"
        "void OnTick(){Sleep(60000);for(int i=0;i<PositionsTotal();i++){trade.PositionClose(i);}}\n"
        "// expires 2027.01.01\n",
    )
    (project / "EA-IR.json").write_text(
        json.dumps(
            {
                "strategy": {
                    "features": [
                        "strategy.dca.enabled",
                        "strategy.hedge.standard",
                    ],
                    "signals": [],
                }
            }
        ),
        encoding="utf-8",
    )

    report = review_project(project)
    titles = {issue["title"] for issue in report["issues"]}

    assert report["strategy"]["family"] == "grid-hedge"
    assert "Raw synchronous PositionClose loop" in titles
    assert "Huge Sleep in OnTick" in titles
    assert "Grid/DCA without max level evidence" in titles
    assert "No hard drawdown stop evidence" in titles
    assert "No drawdown freeze evidence" in titles
    assert "Multiplier lot without broker volume clamp evidence" in titles
    assert "Grid strategy without persistence/recovery evidence" in titles


def test_fast_review_reports_stage_seven_as_skipped_only(tmp_path: Path):
    project = tmp_path / "project"
    _write_project(project)

    report = deep_review.run_deep_review(project, fast=True)

    assert report["schema_version"] == "2.5"
    assert [stage["id"] for stage in report["stages"]] == list(range(8))
    assert all(
        stage["status"] == "EXECUTED" for stage in report["stages"][:7]
    )
    assert report["stages"][7]["status"] == "SKIPPED"
    assert report["line_review"]["mode"] == "skipped"
    assert not any("Stage 7" in item for item in report["checked_categories"])


def test_full_review_claims_packet_preparation_not_llm_verdict(tmp_path: Path):
    project = tmp_path / "project"
    _write_project(project)

    report = deep_review.run_deep_review(project)
    markdown = deep_review.render_markdown(report)

    stage_seven = report["stages"][7]
    assert stage_seven["status"] == "EXECUTED"
    assert "no LLM verdict claimed" in stage_seven["detail"]
    assert report["line_review"]["mode"] == "pack"
    assert any("Stage 7" in item for item in report["checked_categories"])
    assert "## Stage execution" in markdown
    assert "Strategy detection:" in markdown


def test_single_file_review_does_not_scan_siblings_or_leak_tempdirs(
    tmp_path: Path, monkeypatch
):
    target = _write_project(tmp_path / "project")
    (target.parent / "Sibling.mq5").write_text(
        "// digits-tested: 5,3\nvoid OnTick(){Sleep(60000);}\n",
        encoding="utf-8",
    )
    temp_root = tmp_path / "isolations"
    temp_root.mkdir()
    monkeypatch.setattr(deep_review.tempfile, "tempdir", str(temp_root))

    report = deep_review.run_deep_review(target, fast=True)

    assert report["files_scanned"] == ["TruthEA.mq5"]
    assert not any("Sibling.mq5" in issue.get("evidence", "") for issue in report["issues"])
    assert list(temp_root.iterdir()) == []


def test_empty_review_target_returns_explicit_error(tmp_path: Path):
    report = deep_review.run_deep_review(tmp_path)

    assert report["ok"] is False
    assert "no .mq5/.mqh sources" in report["error"]


def test_cli_writes_only_truthful_requested_artifacts(tmp_path: Path, capsys):
    project = tmp_path / "project"
    _write_project(project)
    out = tmp_path / "review-output"

    exit_code = deep_review.main(
        [str(project), "--fast", "--json-only", "--out", str(out)]
    )

    assert exit_code == 1
    assert (out / "deep-review.md").is_file()
    data = json.loads((out / "deep-review.json").read_text(encoding="utf-8"))
    assert data["stages"][7]["status"] == "SKIPPED"
    assert not (out / "deep-review.docx").exists()
    assert "artifacts written" in capsys.readouterr().out
