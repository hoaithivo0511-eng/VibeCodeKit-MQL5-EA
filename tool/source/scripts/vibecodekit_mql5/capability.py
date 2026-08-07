"""Runtime capability disclosure for honest EA build pipelines."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from shutil import which
import os
from typing import Any

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


def detect_capabilities() -> CapabilityReport:
    has_wine = which("wine") is not None or which("wine64") is not None
    metaeditor = resolve_metaeditor_path()
    terminal = resolve_terminal_path()

    compile_backends: list[str] = []
    backtest_backends: list[str] = []
    limitations: list[str] = []

    if metaeditor:
        compile_backends.append("actual_metaeditor")
    elif has_wine:
        compile_backends.append("wine_metaeditor_possible")
        limitations.append("Wine is available but METAEDITOR64/METAEDITOR_PATH is not configured.")
    else:
        limitations.append("No MetaEditor backend detected; compile evidence cannot be produced locally.")

    if terminal:
        backtest_backends.append("actual_mt5_strategy_tester")
    elif has_wine:
        backtest_backends.append("wine_strategy_tester_possible")
        limitations.append("Wine is available but MT5_TERMINAL64/MT5_TERMINAL_PATH is not configured.")
    else:
        limitations.append("No MT5 terminal backend detected; Strategy Tester evidence cannot be produced locally.")

    limitations.append("Imported reports are parse-only and are not release evidence without provenance manifest.")
    limitations.append("Internal AP/Trader/RRI checks are heuristics, not industry standards.")

    return CapabilityReport(
        schema_version="1.0",
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
