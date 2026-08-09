import json
from pathlib import Path

from vibecodekit_mql5 import auto_build
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


def test_auto_build_ir_draft_does_not_suppress_unsupported_feature(tmp_path: Path):
    ir_path = write_ir(tmp_path, "EA named ZoneEA account hedging EURUSD H1 DCA Hedging Zone")
    out = tmp_path / "out"
    rc = auto_build.main(["--spec", str(ir_path), "--out-dir", str(out), "--draft", "--force"])
    assert rc == 1
    report = json.loads((out / "auto-build-report.json").read_text(encoding="utf-8"))
    assert not report["status"]["capability_satisfied"]
    assert not (out / "Experts").exists()
