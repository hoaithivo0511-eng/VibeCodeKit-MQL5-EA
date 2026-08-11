import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def packaged_contract_root() -> Path:
    if (ROOT / "pyproject.toml").is_file():
        return ROOT
    from vibecodekit_mql5.distribution_snapshot import locate_snapshot_root

    return locate_snapshot_root()


def test_rc6_version_triple_is_consistent():
    contract_root = packaged_contract_root()
    pyproject = (contract_root / "pyproject.toml").read_text(encoding="utf-8")
    catalog = json.loads((contract_root / "tool-catalog.json").read_text(encoding="utf-8"))
    contract = json.loads((contract_root / "agent-contract.json").read_text(encoding="utf-8"))

    assert 'version = "3.3.0rc6"' in pyproject
    assert catalog["kit_version"] == "3.3.0rc6"
    assert contract["kit"]["version"] == "3.3.0rc6"


def test_rc5_artifacts_remain_historical_inputs():
    repo = ROOT.parents[1]
    source_zip = repo / "tool/vibecodekit-mql5-v3.3.0rc5-source-full.zip"
    wheel = repo / "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl"
    if source_zip.is_file() or wheel.is_file():
        assert source_zip.is_file()
        assert wheel.is_file()
    else:
        # Standalone RC6 source ZIP and wheel channels intentionally exclude
        # repository-level historical binaries. Keep the channel strict about
        # its own identity instead of skipping this test.
        changelog = ROOT / "CHANGELOG.md"
        if changelog.is_file():
            assert changelog.read_text(encoding="utf-8").startswith("## [3.3.0rc6]")
        else:
            from vibecodekit_mql5._version import get_version
            from vibecodekit_mql5.distribution_snapshot import (
                locate_snapshot_root,
                verify_distribution_snapshot,
            )

            assert get_version() == "3.3.0rc6"
            assert verify_distribution_snapshot(locate_snapshot_root()) == []
