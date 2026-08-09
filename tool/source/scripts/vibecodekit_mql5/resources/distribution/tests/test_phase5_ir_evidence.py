import json
from pathlib import Path

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.composable_codegen import generate
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_verify import verify_project


def build_project(tmp_path: Path):
    ir = parse_text(
        "EA named EvidenceEA account netting EURUSD H1 trend-following EMA cross "
        "base lot 0.01 max lot 1 max spread 2 max positions 4",
        strict=True,
    )
    out = generate(ir, plan(ir), tmp_path / "EvidenceEA")
    return ir, out


def test_generated_project_is_statically_bound_to_ir(tmp_path: Path):
    ir, out = build_project(tmp_path)
    result = verify_project(out)
    assert result.ok
    assert result.static_verified
    assert not result.release_eligible
    assert result.ir_sha256 == ir.sha256()
    matrix = (out / "requirements-matrix.csv").read_text(encoding="utf-8")
    assert ",GENERATED" in matrix
    assert ",PLANNED" not in matrix


def test_artifact_tampering_is_detected(tmp_path: Path):
    _, out = build_project(tmp_path)
    main = out / "Experts/EvidenceEA/EvidenceEA.mq5"
    main.write_text(main.read_text(encoding="utf-8") + "\n// tampered\n", encoding="utf-8")
    result = verify_project(out)
    assert not result.ok
    assert any("artifact changed" in e for e in result.errors)


def test_native_evidence_from_another_ir_is_rejected(tmp_path: Path):
    ir, out = build_project(tmp_path)
    compile_evidence = tmp_path / "compile.json"
    tester_evidence = tmp_path / "tester.json"
    compile_evidence.write_text(json.dumps({
        "ir_sha256": "0" * 64,
        "status": "PASS",
        "evidence_type": "actual_metaeditor",
        "artifacts": [{"path": "x", "sha256": "1" * 64}],
    }), encoding="utf-8")
    tester_evidence.write_text(json.dumps({
        "ir_sha256": ir.sha256(),
        "status": "PASS",
        "evidence_type": "actual_mt5_strategy_tester",
        "artifacts": [{"path": "x", "sha256": "1" * 64}],
    }), encoding="utf-8")
    result = verify_project(out, compile_evidence=compile_evidence, tester_evidence=tester_evidence)
    assert not result.ok
    assert not result.release_eligible
    assert any("compile evidence IR hash mismatch" in e for e in result.errors)


def test_matching_trusted_native_evidence_allows_release(tmp_path: Path):
    ir, out = build_project(tmp_path)
    compile_evidence = tmp_path / "compile.json"
    tester_evidence = tmp_path / "tester.json"
    base = {
        "ir_sha256": ir.sha256(),
        "status": "PASS",
        "artifacts": [{"path": "result", "sha256": "1" * 64}],
    }
    compile_evidence.write_text(json.dumps({**base, "evidence_type": "actual_metaeditor"}), encoding="utf-8")
    tester_evidence.write_text(json.dumps({**base, "evidence_type": "actual_mt5_strategy_tester"}), encoding="utf-8")
    result = verify_project(out, compile_evidence=compile_evidence, tester_evidence=tester_evidence)
    assert result.ok
    assert result.release_eligible
