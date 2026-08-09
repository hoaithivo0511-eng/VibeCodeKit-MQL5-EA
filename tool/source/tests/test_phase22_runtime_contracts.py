import json
from pathlib import Path

import pytest
from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.ea_ir import EAIR
from vibecodekit_mql5.runtime_input_contracts import (
    INPUT_CONTRACTS,
    RuntimeInputContract,
    validate_ir_values,
)


def base_ir() -> EAIR:
    return EAIR(
        identity={"name": "ContractSafeEA", "version": "1.0"},
        runtime={
            "account_model": "hedging",
            "symbols": ["EURUSD"],
            "timeframes": ["H1"],
        },
        strategy={
            "features": ["strategy.entry.signal_selectable", "strategy.dca.enabled"],
            "signals": ["rsi"],
            "signal_logic": "selectable",
            "parameters": {
                "dca_step_pips": 20,
                "async_execution": False,
                "execution_idempotency_policy": "reconcile_before_retry",
            },
        },
        risk={
            "base_lot": 0.01,
            "max_lot": 1.0,
            "max_spread_pips": 2.0,
            "max_open_positions": 8,
        },
        controls={},
    )


def test_contract_registry_has_unique_field_level_semantics():
    names = [contract.name for contract in INPUT_CONTRACTS]

    assert len(names) == len(set(names))
    assert len(names) >= 60
    assert all(contract.unit and contract.zero_semantics for contract in INPUT_CONTRACTS)
    by_name = {contract.name: contract for contract in INPUT_CONTRACTS}
    assert by_name["InpDailyLossPct"].sign == "non_negative"
    assert by_name["InpDailyLossMoney"].sign == "non_positive"
    assert by_name["InpBaseLot"].sign == "positive"
    assert by_name["InpBasketStopMoney"].zero_semantics == "disabled"


def test_contract_range_boundaries_are_explicit():
    contract = RuntimeInputContract(
        name="InpExample",
        source_path="risk.example",
        unit="ratio",
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
    )

    assert not contract.accepts(0)
    assert contract.accepts(0.5)
    assert contract.accepts(1)
    assert not contract.accepts(1.1)
    assert contract.range_text() == "(0, 1]"

    signed = RuntimeInputContract(
        name="InpSigned",
        source_path="risk.signed",
        unit="signed_ratio",
        minimum=-1,
        maximum=1,
    )
    assert signed.sign == "signed"


def test_prebuild_rejects_wrong_sign_and_type_values():
    ir = base_ir()
    ir.strategy["parameters"].update(
        {
            "basket_stop_money": 25,
            "daily_loss_money": "-10",
        }
    )

    blockers = validate_ir_values(ir)
    ids = {item["id"] for item in blockers}
    paths = {item["path"] for item in blockers}
    assert ids == {"RUNTIME-INPUT-OUT-OF-RANGE", "INVALID-RUNTIME-INPUT-TYPE"}
    assert paths == {
        "strategy.parameters.basket_stop_money",
        "strategy.parameters.daily_loss_money",
    }
    planned = plan(ir)
    assert not planned.ok
    assert paths <= {item.get("path") for item in planned.blockers}


def test_prebuild_rejects_zero_or_out_of_range_core_risk():
    ir = base_ir()
    ir.risk.update({"base_lot": 0, "daily_loss_pct": 101})

    blockers = plan(ir).blockers

    assert {item.get("input") for item in blockers} >= {
        "InpBaseLot",
        "InpDailyLossPct",
    }


def test_generated_runtime_gates_oninit_and_emits_bound_contract(tmp_path: Path):
    ir = base_ir()
    build = plan(ir)
    assert build.ok, build.blockers

    out = generate(ir, build, tmp_path / "project")
    main = (out / "Experts/ContractSafeEA/ContractSafeEA.mq5").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        (out / "RUNTIME-INPUT-CONTRACTS.json").read_text(encoding="utf-8")
    )

    assert main.index("bool ValidateOperationalInputs()") < main.index("int OnInit()")
    assert "if(!ValidateOperationalInputs())return INIT_PARAMETERS_INCORRECT" in main
    assert "VCK_CONFIG_INVALID|InpDailyLossMoney|unit=account_currency" in main
    assert "InpBaseLot>InpMaxLot" in main
    assert "InpFreezeDDPct>InpMaxDDPct" in main
    assert "positive_start_and_distance_required" in main
    assert manifest["ir_sha256"] == ir.sha256()
    assert len(manifest["contracts"]) == len(INPUT_CONTRACTS)
    assert manifest["contracts"][0]["range"]


def test_generation_refuses_blocked_plan_and_unapproved_overwrite(tmp_path: Path):
    blocked_ir = base_ir()
    blocked_ir.risk["base_lot"] = 0
    with pytest.raises(ValueError, match="build plan has blockers"):
        generate(blocked_ir, plan(blocked_ir), tmp_path / "blocked")

    ir = base_ir()
    build = plan(ir)
    destination = tmp_path / "existing"
    generate(ir, build, destination)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        generate(ir, build, destination)
