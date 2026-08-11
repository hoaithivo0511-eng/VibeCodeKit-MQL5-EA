import shutil
from pathlib import Path

from vibecodekit_mql5.distribution_snapshot import (
    SNAPSHOT_MANIFEST,
    locate_snapshot_root,
    verify_distribution_snapshot,
)


def test_distribution_snapshot_inventory_and_hashes_are_valid():
    root = locate_snapshot_root()
    assert (root / SNAPSHOT_MANIFEST).is_file()
    assert verify_distribution_snapshot(root) == []


def test_distribution_snapshot_detects_missing_and_modified_tests(tmp_path: Path):
    source = locate_snapshot_root()
    snapshot = tmp_path / "snapshot"
    shutil.copytree(source, snapshot)

    target = snapshot / "tests/test_phase29_generated_review_parity.py"
    target.write_text(target.read_text(encoding="utf-8") + "# mutation\n", encoding="utf-8")
    (snapshot / "tests/test_phase28_rc6_baseline.py").unlink()

    errors = verify_distribution_snapshot(snapshot)
    assert "snapshot hash mismatch: tests/test_phase29_generated_review_parity.py" in errors
    assert "snapshot size mismatch: tests/test_phase29_generated_review_parity.py" in errors
    assert "snapshot file missing: tests/test_phase28_rc6_baseline.py" in errors
