import json
from pathlib import Path

from vibecodekit_mql5 import spec_from_prompt


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


def test_spec_from_prompt_ir_mode_emits_canonical_ir(tmp_path: Path):
    out = tmp_path / "ir.json"
    rc = spec_from_prompt.main([
        "EA named TrendEA account netting EURUSD H1 trend-following",
        "--ir", "--strict", "--out", str(out),
    ])
    assert rc == 0
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "3.1"
    assert raw["runtime"]["account_model"] == "netting"
