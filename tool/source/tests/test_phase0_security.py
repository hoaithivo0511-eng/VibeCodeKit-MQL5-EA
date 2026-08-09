from pathlib import Path

import pytest

from vibecodekit_mql5 import build
from vibecodekit_mql5.safe_paths import safe_join, validate_ea_name


def test_validate_ea_name_accepts_identifier():
    assert validate_ea_name("Apex_EA01") == "Apex_EA01"


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "A/B", "A B", ".hidden", "A-1"])
def test_validate_ea_name_rejects_path_or_invalid_identifier(name):
    with pytest.raises(ValueError):
        validate_ea_name(name)


def test_safe_join_blocks_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../../outside.mq5")


def test_build_rejects_traversal_name_before_writing(tmp_path: Path):
    out = tmp_path / "out"
    req = build.BuildRequest(
        preset="dca",
        name="../InjectedEA",
        symbol="EURUSD",
        tf="H1",
        stack="hedging",
        out_dir=out,
        scaffolds_root=build.DEFAULT_SCAFFOLDS,
        include_root=build.DEFAULT_INCLUDE,
    )
    with pytest.raises(ValueError):
        build.build(req)
    assert not out.exists()
