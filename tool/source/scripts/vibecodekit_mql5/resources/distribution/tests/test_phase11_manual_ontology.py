from pathlib import Path

from vibecodekit_mql5.intake import parse_text


def test_full_ccbsn_fixture_detects_documented_feature_groups():
    ir = parse_text(Path(__file__).with_name("fixtures_ccbsn.txt").read_text(encoding="utf-8"), source="CCBSN")
    features = set(ir.strategy["features"])
    expected = {
        "strategy.lottery.after_sl",
        "strategy.exit.single_tp",
        "strategy.exit.adaptive_basket_tp",
        "strategy.exit.account_money",
        "strategy.exit.side_money",
        "strategy.exit.stepped_target",
        "strategy.exit.trend_reversal",
        "strategy.exit.balance_difference",
        "strategy.time.sessions",
        "strategy.filter.zone_cycle",
    }
    assert expected <= features
    assert "controls.reset_lots" in ir.controls["features"]


def test_ccbsn_signal_menu_is_preserved_without_promoting_macd_filter():
    ir = parse_text(Path(__file__).with_name("fixtures_ccbsn.txt").read_text(encoding="utf-8"), source="CCBSN")
    signals = set(ir.strategy["signals"])
    expected = {
        "cci_reversal", "stochastic_reversal", "rsi_reversal",
        "pinbar_engulfing", "candle_color", "no_condition", "random",
        "external_indicator", "smc_all_with", "smc_all_against",
        "smc_internal_with", "smc_internal_against",
        "smc_swing_with", "smc_swing_against",
        "supertrend", "utbot", "ichimoku_kumo_break",
    }
    assert expected <= signals
    assert "macd" not in signals


def test_explicit_macd_signal_still_parses():
    ir = parse_text("EA named M account netting EURUSD H1 selectable signals MACD cross RSI base lot 0.01 max lot 1 max spread 2 max positions 4", strict=True)
    assert "macd" in ir.strategy["signals"]
