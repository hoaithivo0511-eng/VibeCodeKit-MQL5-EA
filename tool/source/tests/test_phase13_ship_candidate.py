import json
from pathlib import Path

import yaml

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.composable_codegen import generate
from vibecodekit_mql5.contract_check import check_project_contract
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_verify import verify_project


def configured_ir():
    ir = parse_text(
        "EA named ShipGuard account hedging EURUSD H1 RSI DCA Step 25 "
        "DCA Step Multiplier 1.2 standard hedge hedge trigger positions 6 "
        "hedge lot pct 50 basket TP pips 8 base lot 0.01 max lot 1 "
        "max spread 2 max positions 8",
        strict=True,
    )
    ir.strategy.setdefault("parameters", {}).update({"dca_mode": "step_multiplier", "hedge_variant": "single_opposite_leg_v1", "execution_idempotency_policy": "reconcile_before_retry"})
    return ir


def test_generated_project_contains_grid_risk_and_operational_modules(tmp_path: Path):
    ir = configured_ir()
    out = generate(ir, plan(ir), tmp_path / "ShipGuard")
    main = (out / "Experts/ShipGuard/ShipGuard.mq5").read_text(encoding="utf-8")
    cfg = (out / "Include/ShipGuard/Config.mqh").read_text(encoding="utf-8")
    for rel in (
        "Include/ShipGuard/Core/AsyncTradeExecutor.mqh",
        "Include/ShipGuard/Risk/GridRiskGuard.mqh",
        "Include/ShipGuard/Exit/BasketCloseEngine.mqh",
        "Include/ShipGuard/State/PersistentStateStore.mqh",
        "Include/ShipGuard/Telemetry/StructuredLogger.mqh",
        "Include/ShipGuard/Telemetry/MfeMaeLogger.mqh",
    ):
        assert (out / rel).is_file()
    assert "GridRisk.MustStop()" in main
    assert "GridRisk.FreezeDD()" in main
    assert "InpMaxLevelsBuy" in cfg and "InpMaxLevelsSell" in cfg
    assert "InpMaxDDPct" in cfg and "InpFreezeDDPct" in cfg


def test_generated_governance_is_valid_and_bound_to_ir(tmp_path: Path):
    ir = configured_ir()
    out = generate(ir, plan(ir), tmp_path / "ShipGuard")
    spec = yaml.safe_load((out / "EA-SPEC.yaml").read_text(encoding="utf-8"))
    contract = json.loads((out / "AI-BUILD-CONTRACT.json").read_text(encoding="utf-8"))
    assert spec["ir_sha256"] == ir.sha256()
    assert spec["risk"]["max_drawdown_pct"] > 0
    assert contract["project"]["name"] == "ShipGuard"
    result = check_project_contract(out)
    assert result.ok, result.errors
    verify = verify_project(out)
    assert verify.static_verified


def test_evidence_manifest_is_truthful_v2_and_not_release_eligible(tmp_path: Path):
    ir = configured_ir()
    out = generate(ir, plan(ir), tmp_path / "ShipGuard")
    manifest = json.loads((out / "evidence/manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2.0"
    assert manifest["ir_sha256"] == ir.sha256()
    assert manifest["compile_ok"] is False
    assert manifest["backtest_ok"] is False
    assert manifest["release_eligible"] is False
    assert manifest["summary"]["release_eligible"] is False
