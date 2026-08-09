from pathlib import Path

import pytest

from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_verify import verify_project
from tests.test_phase16_semantic_isolation import generic_ir


@pytest.mark.parametrize(
    "prompt,name,expected,forbidden",
    [
        (
            "EA named NorthTrend account netting EURUSD H1 trend-following EMA cross "
            "base lot 0.01 max lot 1 max spread 2 max positions 4",
            "NorthTrend",
            ("strategy.entry.signals.ema_cross",),
            ("strategy.hedge.zone", "strategy.sniper.cross_chain", "controls.pending_order_remote"),
        ),
        (
            "EA named RangePulse account netting XAUUSD M15 breakout ATR break "
            "base lot 0.01 max lot 1 max spread 2.5 max positions 4",
            "RangePulse",
            ("strategy.entry.breakout", "strategy.entry.signals.atr_break"),
            ("strategy.hedge.zone", "strategy.lot_balance", "controls.pending_order_remote"),
        ),
        (
            "EA named BandReturn account netting GBPUSD M30 mean-reversion Bollinger "
            "base lot 0.01 max lot 1 max spread 2 max positions 3",
            "BandReturn",
            ("strategy.entry.mean_reversion", "strategy.entry.signals.bollinger_bands"),
            ("strategy.hedge.zone", "strategy.reverse_entry", "controls.pending_order_remote"),
        ),
    ],
)
def test_unrelated_archetypes_are_not_polluted_by_recovery_fixture(
    tmp_path: Path, prompt: str, name: str, expected: tuple[str, ...], forbidden: tuple[str, ...]
):
    ir = parse_text(prompt, strict=True)
    build = plan(ir)
    assert build.ok, build.blockers
    paths = {feature.path for feature in build.features}
    for path in expected:
        assert path in paths
    for path in forbidden:
        assert path not in paths

    out = generate(ir, build, tmp_path / name)
    assert verify_project(out).ok
    rendered = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in out.rglob("*") if p.is_file()
    )
    for token in ("CCBSN", "Bo.Botfx", "999999", "666666", "888888", "555555"):
        assert token not in rendered


def test_generic_recovery_project_preserves_arbitrary_command_protocol(tmp_path: Path):
    ir = generic_ir()
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "OrionRecovery")
    # This hand-built IR intentionally has no extracted requirement rows, so the
    # source generator is exercised directly while traceability is covered by
    # document/prompt acceptance tests.

    config = (out / "Include/OrionRecovery/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/OrionRecovery/OrionRecovery.mq5").read_text(encoding="utf-8")
    assert "12345.25000000" in config and "23456.75000000" in config
    assert "VCK_SRC_HEDGE_ZONE" in main
    assert "ExposureAllowed" in main
    for token in ("999999", "666666", "888888", "555555", "CCBSN"):
        assert token not in config + main


def test_lint_recognizes_pip_spread_and_entry_delay_guards():
    from vibecodekit_mql5.lint_best_practice import detect_ap8, detect_ap9

    source = """
    CTrade Trade;
    bool SpreadAllowed(){ MqlTick t; return SymbolInfoTick(_Symbol,t) && (t.ask-t.bid)/_Point < 20; }
    bool EntryDelayPassed(){ return TimeCurrent()-last_entry >= 2; }
    """
    assert detect_ap8("EA.mq5", source, source) == []
    assert detect_ap9("EA.mq5", source, source) == []
