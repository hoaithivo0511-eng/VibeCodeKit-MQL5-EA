from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _repo_root() -> Path | None:
    candidate = SOURCE_ROOT.parents[1]
    workflow = candidate / ".github/workflows/rc7-github-native-compile.yml"
    return candidate if workflow.is_file() else None


def test_canonical_native_probe_exists_and_is_workflow_default() -> None:
    repo = _repo_root()
    if repo is None:
        return
    probe = repo / "scripts/native/ProbeEA.mq5"
    assert probe.is_file(), "canonical RC7 native ProbeEA target is missing"
    text = probe.read_text(encoding="utf-8")
    assert "#property strict" in text
    assert "OnInit" in text
    assert "OnTick" in text

    workflow = (repo / ".github/workflows/rc7-github-native-compile.yml").read_text(
        encoding="utf-8"
    )
    assert "default: scripts/native/ProbeEA.mq5" in workflow
    assert "'scripts/native/ProbeEA.mq5'" in workflow
    assert "|| 'scripts/native/ProbeEA.mq5'" in workflow
