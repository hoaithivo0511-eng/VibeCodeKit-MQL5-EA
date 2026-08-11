from copy import deepcopy

from vibecodekit_mql5.feature_config import _validate_remote_commands
from tests.test_phase16_semantic_isolation import generic_ir


def _ids(ir):
    return {item["id"] for item in _validate_remote_commands(ir)}


def test_remote_validation_rejects_unknown_mode_and_missing_map():
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = {
        "mode": "unknown_mode",
        "symbol_scope": "managed_symbol",
    }
    ir.controls["pending_commands"] = {}

    ids = _ids(ir)

    assert "INVALID-REMOTE-COMMAND-OWNERSHIP-MODE" in ids
    assert "MISSING-REMOTE-COMMAND-MAP" in ids


def test_remote_validation_exercises_malformed_authenticated_commands():
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = {
        "mode": "authenticated_ea_order",
        "magic": 880001,
        "comment_prefix": "ORIONCMD",
        "symbol_scope": "managed_symbol",
    }
    ir.controls["pending_commands"] = {
        "1bad": {
            "order_type": "buy_stop",
            "price": 100,
            "action": {"type": "set_state", "path": "ea.enabled", "value": False},
        },
        "not_mapping": "bad",
        "bad_values": {
            "order_type": "market",
            "price": 0,
            "action": None,
        },
    }

    ids = _ids(ir)

    assert {
        "INVALID-REMOTE-COMMAND-ID",
        "INVALID-REMOTE-COMMAND",
        "INVALID-REMOTE-ORDER-TYPE",
        "INVALID-REMOTE-COMMAND-PRICE",
        "MISSING-REMOTE-COMMAND-ACTION",
    } <= ids


def test_manual_tokens_must_be_portable_and_unique():
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = {
        "mode": "manual_comment_token",
        "symbol_scope": "managed_symbol",
    }
    base = {
        "order_type": "buy_stop",
        "price": 100,
        "action": {"type": "set_state", "path": "ea.enabled", "value": False},
    }
    ir.controls["pending_commands"] = {
        "invalid_token": {**deepcopy(base), "comment_token": "x"},
        "token_a": {**deepcopy(base), "price": 101, "comment_token": "TOKEN_123"},
        "token_b": {**deepcopy(base), "price": 102, "comment_token": "TOKEN_123"},
    }

    ids = _ids(ir)

    assert "INVALID-REMOTE-COMMAND-COMMENT-TOKEN" in ids
    assert "REMOTE-COMMAND-TOKEN-COLLISION" in ids


def test_remote_actions_reject_invalid_state_scope_and_account_authority():
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = {
        "mode": "authenticated_ea_order",
        "magic": 880001,
        "comment_prefix": "ORIONCMD",
        "symbol_scope": "managed_symbol",
    }
    ir.controls["pending_commands"] = {
        "bad_state": {
            "order_type": "buy_stop",
            "price": 100,
            "action": {"type": "set_state", "path": "unknown.state", "value": "false"},
        },
        "bad_scope": {
            "order_type": "sell_stop",
            "price": 101,
            "action": {"type": "close_scope", "scope": "unknown_scope"},
        },
        "account_scope": {
            "order_type": "buy_limit",
            "price": 102,
            "action": {"type": "close_scope", "scope": "account_all"},
        },
        "unknown_action": {
            "order_type": "sell_limit",
            "price": 103,
            "action": {"type": "launch_missiles"},
        },
    }

    ids = _ids(ir)

    assert {
        "INVALID-SET-STATE-ACTION",
        "INVALID-CLOSE-SCOPE-ACTION",
        "ACCOUNT-WIDE-COMMAND-NOT-APPROVED",
        "UNSUPPORTED-REMOTE-ACTION",
    } <= ids


def test_ownership_shape_and_symbol_scope_are_fail_closed():
    ir = generic_ir()
    ir.controls["pending_command_ownership"] = {
        "mode": "authenticated_ea_order",
        "magic": 0,
        "comment_prefix": "x",
        "symbol_scope": "account",
        "unexpected": True,
    }

    ids = _ids(ir)

    assert {
        "INVALID-REMOTE-COMMAND-OWNERSHIP-SHAPE",
        "INVALID-REMOTE-COMMAND-OWNER-MAGIC",
        "INVALID-REMOTE-COMMAND-COMMENT-PREFIX",
        "INVALID-REMOTE-COMMAND-SYMBOL-SCOPE",
    } <= ids
