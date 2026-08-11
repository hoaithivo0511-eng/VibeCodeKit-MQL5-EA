import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from vibecodekit_mql5 import auto_build, spec_from_prompt
from vibecodekit_mql5.intake import parse_text


def write_ir(tmp_path: Path, prompt: str) -> Path:
    ir = parse_text(prompt, strict=True)
    p = tmp_path / "EA-IR.json"
    p.write_text(json.dumps(ir.to_dict()), encoding="utf-8")
    return p


def test_auto_build_accepts_ir_and_generates_source(tmp_path: Path):
    ir_path = write_ir(tmp_path, "EA named TrendEA account netting EURUSD H1 trend-following EMA cross "
                                  "base lot 0.01 max lot 1.0 max spread 2 max positions 4")
    out = tmp_path / "out"
    rc = auto_build.main(["--spec", str(ir_path), "--out-dir", str(out), "--no-compile", "--no-gate", "--force"])
    assert rc == 0
    assert (out / "Experts/TrendEA/TrendEA.mq5").is_file()
    report = json.loads((out / "auto-build-report.json").read_text(encoding="utf-8"))
    assert report["status"]["source_complete"]
    assert not report["status"]["release_eligible"]


def test_default_prompt_output_feeds_canonical_auto_build(tmp_path: Path):
    ir_path = tmp_path / "EA-IR.json"
    prompt_rc = spec_from_prompt.main([
        (
            "EA named PromptTrend account netting EURUSD H1 trend-following EMA cross "
            "base lot 0.01 max lot 1.0 max spread 2 max positions 4"
        ),
        "--strict",
        "--out",
        str(ir_path),
    ])
    assert prompt_rc == 0

    out = tmp_path / "prompt-out"
    build_rc = auto_build.main([
        "--spec",
        str(ir_path),
        "--out-dir",
        str(out),
        "--no-compile",
        "--no-gate",
        "--force",
    ])
    assert build_rc == 0
    assert (out / "Experts/PromptTrend/PromptTrend.mq5").is_file()
    report = json.loads((out / "auto-build-report.json").read_text(encoding="utf-8"))
    assert report["status"]["source_complete"] is True
    assert report["status"]["release_eligible"] is False


def test_auto_build_ir_draft_does_not_suppress_unsupported_feature(tmp_path: Path):
    ir_path = write_ir(tmp_path, "EA named ZoneEA account hedging EURUSD H1 DCA Hedging Zone")
    out = tmp_path / "out"
    rc = auto_build.main(["--spec", str(ir_path), "--out-dir", str(out), "--draft", "--force"])
    assert rc == 1
    report = json.loads((out / "auto-build-report.json").read_text(encoding="utf-8"))
    assert not report["status"]["capability_satisfied"]
    assert not (out / "Experts").exists()


def test_auto_build_spec_loading_and_main_invocation_errors(tmp_path: Path, capsys):
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text("name: Sample\n", encoding="utf-8")
    assert auto_build.load_spec(yaml_path) == {"name": "Sample"}

    json_path = tmp_path / "spec.json"
    json_path.write_text('{"name":"Sample"}', encoding="utf-8")
    assert auto_build.load_spec(json_path) == {"name": "Sample"}
    scalar_path = tmp_path / "scalar.json"
    scalar_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        auto_build.load_spec(scalar_path)
    with pytest.raises(FileNotFoundError):
        auto_build.load_spec(tmp_path / "missing.json")
    assert auto_build.main(["--spec", str(tmp_path / "missing.json")]) == 2
    assert "spec not found" in capsys.readouterr().err

    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(spec_from_prompt.parse(
            "EA named TrendEA account netting EURUSD H1 trend-following"
        ).spec),
        encoding="utf-8",
    )
    assert auto_build.main([
        "--spec", str(legacy_path), "--docs-formats", "html,unknown"
    ]) == 2
    assert "unknown --docs-formats" in capsys.readouterr().err


def test_main_source_locator_covers_flat_named_fallback_and_missing(tmp_path: Path):
    flat = tmp_path / "flat"
    flat.mkdir()
    direct = flat / "FlatEA.mq5"
    direct.write_text("", encoding="utf-8")
    assert auto_build._locate_main_mq5(flat, "FlatEA") == direct

    nested = tmp_path / "nested"
    (nested / "other").mkdir(parents=True)
    named = nested / "other" / "NamedEA.mq5"
    named.write_text("", encoding="utf-8")
    assert auto_build._locate_main_mq5(nested, "NamedEA") == named

    fallback = tmp_path / "fallback"
    fallback.mkdir()
    only = fallback / "Renamed.mq5"
    only.write_text("", encoding="utf-8")
    assert auto_build._locate_main_mq5(fallback, "MissingName") == only
    assert auto_build._locate_main_mq5(tmp_path / "absent", "NoEA") is None


