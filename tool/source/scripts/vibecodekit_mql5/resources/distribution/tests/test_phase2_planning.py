from pathlib import Path

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.traceability import rows


def test_supported_generic_dca_plan_has_dependencies_and_traceability():
    ir = parse_text(
        "EA named AtlasDCA account hedging EURUSD H1 DCA Step 25 DCA Step Multiplier 1.2 "
        "martingale lot multiplier 1.2 basket TP pips 8 base lot 0.01 max lot 1.0 "
        "max spread 2 max positions 8",
        strict=True,
    )
    build_plan = plan(ir)
    assert build_plan.ok
    paths = [f.path for f in build_plan.features]
    assert paths.index("strategy.dca.enabled") < paths.index("strategy.dca.step_multiplier")
    assert "strategy.sizing.martingale" in paths
    assert any(r["implementation"] == "CDCAEngine::RequiredDistance" for r in rows(ir, build_plan))


def test_advanced_feature_without_operational_config_blocks_instead_of_using_defaults():
    ir = parse_text("EA named ZoneEA account hedging EURUSD H1 DCA with Hedging Zone", strict=True)
    build_plan = plan(ir)
    assert not build_plan.ok
    assert any(
        b.get("id") == "MISSING-FEATURE-CONFIG" and
        "strategy.hedge.zone" in b.get("required_by", [])
        for b in build_plan.blockers
    )


def test_ccbsn_fixture_is_understood_and_blocked_only_until_configured():
    text = Path(__file__).with_name("fixtures_ccbsn.txt").read_text(encoding="utf-8")
    ir = parse_text(text, source="CCBSN-manual")
    build_plan = plan(ir)
    assert not build_plan.ok
    assert any(b.get("id") == "MISSING-FEATURE-CONFIG" for b in build_plan.blockers)
    planned = {f.path for f in build_plan.features}
    assert "strategy.dca.step_multiplier" in planned
    assert "strategy.hedge.standard" in planned
    assert "strategy.hedge.zone" in planned
    assert "strategy.sniper.cross_chain" in planned
    assert "strategy.lot_balance" in planned


def test_beta_features_can_be_forbidden_for_release_plan():
    ir = parse_text("EA named SniperEA account hedging EURUSD H1 DCA tỉa lệnh cùng chuỗi", strict=True)
    build_plan = plan(ir, allow_beta=False)
    assert any(b.get("id") == "BETA-FEATURE-BLOCKED" for b in build_plan.blockers)
