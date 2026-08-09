from pathlib import Path

from vibecodekit_mql5.dist_package import collect_dist_files, is_excluded


def test_build_and_egg_info_never_ship():
    assert is_excluded(Path("build/lib/module.py"), include_dev=True)
    assert is_excluded(Path("scripts/vibecodekit_mql5_ea.egg-info/PKG-INFO"), include_dev=True)


def test_collection_excludes_build_metadata(tmp_path: Path):
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    (tmp_path / "build/lib").mkdir(parents=True)
    (tmp_path / "build/lib/x.py").write_text("x", encoding="utf-8")
    (tmp_path / "pkg.egg-info").mkdir()
    (tmp_path / "pkg.egg-info/PKG-INFO").write_text("x", encoding="utf-8")
    files = {p.as_posix() for p in collect_dist_files(tmp_path, include_dev=True)}
    assert files == {"README.md"}

def test_coverage_database_never_ships(tmp_path: Path):
    assert is_excluded(Path(".coverage"), include_dev=False)
    assert is_excluded(Path(".coverage"), include_dev=True)
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    (tmp_path / ".coverage").write_bytes(b"runtime-data")
    files = {p.as_posix() for p in collect_dist_files(tmp_path, include_dev=True)}
    assert files == {"README.md"}



def test_runtime_coverage_reports_are_never_shipped():
    from vibecodekit_mql5.dist_package import is_excluded
    assert is_excluded(Path(".coverage"), include_dev=True)
    assert is_excluded(Path("coverage.json"), include_dev=True)
    assert is_excluded(Path("coverage.json"), include_dev=False)
