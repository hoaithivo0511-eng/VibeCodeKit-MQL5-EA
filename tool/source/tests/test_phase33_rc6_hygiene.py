"""Historical RC6 and current integrated repository-hygiene contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

SOURCE_ROOT = Path(__file__).resolve().parents[1]
RC6_VERSION = "3.3.0rc6"


def repository_root() -> Path | None:
    candidate = SOURCE_ROOT.parents[1]
    marker = candidate / "scripts/maintenance/check_rc6_hygiene.py"
    return candidate if marker.is_file() else None


def packaged_contract_root() -> Path:
    if (SOURCE_ROOT / "pyproject.toml").is_file():
        return SOURCE_ROOT
    from vibecodekit_mql5.distribution_snapshot import locate_snapshot_root

    return locate_snapshot_root()


def current_version() -> str:
    from vibecodekit_mql5._version import get_version

    return get_version()


def test_root_release_surfaces_are_current_and_fail_closed() -> None:
    repo = repository_root()
    if repo is None:
        readme = SOURCE_ROOT / "README.md"
        draft_notice = SOURCE_ROOT / "DRAFT-NOT-VALIDATED.txt"
        if readme.is_file() or draft_notice.is_file():
            text = readme.read_text(encoding="utf-8")
            assert current_version() in text or f"v{current_version()}" in text
            notice = draft_notice.read_text(encoding="utf-8")
            assert "not compiled, gated, or validated" in notice
            assert "Do not use draft artifacts for live trading" in notice
        else:
            from vibecodekit_mql5.distribution_snapshot import (
                locate_snapshot_root,
                verify_distribution_snapshot,
            )

            assert current_version() == "3.3.0rc7"
            assert verify_distribution_snapshot(locate_snapshot_root()) == []
        return

    readme = (repo / "README.md").read_text(encoding="utf-8")
    structure = (repo / "STRUCTURE.md").read_text(encoding="utf-8")
    trust = (repo / "RELEASE-TRUST.yaml").read_text(encoding="utf-8")

    # Root docs must tell both truths: RC6 is the latest published historical
    # tester release, while the integrated source follows the current package.
    assert RC6_VERSION in readme
    assert current_version() in readme or f"v{current_version()}" in readme
    assert "release_eligible=false" in readme
    assert RC6_VERSION in structure
    assert current_version() in structure or f"v{current_version()}" in structure
    assert "historical" in structure.lower()

    # RC6 runner trust root remains immutable historical release evidence.
    assert "RC6 native release trust root" in trust
    assert yaml.safe_load(trust)["runner_keys"] == []


def test_active_workflows_preserve_rc6_history_and_never_auto_promote_release() -> None:
    repo = repository_root()
    if repo is None:
        catalog = json.loads(
            (packaged_contract_root() / "tool-catalog.json").read_text(encoding="utf-8")
        )
        assert catalog["kit_version"] == current_version()
        return

    workflow_dir = repo / ".github/workflows"
    expected = {
        "release-gate.yml": "RC6 Development Gate",
        "rc6-native-evidence-verify.yml": "RC6 Native Evidence Gate",
        "rc6-package-integration.yml": "RC6 Package Integration Gate",
    }
    for name, label in expected.items():
        text = (workflow_dir / name).read_text(encoding="utf-8")
        assert f"name: {label}" in text
        assert "release_eligible=true" not in text
    package = (workflow_dir / "rc6-package-integration.yml").read_text(encoding="utf-8")
    assert "build_rc6_candidate.py repro-check" in package
    assert "actions/upload-artifact@v6" in package
    assert "git push" not in package


def test_native_runbook_uses_ir_generated_source_and_real_case_logs() -> None:
    repo = repository_root()
    if repo is None:
        from vibecodekit_mql5.provenance import BOUND_INPUT_SCHEMA, REQUIRED_RESTART_CASES

        assert BOUND_INPUT_SCHEMA == "2.1"
        assert len(REQUIRED_RESTART_CASES) == 4
        return
    runbook = (repo / "docs/release/v3.3.0rc6/TASK-18-NATIVE-EVIDENCE-RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    runner = (repo / "scripts/native/Invoke-RC6NativeEvidence.ps1").read_text(encoding="utf-8")
    assert "-EaIr" in runbook
    assert "-EaPath" not in runbook
    assert "mql5-ir-build" in runbook
    assert "[string]$EaIr" in runner
    for case_id in (
        "abrupt_terminal_kill",
        "restart_reconcile",
        "no_duplicate_order",
        "legacy_v1_migration_restart",
    ):
        assert f"{case_id}.log" in runbook


def test_hygiene_checker_passes_the_git_inventory() -> None:
    repo = repository_root()
    if repo is None:
        from vibecodekit_mql5.distribution_snapshot import (
            locate_snapshot_root,
            verify_distribution_snapshot,
        )

        assert verify_distribution_snapshot(locate_snapshot_root()) == []
        return
    result = subprocess.run(
        ["python", "scripts/maintenance/check_rc6_hygiene.py", "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0, payload["errors"]
    assert payload["ok"] is True


def test_historical_candidates_stay_fail_closed() -> None:
    repo = repository_root()
    if repo is None:
        # Historical candidate files are repository-only evidence and are not
        # duplicated into the installed wheel. The package must still identify
        # the current integrated kit version honestly.
        assert current_version() == "3.3.0rc7"
        return
    rc5 = json.loads(
        (repo / "docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json").read_text(encoding="utf-8")
    )
    assert rc5["kit_version"] == "3.3.0rc5"
    assert rc5["release_eligible"] is False
    assert (repo / "VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip").is_file()


def test_task16_traceability_is_closed_but_native_remains_planned() -> None:
    repo = repository_root()
    if repo is None:
        contract = json.loads(
            (packaged_contract_root() / "agent-contract.json").read_text(encoding="utf-8")
        )
        assert contract["kit"]["version"] == current_version()
        return
    requirements = (repo / "docs/release/v3.3.0rc6/REQUIREMENTS.csv").read_text(encoding="utf-8")
    assert (
        'REQ-033,P2,"Version README plan ledger and package metadata remain consistent",RC5 deep audit,COMPLETED,16'
        in requirements
    )
    assert (
        'REQ-032,P0,"Trusted MetaEditor MT5 and restart evidence is mandatory for release",Release contract,PLANNED,18'
        in requirements
    )