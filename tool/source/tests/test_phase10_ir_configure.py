import json
from pathlib import Path

import pytest

from vibecodekit_mql5.ea_ir import from_dict
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_configure import apply_profile, run


def test_profile_adds_operational_values_with_provenance():
    ir = parse_text("EA named GenericDCA account hedging DCA Step RSI", strict=False)
    profile = {
        "schema_version": "1",
        "profile_name": "demo-safe",
        "overrides": {
            "runtime": {"symbol_mode": "chart_symbol", "timeframe_mode": "chart_timeframe"},
            "risk": {"base_lot": 0.01, "max_lot": 0.2, "max_spread_pips": 2.5, "max_open_positions": 8},
            "strategy": {"parameters": {"dca_step_pips": 25.0}},
        },
        "resolve_ambiguities": ["AMB-SYMBOL", "AMB-TIMEFRAME"],
        "assumptions": ["Attach the EA to the intended symbol/timeframe."],
    }
    out = apply_profile(ir, profile, source="profile.yaml")
    assert out.risk["base_lot"] == 0.01
    assert out.strategy["parameters"]["dca_step_pips"] == 25.0
    cfg = {r.path: r for r in out.requirements if r.id.startswith("CFG-")}
    assert cfg["risk.base_lot"].status == "confirmed"
    assert cfg["risk.base_lot"].source_refs[0].source == "profile.yaml"
    assert out.metadata["configuration_profile"] == "demo-safe"
    assert out.sha256() != ir.sha256()


def test_profile_rejects_unknown_root():
    ir = parse_text("EA named X account netting EURUSD H1 trend-following", strict=True)
    with pytest.raises(ValueError, match="unsupported profile override roots"):
        apply_profile(ir, {"schema_version": "1", "overrides": {"filesystem": {"path": "/tmp"}}})


def test_profile_run_round_trips_hash(tmp_path: Path):
    ir = parse_text("EA named X account netting EURUSD H1 trend-following", strict=True)
    ir_path = tmp_path / "ir.json"
    ir_path.write_text(json.dumps(ir.to_dict()), encoding="utf-8")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({
        "schema_version": "1",
        "overrides": {"risk": {"base_lot": 0.01, "max_lot": 1.0, "max_spread_pips": 2.0, "max_open_positions": 4}},
    }), encoding="utf-8")
    out_path = tmp_path / "configured.json"
    configured = run(ir_path, profile_path, out_path)
    loaded = from_dict(json.loads(out_path.read_text(encoding="utf-8")))
    assert loaded.sha256() == configured.sha256()


def test_atomic_command_overlay_removes_stale_extracted_command_requirements():
    from vibecodekit_mql5.intake import parse_text
    extracted = parse_text(
        "EA named AtomicMap account hedging EURUSD H1. "
        "Pending order control Buy Stop 11111 Stop EA.",
        source="manual", strict=True,
    )
    assert extracted.controls["pending_commands"]
    profile = {
        "schema_version": "1",
        "profile_name": "replace-command-map",
        "resolve_ambiguities": [a["id"] for a in extracted.ambiguities],
        "overrides": {
            "controls": {
                "pending_commands": {
                    "custom_resume": {
                        "order_type": "sell_limit", "price": 22222,
                        "action": {"type": "set_state", "path": "ea.enabled", "value": True},
                    }
                }
            }
        },
    }
    configured = apply_profile(extracted, profile, source="profile")
    assert set(configured.controls["pending_commands"]) == {"custom_resume"}
    command_requirements = [r.path for r in configured.requirements if r.path.startswith("controls.pending_commands.")]
    assert command_requirements
    assert all("custom_resume" in path for path in command_requirements)
