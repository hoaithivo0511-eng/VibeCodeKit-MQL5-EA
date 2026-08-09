import json
from pathlib import Path

import pytest
import yaml
from vibecodekit_mql5 import auto_build, spec_from_prompt, spec_schema
from vibecodekit_mql5.ea_ir import from_dict as ir_from_dict


def test_legacy_parser_dca_with_trend_filter_is_not_misclassified_as_trend():
    result = spec_from_prompt.parse(
        "EA named AtlasDCA account hedging EURUSD H1 DCA Step Multiplier with trend filter EMA"
    )
    assert result.spec["preset"] == "dca"
    assert result.spec["stack"] == "hedging"
    assert any("multi-engine" in w for w in result.warnings)


def test_legacy_parser_does_not_clamp_explicit_incompatible_account_model():
    result = spec_from_prompt.parse("EA named BadDCA account netting EURUSD H1 DCA")
    assert result.errors
    assert "silent clamp" in result.errors[0]


def test_spec_from_prompt_default_emits_real_canonical_ir(tmp_path: Path):
    out = tmp_path / "ir.json"
    rc = spec_from_prompt.main([
        "EA named TrendEA account netting EURUSD H1 trend-following",
        "--strict", "--out", str(out),
    ])
    assert rc == 0
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "3.1"
    assert raw["runtime"]["account_model"] == "netting"
    assert {"identity", "runtime", "strategy", "risk", "controls", "requirements"} <= set(raw)
    assert not ({"preset", "stack", "symbol", "timeframe"} & set(raw))
    assert ir_from_dict(raw).sha256() == raw["ir_sha256"]


def test_ir_flag_remains_a_compatibility_alias_for_default(capsys):
    rc = spec_from_prompt.main([
        "EA named TrendEA account netting EURUSD H1 trend-following",
        "--ir", "--strict", "--explain",
    ])
    assert rc == 0
    raw = json.loads(capsys.readouterr().out)
    assert raw["schema_version"] == "3.1"


def test_legacy_output_requires_flag_and_carries_non_release_marker(tmp_path: Path):
    out = tmp_path / "ea-spec.yaml"
    rc = spec_from_prompt.main([
        "EA named TrendEA account netting EURUSD H1 trend-following",
        "--legacy", "--strict", "--out", str(out),
    ])
    assert rc == 0
    raw = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "schema_version" not in raw
    assert raw["compatibility"] == {
        "mode": "legacy_scaffold",
        "release_eligible": False,
    }
    spec_schema.validate(raw, valid_presets=auto_build.build_mod.PRESETS)


def test_legacy_marker_is_a_release_blocker(tmp_path: Path):
    legacy = spec_from_prompt.parse(
        "EA named TrendEA account netting EURUSD H1 trend-following"
    ).spec
    report = auto_build.run_pipeline(
        legacy,
        tmp_path / "legacy-out",
        skip_compile=True,
        skip_gate=True,
        skip_dashboard=True,
        skip_docs=True,
    )
    assert "--legacy-scaffold" in report.unsafe_flags_used
    assert report.status["release_eligible"] is False
    assert report.evidence_manifest["release_eligible"] is False


def test_legacy_compatibility_marker_cannot_claim_release_eligibility():
    legacy = spec_from_prompt.parse(
        "EA named TrendEA account netting EURUSD H1 trend-following"
    ).spec
    legacy["compatibility"]["release_eligible"] = True
    with pytest.raises(spec_schema.SpecValidationError, match="must be false"):
        spec_schema.validate(legacy, valid_presets=auto_build.build_mod.PRESETS)


def test_legacy_mapping_cannot_be_relabelled_by_adding_schema_version_only():
    legacy = spec_from_prompt.parse(
        "EA named TrendEA account netting EURUSD H1 trend-following"
    ).spec
    legacy["schema_version"] = "3.1"
    with pytest.raises(ValueError, match="cannot be relabelled"):
        ir_from_dict(legacy)


def test_legacy_strict_rejects_blank_and_underspecified_prompts(capsys):
    assert spec_from_prompt.main(["", "--legacy", "--strict"]) == 1
    assert "empty prompt" in capsys.readouterr().err

    assert spec_from_prompt.main(["trend strategy", "--legacy", "--strict"]) == 1
    assert "missing fields" in capsys.readouterr().err


def test_legacy_rich_prompt_renders_yaml_blocks_and_explanation(capsys):
    rc = spec_from_prompt.main([
        (
            "EA named RiskTrend account netting EURUSD H1 trend risk 0.5% "
            "SL 30 TP 60 MACD and SAR trailing start 10 trailing distance 5"
        ),
        "--legacy",
        "--explain",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    raw = yaml.safe_load(captured.out)
    assert raw["risk"]["per_trade_pct"] == 0.5
    assert raw["signals"]["logic"] == "AND"
    assert raw["compatibility"]["release_eligible"] is False
    assert "inferred:" in captured.err


def test_legacy_strict_refuses_multi_engine_loss(capsys):
    rc = spec_from_prompt.main([
        (
            "EA named AtlasDCA account hedging EURUSD H1 DCA Step Multiplier "
            "with trend filter EMA"
        ),
        "--legacy",
        "--strict",
    ])
    assert rc == 1
    assert "remove --legacy" in capsys.readouterr().err


def test_legacy_multi_symbol_warning_is_never_silent():
    result = spec_from_prompt.parse(
        "EA named Basket account netting EURUSD GBPUSD H1 portfolio basket"
    )
    assert result.spec["preset"] == "portfolio-basket"
    assert any("multi-symbol" in warning for warning in result.warnings)
