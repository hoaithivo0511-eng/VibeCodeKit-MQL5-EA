from pathlib import Path

from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_configure import apply_profile


def test_structured_command_ids_and_prices_are_project_defined(tmp_path: Path):
    text = """
    EA named NimbusControl uses MT5 hedging account on EURUSD H1.
    Use RSI entry signal, DCA step, base lot 0.01, max lot 1.0,
    max spread 2 pips and max 6 positions. Allow conservative defaults.
    COMMAND pause_alpha: buy_limit 12345 -> set_state ea.enabled=false
    COMMAND flatten_magic: sell_stop 23456 -> close_scope managed_all
    """
    ir = parse_text(text, source="nimbus-spec", strict=True)
    commands = ir.controls["pending_commands"]
    assert set(commands) == {"pause_alpha", "flatten_magic"}
    assert commands["pause_alpha"]["price"] == 12345.0
    assert commands["flatten_magic"]["action"] == {"type": "close_scope", "scope": "managed_all"}

    # Add explicit semantics required by the generic recovery builder.
    configured = apply_profile(ir, {
        "schema_version": "1",
        "profile_name": "nimbus-test",
        "resolve_ambiguities": [a["id"] for a in ir.ambiguities],
        "overrides": {
        "runtime": {"account_model": "hedging", "symbols": ["EURUSD"], "timeframes": ["H1"]},
        "controls": {
            "pending_command_ownership": {
                "magic": 881234,
                "comment_prefix": "NIMBUSCMD",
                "symbol_scope": "managed_symbol",
            },
        },
        "strategy": {
            "features": ["strategy.entry.signal_selectable", "strategy.dca.enabled", "strategy.dca.step"],
            "signals": ["rsi"], "signal_logic": "selectable",
            "parameters": {
                "dca_step_pips": 20, "async_execution": False,
                "execution_idempotency_policy": "reconcile_before_retry",
            },
        },
        "risk": {"base_lot": 0.01, "max_lot": 1.0, "max_spread_pips": 2.0, "max_open_positions": 6},
        },
    }, source="nimbus-profile")
    build = plan(configured)
    assert build.ok, build.blockers
    out = generate(configured, build, tmp_path / "nimbus")
    cfg = (out / "Include/NimbusControl/Config.mqh").read_text(encoding="utf-8")
    assert "InpCmd_PAUSE_ALPHA=12345.0" in cfg
    assert "InpCmd_FLATTEN_MAGIC=23456.0" in cfg
    for forbidden in ("999999", "666666", "888888", "555555"):
        assert forbidden not in cfg


def test_unknown_natural_language_remote_effect_is_not_guessed():
    text = """
    EA named ArbitraryBot uses MT5 hedging account on EURUSD H1.
    Mobile Control uses Buy Stop 34567 to rotate the proprietary recovery lattice.
    """
    ir = parse_text(text, source="arbitrary-manual", strict=True)
    assert ir.controls["pending_commands"] == {}
    assert any(a["id"] == "AMB-REMOTE-COMMAND-MAP" for a in ir.ambiguities)


def test_natural_language_table_has_no_fixed_required_command_set():
    text = """
    EA named OneCommand uses MT5 hedging account on EURUSD H1.
    Pending order control:
    Sell Limit 45678 Enable New Cycle and resume new entries.
    """
    ir = parse_text(text, source="one-command", strict=True)
    commands = ir.controls["pending_commands"]
    assert len(commands) == 1
    only = next(iter(commands.values()))
    assert only["order_type"] == "sell_limit"
    assert only["price"] == 45678.0
    assert only["action"] == {"type": "set_state", "path": "cycle.new_enabled", "value": True}
