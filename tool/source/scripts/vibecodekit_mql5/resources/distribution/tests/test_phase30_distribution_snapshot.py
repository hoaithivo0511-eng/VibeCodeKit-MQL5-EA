import shutil
from pathlib import Path

from vibecodekit_mql5.distribution_snapshot import (
    IGNORED_RUNTIME_DIRS,
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
    shutil.copytree(
        source,
        snapshot,
        ignore=shutil.ignore_patterns(*IGNORED_RUNTIME_DIRS),
    )

    cache = snapshot / "tests/__pycache__/runtime-generated.pyc"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"runtime cache is not distribution input")

    target = snapshot / "tests/test_phase29_generated_review_parity.py"
    target.write_text(target.read_text(encoding="utf-8") + "# mutation\n", encoding="utf-8")
    (snapshot / "tests/test_phase28_rc6_baseline.py").unlink()

    errors = verify_distribution_snapshot(snapshot)
    assert not any("__pycache__" in error for error in errors)
    assert "snapshot hash mismatch: tests/test_phase29_generated_review_parity.py" in errors
    assert "snapshot size mismatch: tests/test_phase29_generated_review_parity.py" in errors
    assert "snapshot file missing: tests/test_phase28_rc6_baseline.py" in errors


def test_snapshot_ignores_known_tool_caches_but_rejects_rogue_files(tmp_path: Path):
    source = locate_snapshot_root()
    snapshot = tmp_path / "snapshot"
    shutil.copytree(
        source,
        snapshot,
        ignore=shutil.ignore_patterns(*IGNORED_RUNTIME_DIRS),
    )

    for relative in (
        ".ruff_cache/CACHEDIR.TAG",
        ".pytest_cache/v/cache/nodeids",
        "pytest-of-root/pytest-1/runtime.txt",
        "tests/__pycache__/generated.pyc",
    ):
        path = snapshot / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime cache", encoding="utf-8")
    rogue = snapshot / "undeclared-release-input.txt"
    rogue.write_text("must not be ignored", encoding="utf-8")

    errors = verify_distribution_snapshot(snapshot)

    assert not any("cache" in error.lower() for error in errors)
    assert errors == ["undeclared snapshot file: undeclared-release-input.txt"]