def test_pipeline_fail_fast_branches_still_finalize_honestly(tmp_path: Path, monkeypatch):
    spec = spec_from_prompt.parse(
        "EA named TrendEA account netting EURUSD H1 trend-following"
    ).spec
    monkeypatch.setattr(auto_build.docs_ship_stage_mod, "attach_docs_bundle", lambda *args, **kwargs: None)
    monkeypatch.setattr(auto_build.docs_ship_stage_mod, "attach_docs_assemble", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        auto_build,
        "_stage_build",
        lambda *args, **kwargs: auto_build.StageResult("build", ok=False, detail={"error": "build"}),
    )
    assert auto_build.run_pipeline(
        spec, tmp_path / "build-fail", skip_docs=True, skip_dashboard=True
    ).ok is False

    empty = tmp_path / "no-source"
    empty.mkdir()
    monkeypatch.setattr(
        auto_build,
        "_stage_build",
        lambda *args, **kwargs: auto_build.StageResult("build", ok=True, detail={"out_dir": str(empty)}),
    )
    no_source = auto_build.run_pipeline(
        spec, empty, skip_docs=True, skip_dashboard=True
    )
    assert no_source.stages[-1].name == "lint"

    out = tmp_path / "with-source"
    out.mkdir()
    source = out / "TrendEA.mq5"
    source.write_text("void OnTick(){}", encoding="utf-8")
    monkeypatch.setattr(
        auto_build,
        "_stage_build",
        lambda *args, **kwargs: auto_build.StageResult("build", ok=True, detail={"out_dir": str(out)}),
    )
    monkeypatch.setattr(
        auto_build, "_stage_lint", lambda _path: auto_build.StageResult("lint", ok=False)
    )
    assert auto_build.run_pipeline(
        spec, out, skip_docs=True, skip_dashboard=True
    ).ok is False

    monkeypatch.setattr(
        auto_build, "_stage_lint", lambda _path: auto_build.StageResult("lint", ok=True)
    )
    monkeypatch.setattr(
        auto_build, "_stage_compile", lambda _path: auto_build.StageResult("compile", ok=False)
    )
    assert auto_build.run_pipeline(
        spec, out, skip_gate=True, skip_docs=True, skip_dashboard=True
    ).ok is False

    monkeypatch.setattr(
        auto_build, "_stage_compile", lambda _path: auto_build.StageResult("compile", ok=True)
    )
    monkeypatch.setattr(
        auto_build, "_stage_gate", lambda _path, _mode: auto_build.StageResult("gate", ok=False)
    )
    assert auto_build.run_pipeline(
        spec, out, skip_docs=True, skip_dashboard=True
    ).ok is False


def test_package_dashboard_and_docs_helpers_are_fail_safe(tmp_path: Path, monkeypatch):
    blocked = auto_build.PipelineReport(spec={"name": "EA"}, out_dir=str(tmp_path))
    auto_build._maybe_attach_package(
        blocked, tmp_path, enabled=True, spec_path=None, zip_path=None
    )
    assert blocked.package["blocked"] is True

    green = auto_build.PipelineReport(
        spec={"name": "EA"},
        out_dir=str(tmp_path),
        stages=[
            auto_build.StageResult("compile", ok=True),
            auto_build.StageResult("gate", ok=True),
            auto_build.StageResult("backtest", ok=True),
        ],
        evidence_manifest={"ok": True},
    )
    manifest = SimpleNamespace(zip_path="ea.zip", groups={"source": ["EA.mq5"]}, artifacts=[1])
    monkeypatch.setattr(auto_build.package_mod, "package_out_dir", lambda *args, **kwargs: manifest)
    auto_build._maybe_attach_package(
        green, tmp_path, enabled=True, spec_path=None, zip_path=None
    )
    assert green.package["ok"] is True

    inside = tmp_path / "guide.md"
    inside.write_text("guide", encoding="utf-8")
    assert auto_build._docs_links_from_report(
        {"ok": True, "outputs": {"md": str(inside), "bad": 3}}, tmp_path
    ) == {"md": "guide.md"}
    assert auto_build._docs_links_from_report({"ok": True, "outputs": []}, tmp_path) == {}

    location = SimpleNamespace(to_dict=lambda: {"url": "file:///dashboard.html"})
    monkeypatch.setattr(auto_build.dashboard_mod, "write_dashboard", lambda digest, out: out / "dashboard.html")
    monkeypatch.setattr(auto_build.dashboard_mod, "publish", lambda path, publish_cmd=None: location)
    auto_build._maybe_attach_dashboard(green, tmp_path, skip=False, publish_cmd=None)
    assert green.dashboard == {"url": "file:///dashboard.html"}
    monkeypatch.setattr(
        auto_build.dashboard_mod,
        "write_dashboard",
        lambda digest, out: (_ for _ in ()).throw(OSError("disk")),
    )
    auto_build._maybe_attach_dashboard(green, tmp_path, skip=False, publish_cmd=None)
    assert "disk" in green.dashboard["error"]


def test_stage_build_and_compile_convert_tool_failures_to_results(tmp_path: Path, monkeypatch):
    invalid = {
        "name": "Bad",
        "preset": "missing",
        "stack": "netting",
        "symbol": "EURUSD",
        "timeframe": "H1",
    }
    assert auto_build._stage_build(invalid, tmp_path / "bad", False).ok is False

    fake_compile = SimpleNamespace(
        to_dict=lambda: {
            "success": False,
            "errors": ["compile error"],
            "warnings": [],
            "ex5_path": "",
        }
    )
    monkeypatch.setattr(auto_build.compile_mod, "compile_mq5", lambda _path: fake_compile)
    result = auto_build._stage_compile(tmp_path / "EA.mq5")
    assert result.ok is False
    assert result.detail["errors"] == ["compile error"]
