from copy import deepcopy
from pathlib import Path

import pytest
from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.intake import parse_text

from tests.test_phase16_semantic_isolation import generic_ir


def test_remote_commands_require_explicit_three_factor_ownership():
    ir = generic_ir()
    ir.controls.pop("pending_command_ownership")

    blockers = plan(ir).blockers

    assert any(item["id"] == "MISSING-REMOTE-COMMAND-OWNERSHIP" for item in blockers)


@pytest.mark.parametrize(
    ("ownership", "blocker"),
    [
        (
            {"magic": 0, "comment_prefix": "OWNEDCMD", "symbol_scope": "managed_symbol"},
            "INVALID-REMOTE-COMMAND-OWNER-MAGIC",
        ),
        (
            {"magic": 880001, "comment_prefix": "x", "symbol_scope": "managed_symbol"},
            "INVALID-REMOTE-COMMAND-COMMENT-PREFIX",
        ),
        (
            {"magic": 880001, "comment_prefix": "OWNEDCMD", "symbol_scope": "account"},
            "INVALID-REMOTE-COMMAND-SYMBOL-SCOPE",
        ),
    ],
)
def test_each_remote_ownership_factor_is_validated(ownership, blocker):
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = ownership

    assert any(item["id"] == blocker for item in plan(ir).blockers)


def test_intake_marks_unowned_command_channel_as_blocking_ambiguity():
    ir = parse_text(
        "EA named OwnershipGate account hedging EURUSD H1.\n"
        "COMMAND pause: buy_limit 12345 -> set_state ea.enabled=false",
        source="ownership-spec",
        strict=True,
    )

    assert ir.controls["pending_command_ownership"] == {}
    assert any(
        item["id"] == "AMB-REMOTE-COMMAND-OWNERSHIP"
        and item["severity"] == "blocking"
        for item in ir.ambiguities
    )


def test_generated_handler_claims_deletes_then_applies_once(tmp_path: Path):
    ir = generic_ir()
    ir.controls["pending_commands"]["flatten_managed"] = {
        "order_type": "buy_stop",
        "price": 34567,
        "action": {"type": "close_scope", "scope": "managed_all"},
    }
    build = plan(ir)
    assert build.ok, build.blockers

    out = generate(ir, build, tmp_path / "remote-safe")
    config = (out / "Include/OrionRecovery/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/OrionRecovery/OrionRecovery.mq5").read_text(
        encoding="utf-8"
    )
    ledger = (
        out / "Include/OrionRecovery/Core/RemoteCommandLedger.mqh"
    ).read_text(encoding="utf-8")

    assert "VCK_COMMAND_OWNER_MAGIC=880001" in config
    assert 'VCK_COMMAND_COMMENT_PREFIX="ORIONCMD"' in config
    assert "OrderGetInteger(ORDER_MAGIC)==VCK_COMMAND_OWNER_MAGIC" in main
    assert "StringFind(comment,VCK_COMMAND_COMMENT_PREFIX)==0" in main
    assert (
        "CommandLedger.Claim(ticket,command_index))return true;"
        "return ContinueRemoteCommand()" in main
    )
    continue_start = main.index("bool ContinueRemoteCommand()")
    delete_at = main.index("Trade.DeleteOrder(ticket)", continue_start)
    apply_at = main.index("ApplyRemoteCommandOnce(command_index)", continue_start)
    assert delete_at < apply_at
    assert "RemoteCommandEffectSatisfied(command_index)" in main
    assert "effect not satisfied; no replay" in main
    assert "RemoteManagedScopeEmpty(0)" in main
    assert "if(used){Trade.DeleteOrder" not in main
    assert "GlobalVariableSetOnCondition" in ledger
    assert "VCK_CMD_CLAIMED" in ledger
    assert "VCK_CMD_DELETED" in ledger
    assert "VCK_CMD_APPLYING" in ledger
    assert "VCK_CMD_APPLIED" in ledger
    assert "GlobalVariablesFlush" in ledger


def test_generated_command_protocol_remains_project_defined(tmp_path: Path):
    first = generic_ir()
    second = deepcopy(first)
    second.identity["name"] = "SecondControl"
    second.controls["pending_command_ownership"] = {
        "magic": 992244,
        "comment_prefix": "SECONDCMD",
        "symbol_scope": "managed_symbol",
    }

    first_out = generate(first, plan(first), tmp_path / "first")
    second_out = generate(second, plan(second), tmp_path / "second")
    first_config = (first_out / "Include/OrionRecovery/Config.mqh").read_text(
        encoding="utf-8"
    )
    second_config = (second_out / "Include/SecondControl/Config.mqh").read_text(
        encoding="utf-8"
    )

    assert "ORIONCMD" in first_config and "880001" in first_config
    assert "SECONDCMD" in second_config and "992244" in second_config
    assert "SECONDCMD" not in first_config
