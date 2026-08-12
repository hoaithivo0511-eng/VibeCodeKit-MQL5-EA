"""Runtime capability disclosure for honest EA build pipelines."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import which
from typing import Any
import os
import sys

from .env_paths import resolve_metaeditor_path, resolve_terminal_path


@dataclass
class CapabilityReport:
    schema_version: str
    platform: str
    has_wine: bool
    has_metaeditor_env: bool
    has_terminal_env: bool
    compile_backends: list[str]
    backtest_backends: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _github_compile_config() -> tuple[bool, list[str]]:
    missing: list[str] = []
    repository = os.environ.get("VKMQL_GITHUB_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY")
    ref = os.environ.get("VKMQL_GITHUB_REF") or os.environ.get("GITHUB_REF_NAME")
    token = (
        os.environ.get("VKMQL_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    if not repository:
        missing.append("VKMQL_GITHUB_REPOSITORY/GITHUB_REPOSITORY")
    if not ref:
        missing.append("VKMQL_GITHUB_REF/GITHUB_REF_NAME")
    if not token:
        missing.append("VKMQL_GITHUB_TOKEN/GITHUB_TOKEN/GH_TOKEN")
    return not missing, missing


def detect_capabilities() -> CapabilityReport:
    has_wine = which("wine") is not None or which("wine64") is not None
    metaeditor = resolve_metaeditor_path()
    terminal = resolve_terminal_path()
    is_windows = sys.platform.startswith("win")

    compile_backends: list[str] = []
    backtest_backends: list[str] = []
    limitations: list[str] = []

    if metaeditor and is_windows:
        compile_backends.append("actual_metaeditor")
    elif metaeditor and has_wine:
        compile_backends.append("wine_metaeditor")
        limitations.append("Wine MetaEditor is development/diagnostic evidence, not native Windows release authority.")
    elif has_wine:
        compile_backends.append("wine_metaeditor_possible")
        limitations.append("Wine is available but METAEDITOR64/METAEDITOR_PATH is not configured.")
    else:
        limitations.append("No local MetaEditor backend detected; compile evidence cannot be produced locally.")

    github_ready, github_missing = _github_compile_config()
    if github_ready:
        compile_backends.append("github_actions_metaeditor")
    elif len(github_missing) < 3:
        limitations.append(
            "GitHub Actions compile backend is partially configured; missing: "
            + ", ".join(github_missing)
        )

    worker_url = os.environ.get("VKMQL_WORKER_URL") or os.environ.get("MQL5_WORKER_URL")
    if worker_url:
        compile_backends.append("remote_worker_metaeditor")

    if terminal and is_windows:
        backtest_backends.append("actual_mt5_strategy_tester")
    elif terminal and has_wine:
        backtest_backends.append("wine_strategy_tester_possible")
        limitations.append("Wine Strategy Tester is development evidence unless native parity policy explicitly promotes it.")
    elif has_wine:
        backtest_backends.append("wine_strategy_tester_possible")
        limitations.append("Wine is available but MT5_TERMINAL64/MT5_TERMINAL_PATH is not configured.")
    else:
        limitations.append("No MT5 terminal backend detected; Strategy Tester evidence cannot be produced locally.")

    limitations.append("Imported reports are parse-only and are not release evidence without provenance manifest.")
    limitations.append("Internal AP/Trader/RRI checks are heuristics, not industry standards.")

    return CapabilityReport(
        schema_version="1.1",
        platform=os.name,
        has_wine=has_wine,
        has_metaeditor_env=bool(metaeditor),
        has_terminal_env=bool(terminal),
        compile_backends=compile_backends,
        backtest_backends=backtest_backends,
        limitations=limitations,
    )


def write_capability_report(path: str | Path) -> dict[str, Any]:
    report = detect_capabilities().to_dict()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    import json

    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
