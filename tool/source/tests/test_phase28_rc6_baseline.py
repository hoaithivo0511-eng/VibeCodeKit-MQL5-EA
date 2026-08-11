import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rc6_version_triple_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    catalog = json.loads((ROOT / "tool-catalog.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "agent-contract.json").read_text(encoding="utf-8"))

    assert 'version = "3.3.0rc6"' in pyproject
    assert catalog["kit_version"] == "3.3.0rc6"
    assert contract["kit"]["version"] == "3.3.0rc6"


def test_rc5_artifacts_remain_historical_inputs():
    repo = ROOT.parents[1]
    assert (repo / "tool/vibecodekit-mql5-v3.3.0rc5-source-full.zip").is_file()
    assert (repo / "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl").is_file()
