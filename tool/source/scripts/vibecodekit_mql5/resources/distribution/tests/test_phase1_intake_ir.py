from pathlib import Path

from vibecodekit_mql5.intake import parse_text


def feature_set(ir):
    return set(ir.strategy["features"])


def test_trend_filter_does_not_collapse_dca_to_trend_strategy():
    ir = parse_text(
        "Build EA DCA Step Multiplier with trend filter EMA MACD, account hedging, EURUSD H1, name AtlasDCA",
        strict=True,
    )
    feats = feature_set(ir)
    assert "strategy.dca.enabled" in feats
    assert "strategy.dca.step_multiplier" in feats
    assert "strategy.filter.trend" in feats
    assert "strategy.entry.trend_following" not in feats
    assert ir.runtime["account_model"] == "hedging"
    assert ir.ready_for_planning


def test_multi_symbol_is_preserved_not_collapsed():
    ir = parse_text("EA named BasketEA account netting EURUSD GBPUSD USDJPY H1 trend-following", strict=True)
    assert ir.runtime["symbols"] == ["EURUSD", "GBPUSD", "USDJPY"]


def test_punctuated_number_parses_without_crash():
    ir = parse_text("EA named RiskEA account netting EURUSD H1 trend-following risk 0.5%. daily loss 4.0.")
    assert ir.risk["per_trade_pct"] == 0.5
    assert ir.risk["daily_loss_pct"] == 4.0


def test_hedge_and_explicit_netting_is_a_conflict():
    ir = parse_text("EA named BadEA account netting EURUSD H1 with standard hedge", strict=True)
    assert any(c["id"] == "CONFLICT-HEDGE-NETTING" for c in ir.conflicts)
    assert not ir.ready_for_planning


def test_missing_critical_fields_block_in_strict_mode():
    ir = parse_text("Build a strategy with RSI", strict=True)
    assert not ir.ready_for_planning
    paths = {a["path"] for a in ir.ambiguities if a["severity"] == "blocking"}
    assert {"identity.name", "runtime.account_model", "runtime.symbols", "runtime.timeframes"} <= paths


def test_ccbsn_is_a_golden_fixture_not_a_fixed_template():
    text = Path(__file__).with_name("fixtures_ccbsn.txt").read_text(encoding="utf-8")
    ir = parse_text(text, source="CCBSN-manual")
    feats = feature_set(ir)
    required = {
        "strategy.dca.enabled",
        "strategy.dca.step_multiplier",
        "strategy.sniper.same_chain",
        "strategy.sniper.cross_chain",
        "strategy.sniper.partial",
        "strategy.hedge.standard",
        "strategy.hedge.zone",
        "strategy.lot_balance",
        "strategy.filter.trend",
    }
    assert required <= feats
    assert "controls.pending_order_remote" in ir.controls["features"]
    assert ir.runtime["account_model"] == "hedging"
    assert ir.strategy["topology"] == "multi_engine"
    assert ir.identity["version"] == "3.0.3"
    assert ir.controls["new_cycle_semantics"] == "true_means_allow_new_cycle"


def test_generic_breakout_fixture_stays_generic():
    ir = parse_text("EA named PulseBreak account netting XAUUSD M15 breakout with ATR break and max spread 2.5", strict=True)
    assert "strategy.entry.breakout" in feature_set(ir)
    assert "strategy.dca.enabled" not in feature_set(ir)
    assert ir.strategy["signals"] == ["atr_break"]
    assert ir.risk["max_spread_pips"] == 2.5
