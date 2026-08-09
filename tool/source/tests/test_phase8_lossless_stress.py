from pathlib import Path

import pytest

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.composable_codegen import generate
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_verify import verify_project


@pytest.mark.parametrize("prompt,name", [
    (
        "EA named TrendCore account netting EURUSD H1 trend-following EMA cross "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        "TrendCore",
    ),
    (
        "EA named PulseBreak account netting XAUUSD M15 breakout ATR break "
        "base lot 0.01 max lot 1 max spread 2.5 max positions 4",
        "PulseBreak",
    ),
    (
        "EA named MeanBand account netting GBPUSD M30 mean-reversion Bollinger "
        "base lot 0.01 max lot 1 max spread 2 max positions 3",
        "MeanBand",
    ),
    (
        "EA named AtlasDCA account hedging EURUSD H1 RSI DCA Step 25 DCA Step Multiplier 1.2 "
        "martingale lot multiplier 1.2 basket TP pips 8 base lot 0.01 max lot 1 "
        "max spread 2 max positions 8",
        "AtlasDCA",
    ),
])
def test_generic_archetypes_build_and_verify(tmp_path: Path, prompt: str, name: str):
    ir = parse_text(prompt, strict=True)
    build_plan = plan(ir)
    assert build_plan.ok, build_plan.blockers
    out = generate(ir, build_plan, tmp_path / name)
    result = verify_project(out)
    assert result.ok
    main = out / f"Experts/{name}/{name}.mq5"
    assert "Trade.Open(" in main.read_text(encoding="utf-8")


def test_multi_symbol_is_preserved_and_blocks_single_symbol_codegen():
    ir = parse_text(
        "EA named BasketEA account netting EURUSD GBPUSD USDJPY H1 trend-following "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    assert ir.runtime["symbols"] == ["EURUSD", "GBPUSD", "USDJPY"]
    build_plan = plan(ir)
    assert any(b["id"] == "MULTI-SYMBOL-CODEGEN-UNSUPPORTED" for b in build_plan.blockers)


def test_multi_timeframe_blocks_instead_of_taking_first():
    ir = parse_text(
        "EA named MTF account netting EURUSD H1 M15 trend-following "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    assert ir.runtime["timeframes"] == ["H1", "M15"]
    assert any(b["id"] == "MULTI-TIMEFRAME-CODEGEN-UNSUPPORTED" for b in plan(ir).blockers)


def test_filter_indicators_are_not_promoted_to_entry_signals():
    ir = parse_text(
        "EA named FilterEA account hedging EURUSD H1 RSI trend filter EMA MACD DCA Step 25 "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    assert ir.strategy["signals"] == ["rsi"]
    assert "strategy.filter.ema" in ir.strategy["features"]
    assert "strategy.filter.macd" in ir.strategy["features"]


def test_multiple_signals_without_composition_are_blocking():
    ir = parse_text(
        "EA named AmbiguousSignals account netting EURUSD H1 RSI CCI "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    assert any(a["id"] == "AMB-SIGNAL-LOGIC" for a in ir.ambiguities)
    assert not plan(ir).ok


def test_selectable_multiple_signals_are_supported():
    ir = parse_text(
        "EA named SelectableEA account netting EURUSD H1 selectable signals RSI CCI "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    assert ir.strategy["signal_logic"] == "selectable"
    assert plan(ir).ok
