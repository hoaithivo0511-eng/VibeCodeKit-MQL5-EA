from __future__ import annotations

import importlib.util
import json
import shutil
import typing
from pathlib import Path

import pytest

from vibecodekit_mql5 import backtest, check_all, deep_review, vkmql
from vibecodekit_mql5._version import get_version
from vibecodekit_mql5.ea_doc_analyzer import read_reachable_mql_files
from vibecodekit_mql5.selftest import _check_version_triple_match


SOURCE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SOURCE_ROOT.parents[1]


def _write_project(project: Path, *, include: str, helper_source: str) -> None:
    main = project / "Experts" / "AuditEA" / "AuditEA.mq5"
    helper = project / "Include" / "AuditEA" / "Helper.mqh"
    unused = project / "Include" / "AuditEA" / "UnusedUnsafe.mqh"
    main.parent.mkdir(parents=True)
    helper.parent.mkdir(parents=True)
    main.write_text(
        "// digits-tested: 5,3\n"
        f"#include <AuditEA/{include}>\n"
        "int OnInit(){return INIT_SUCCEEDED;}\n"
        "void OnTick(){}\n",
        encoding="utf-8",
    )
    helper.write_text(helper_source, encoding="utf-8")
    unused.write_text(
        "bool CloseAllAsync(){MqlTradeRequest r;MqlTradeResult x;return OrderSendAsync(r,x);}\n",
        encoding="utf-8",
    )


def test_all_shipped_agent_contract_versions_match_canonical_rc7() -> None:
    expected = get_version()
    candidates = [
        SOURCE_ROOT / "agent-contract.json",
        SOURCE_ROOT / "scripts" / "vibecodekit_mql5" / "agent-contract.json",
        SOURCE_ROOT
        / "scripts"
        / "vibecodekit_mql5"
        / "resources"
        / "distribution"
        / "agent-contract.json",
    ]
    contracts = [path for path in candidates if path.is_file()]
    # A source checkout/archive ships all three synchronized surfaces. The
    # installed-wheel verification snapshot intentionally ships only its
    # canonical distribution contract.
    assert len(contracts) in {1, 3}
    assert candidates[0] in contracts
    versions = {
        path.relative_to(SOURCE_ROOT).as_posix(): json.loads(
            path.read_text(encoding="utf-8")
        )["kit"]["version"]
        for path in contracts
    }
    assert set(versions.values()) == {expected}, versions


def test_version_selftest_ignores_runtime_build_and_pytest_residue(tmp_path: Path) -> None:
    for name in ("pyproject.toml", "tool-catalog.json", "agent-contract.json"):
        shutil.copyfile(SOURCE_ROOT / name, tmp_path / name)
    stale = tmp_path / "pytest-of-root" / "case" / "agent-contract.json"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"kit":{"version":"0.0.0-stale"}}', encoding="utf-8")

    ok, detail = _check_version_triple_match(tmp_path)

    assert ok, detail


def test_backtest_runtime_annotations_resolve() -> None:
    hints = typing.get_type_hints(backtest._number)
    assert hints["default"] is typing.Any
    assert hints["return"] is typing.Any


def test_project_analyzers_ignore_unreachable_optional_headers(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, include="Helper.mqh", helper_source="double Safe(){return 1.0;}\n")

    reachable = read_reachable_mql_files(project)
    assert sorted(reachable) == [
        "Experts/AuditEA/AuditEA.mq5",
        "Include/AuditEA/Helper.mqh",
    ]
    assert check_all._stage_lint(project).status == "PASS"
    report = deep_review.run_deep_review(project, fast=True)
    assert "Include/AuditEA/UnusedUnsafe.mqh" not in report["files_scanned"]
    assert not any(
        issue.get("title", "").startswith(("AP-18:", "UX-09:"))
        for issue in report["issues"]
    )


def test_project_analyzers_keep_reachable_header_findings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        include="UnusedUnsafe.mqh",
        helper_source="double Safe(){return 1.0;}\n",
    )

    lint = check_all._stage_lint(project)
    assert lint.status == "FAIL"
    assert "AP-18" in lint.detail


def test_non_ui_close_helper_does_not_trigger_panel_rule(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        include="Helper.mqh",
        helper_source="bool CloseAllAsync(){return true;}\n",
    )

    lint = check_all._stage_lint(project)
    assert lint.status == "PASS", lint.detail


@pytest.mark.parametrize(
    ("preset", "name", "symbol", "timeframe"),
    (
        ("trend", "TrendPublic", "EURUSD", "H1"),
        ("mean-reversion", "MeanPublic", "GBPUSD", "M30"),
        ("breakout", "BreakPublic", "XAUUSD", "M15"),
        ("hedging-multi", "HedgePublic", "EURUSD", "H1"),
    ),
)
def test_public_build_presets_pass_static_lint(
    tmp_path: Path,
    preset: str,
    name: str,
    symbol: str,
    timeframe: str,
) -> None:
    project = tmp_path / name
    assert vkmql.new_main(
        [
            "build",
            preset,
            "--name",
            name,
            "--symbol",
            symbol,
            "--tf",
            timeframe,
            "--out",
            str(project),
        ]
    ) == 0

    lint = check_all._stage_lint(project)
    assert lint.status == "PASS", (preset, lint.detail)


def _load_server(path: Path):
    name = "test_" + path.parent.name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_mcp_bridges_reject_missing_required_arguments() -> None:
    mcp_root = REPO_ROOT / "tool" / "source" / "mcp"
    if not mcp_root.is_dir():
        return
    servers = sorted(mcp_root.glob("*/server.py"))
    assert len(servers) == 4
    for server_path in servers:
        server = _load_server(server_path)
        schema = next(
            item
            for item in server.TOOL_SCHEMAS
            if item.get("inputSchema", {}).get("required")
        )
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": schema["name"], "arguments": {}},
            }
        )
        assert response["error"]["code"] == -32602, server_path


def test_active_rc7_methodology_and_supply_chain_docs_are_current() -> None:
    status_path = REPO_ROOT / "docs" / "release" / "v3.3.0rc7" / "RC7-CANDIDATE-STATUS.md"
    if not status_path.is_file():
        return
    status = status_path.read_text(encoding="utf-8")
    retro = (
        SOURCE_ROOT / "skill" / "vibecode-mql5" / "references" / "retro-guards.md"
    ).read_text(encoding="utf-8")
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    )

    assert "c4924211d3dee507957c6ec2590c21d0563cfc59" in status
    assert "c444cfc3389719ac5ef8a5aaf32d2f1eed6c287d" in status
    assert "This is being corrected" not in status
    assert "A1`–`A14" in retro
    assert "| A13 |" in retro and "| A14 |" in retro
    assert "actions/checkout@v" not in workflows
    assert "actions/setup-python@v" not in workflows
    assert "actions/upload-artifact@v" not in workflows
    assert (SOURCE_ROOT / "requirements-ci.lock").is_file()

    native_workflow = (
        REPO_ROOT / ".github" / "workflows" / "rc7-github-native-compile.yml"
    ).read_text(encoding="utf-8")
    assert "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" in native_workflow
    assert "a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93" in native_workflow
    assert "using the SHA-pinned canonical MetaQuotes installer" in native_workflow
