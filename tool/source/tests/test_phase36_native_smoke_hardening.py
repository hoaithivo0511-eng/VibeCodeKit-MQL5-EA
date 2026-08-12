from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _repo_root() -> Path | None:
    candidate = SOURCE_ROOT.parents[1]
    action = candidate / ".github/actions/mql5-native-compile/action.yml"
    return candidate if action.is_file() else None


def test_native_action_prepares_toolchain_before_compile() -> None:
    repo = _repo_root()
    if repo is None:
        return
    action = (repo / ".github/actions/mql5-native-compile/action.yml").read_text(
        encoding="utf-8"
    )
    assert "Prepare-VKMql5Toolchain.ps1" in action
    assert "Finalize-VKMql5ToolchainEvidence.ps1" in action
    assert "-InstallerUrl ''" in action
    assert "-WarmStdlib never" in action
    assert "steps.prepare-toolchain.outputs.metaeditor" in action


def test_installer_exit_code_is_not_the_success_authority() -> None:
    repo = _repo_root()
    if repo is None:
        return
    prepare = (
        repo / ".github/actions/mql5-native-compile/Prepare-VKMql5Toolchain.ps1"
    ).read_text(encoding="utf-8")
    assert 'if ($proc.ExitCode -ne 0) { throw' not in prepare
    assert "MetaEditor64.exe is present; accepting observed installation state" in prepare
    assert "MetaEditor64.exe not found after MT5 installer exit" in prepare
    assert "MT5 installer SHA-256 mismatch" in prepare


def test_stdlib_auto_warm_is_verified_not_assumed() -> None:
    repo = _repo_root()
    if repo is None:
        return
    prepare = (
        repo / ".github/actions/mql5-native-compile/Prepare-VKMql5Toolchain.ps1"
    ).read_text(encoding="utf-8")
    assert "Start-Sleep -Seconds 45" in prepare
    assert "Trade/Trade.mqh not materialized after 45-second terminal warmup" in prepare
    assert "MQL5 stdlib verified" in prepare
    assert "#include" in prepare


def test_finalize_restores_installer_and_stdlib_provenance() -> None:
    repo = _repo_root()
    if repo is None:
        return
    finalize = (
        repo / ".github/actions/mql5-native-compile/Finalize-VKMql5ToolchainEvidence.ps1"
    ).read_text(encoding="utf-8")
    assert "metaeditor.installer_sha256" in finalize
    assert "toolchain.stdlib_warmed" in finalize
    assert "UTF8Encoding($false)" in finalize
