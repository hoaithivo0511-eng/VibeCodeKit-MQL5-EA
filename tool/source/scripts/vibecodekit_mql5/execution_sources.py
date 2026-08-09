"""Execution source classification for compile/backtest evidence.

This module intentionally distinguishes real execution from imported, fixture,
or stub outputs. Only actual MetaEditor/MT5 execution may become release evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Any

CompileSource = Literal[
    "actual_metaeditor",
    "wine_metaeditor",
    "remote_worker_metaeditor",
    "imported_log",
    "stub",
    "unknown",
]
BacktestSource = Literal[
    "actual_mt5_strategy_tester",
    "remote_worker_strategy_tester",
    "imported_report",
    "sample_fixture",
    "manual_unverified",
    "unknown",
]

FIXTURE_DIR_NAMES = {"tests", "fixtures", "examples", "samples", "docs"}


def is_fixture_path(path: str | Path) -> bool:
    parts = [p.lower() for p in Path(path).parts]
    return any(p in FIXTURE_DIR_NAMES for p in parts)


@dataclass(frozen=True)
class SourceAssessment:
    kind: str
    source: str
    trusted_for_release: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_compile_source(source: str | None) -> SourceAssessment:
    src = (source or "unknown").strip().lower()
    # Wine is a useful development/CI backend, but it is not release
    # authority unless a separately attested Windows-native/remote run exists.
    # Keeping it untrusted here prevents a local compatibility run from being
    # misrepresented as production compile evidence.
    trusted = src in {"actual_metaeditor", "remote_worker_metaeditor"}
    if src == "stub":
        return SourceAssessment("compile", src, False, "Stub output is not compile evidence.")
    if src == "imported_log":
        return SourceAssessment("compile", src, False, "Imported compile logs do not prove execution provenance.")
    if src == "unknown":
        return SourceAssessment("compile", src, False, "Compile source is unknown.")
    if src == "wine_metaeditor":
        return SourceAssessment("compile", src, False, "Wine compile is development/CI evidence, not release authority.")
    if trusted:
        return SourceAssessment("compile", src, True, "Compile was produced by a trusted MetaEditor execution backend.")
    return SourceAssessment("compile", src, False, "Unrecognized compile source is not trusted for release.")


def assess_backtest_source(source: str | None, report_path: str | Path | None = None) -> SourceAssessment:
    if report_path is not None and is_fixture_path(report_path):
        return SourceAssessment("backtest", "sample_fixture", False, "Report path is inside fixture/sample/docs/example area.")
    src = (source or "unknown").strip().lower()
    trusted = src in {"actual_mt5_strategy_tester", "remote_worker_strategy_tester"}
    if src == "imported_report":
        return SourceAssessment("backtest", src, False, "Imported reports can be parsed but cannot prove execution provenance.")
    if src == "manual_unverified":
        return SourceAssessment("backtest", src, False, "Manual/unverified report is not trusted for release.")
    if src == "sample_fixture":
        return SourceAssessment("backtest", src, False, "Sample fixture is not release evidence.")
    if src == "unknown":
        return SourceAssessment("backtest", src, False, "Backtest source is unknown.")
    if trusted:
        return SourceAssessment("backtest", src, True, "Backtest was produced by MT5 Strategy Tester execution backend.")
    return SourceAssessment("backtest", src, False, "Unrecognized backtest source is not trusted for release.")
