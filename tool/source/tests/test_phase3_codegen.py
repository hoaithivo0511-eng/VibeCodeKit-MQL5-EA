import json
from pathlib import Path

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.composable_codegen import generate
from vibecodekit_mql5.ea_ir import from_dict
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_build import run


def supported_ir():
    ir = parse_text(
        "EA named AtlasDCA account hedging EURUSD H1 DCA Step 25 DCA Step Multiplier 1.2 "
        "martingale lot multiplier 1.2 basket TP pips 8 standard hedge "
        "hedge trigger positions 6 hedge lot pct 50 tỉa lệnh cùng chuỗi "
        "sniper trigger positions 5 sniper target money 1 tỉa lệnh 1 phần partial close pct 30 "
        "RSI trend filter EMA MACD base lot 0.01 max lot 1.0 max spread 2 max positions 8",
        strict=True,
    )
    ir.strategy.setdefault("parameters", {}).update({
        "hedge_variant": "single_opposite_leg_v1",
        "same_chain_sniper_variant": "oldest_best_pair_v1",
        "execution_idempotency_policy": "reconcile_before_retry",
    })
    return ir


def test_composable_codegen_generates_real_order_path_and_modules(tmp_path: Path):
    ir = supported_ir()
    build_plan = plan(ir)
    assert build_plan.ok
    out = generate(ir, build_plan, tmp_path / "AtlasDCA")
    main = (out / "Experts/AtlasDCA/AtlasDCA.mq5").read_text(encoding="utf-8")
    assert "Trade.Open(" in main
    assert "ManageDCA(" in main
    assert "ManageHedge(" in main
    assert "ManageSniper(" in main
    assert "OnTradeTransaction" in main
    assert "{{" not in main and "TODO" not in main
    assert (out / "Include/AtlasDCA/Signal/EntryEngine.mqh").is_file()
    assert (out / "requirements-matrix.csv").is_file()


def test_ir_hash_is_preserved_across_written_artifacts(tmp_path: Path):
    ir = supported_ir()
    out = generate(ir, plan(ir), tmp_path / "AtlasDCA")
    raw = json.loads((out / "EA-IR.json").read_text(encoding="utf-8"))
    loaded = from_dict(raw)
    assert loaded.sha256() == ir.sha256()
    assert ir.sha256() in (out / "Experts/AtlasDCA/AtlasDCA.mq5").read_text(encoding="utf-8")


def test_ir_build_blocks_unsupported_before_source_generation(tmp_path: Path):
    ir = parse_text("EA named ZoneEA account hedging EURUSD H1 DCA Hedging Zone", strict=True)
    ir_path = tmp_path / "zone-ir.json"
    ir_path.write_text(json.dumps(ir.to_dict()), encoding="utf-8")
    out = tmp_path / "out"
    report = run(ir_path, out)
    assert not report["status"]["capability_satisfied"]
    assert not (out / "Experts").exists()


def test_full_ir_build_reports_source_complete(tmp_path: Path):
    ir = supported_ir()
    ir_path = tmp_path / "ir.json"
    ir_path.write_text(json.dumps(ir.to_dict()), encoding="utf-8")
    report = run(ir_path, tmp_path / "project")
    assert report["status"]["source_generated"]
    assert report["status"]["source_complete"]
    assert report["status"]["compile_verified"] is False
    assert report["status"]["release_eligible"] is False
