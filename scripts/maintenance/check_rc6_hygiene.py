#!/usr/bin/env python3
"""Fail-closed RC6 documentation, workflow and repository hygiene checks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
VERSION = "3.3.0rc6"

REQUIRED_PATHS = (
    ".github/workflows/release-gate.yml",
    ".github/workflows/rc6-native-evidence-verify.yml",
    ".github/workflows/rc6-package-integration.yml",
    ".github/workflows/rc6-prerelease-publish.yml",
    "docs/release/v3.3.0rc6/HARDENING-PLAN.md",
    "docs/release/v3.3.0rc6/DOCUMENTATION-AUDIT.md",
    "docs/release/v3.3.0rc6/REQUIREMENTS.csv",
    "docs/release/v3.3.0rc6/TEST-LEDGER.csv",
    "docs/release/v3.3.0rc6/TASK-11-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-12-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-13-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-14-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-15-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-16-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-17-COMPLETION.md",
    "docs/release/v3.3.0rc6/TASK-18-NATIVE-EVIDENCE-RUNBOOK.md",
    "docs/release/v3.3.0rc6/TASK-18-STATUS.md",
    "docs/release/v3.3.0rc6/TASK-19-DECISION.md",
    "docs/release/v3.3.0rc6/TASK-20-DOCUMENTATION-SYNC-COMPLETION.md",
    "docs/release/v3.3.0rc6/RC6-ARTIFACTS.sha256",
    "docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json",
    "docs/release/v3.3.0rc6/PRERELEASE-NOTES.md",
    "scripts/maintenance/build_rc6_candidate.py",
    "scripts/maintenance/check_rc6_hygiene.py",
    "scripts/maintenance/sync_distribution_snapshot.py",
    "scripts/maintenance/verify_rc6_native_evidence.py",
    "scripts/native/Invoke-RC6NativeEvidence.ps1",
)
EXECUTABLE_SCRIPTS = (
    "scripts/maintenance/build_rc6_candidate.py",
    "scripts/maintenance/check_rc6_hygiene.py",
    "scripts/maintenance/import-release-bundle.sh",
    "scripts/maintenance/repo_manifest.py",
    "scripts/maintenance/sync_distribution_snapshot.py",
    "scripts/maintenance/verify_rc6_native_evidence.py",
)
FORBIDDEN_SEGMENTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "htmlcov",
}
FORBIDDEN_BASENAMES = {".DS_Store", "Thumbs.db", ".coverage", ".env"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _project_scripts(pyproject: str) -> list[str]:
    """Read names from [project.scripts] without requiring TOML on Python 3.10."""

    scripts: list[str] = []
    in_section = False
    for raw in pyproject.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_section = line == "[project.scripts]"
            continue
        if in_section and line and not line.startswith("#") and "=" in line:
            scripts.append(line.split("=", 1)[0].strip())
    return scripts


def _missing_relative_doc_links(tracked: list[str]) -> list[str]:
    missing: list[str] = []
    for rel in tracked:
        path = ROOT / rel
        if path.suffix.lower() not in {".md", ".rst", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in MARKDOWN_LINK.finditer(text):
            ref = match.group(1).strip().split()[0].strip("<>")
            if not ref or ref.startswith(
                ("#", "http://", "https://", "mailto:", "data:", "javascript:")
            ):
                continue
            target = (path.parent / ref.split("#", 1)[0]).resolve()
            if not target.exists():
                missing.append(f"{rel} -> {ref}")
    return missing


def _tracked() -> list[str]:
    return subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()


def _git_modes() -> dict[str, str]:
    lines = subprocess.check_output(
        ["git", "ls-files", "-s"], cwd=ROOT, text=True
    ).splitlines()
    modes: dict[str, str] = {}
    for line in lines:
        metadata, path = line.split("\t", 1)
        modes[path] = metadata.split()[0]
    return modes


def evaluate() -> dict[str, object]:
    errors: list[str] = []
    tracked = _tracked()
    tracked_set = set(tracked)
    for rel in REQUIRED_PATHS:
        if rel not in tracked_set or not (ROOT / rel).is_file():
            errors.append(f"required RC6 path is missing or untracked: {rel}")

    for rel in tracked:
        path = PurePosixPath(rel)
        generated_coverage = path.name == "coverage.json" and path.parts[:1] != (
            "reports",
        )
        if (
            any(segment in FORBIDDEN_SEGMENTS for segment in path.parts)
            or path.name in FORBIDDEN_BASENAMES
            or generated_coverage
        ):
            errors.append(f"forbidden generated file is tracked: {rel}")

    modes = _git_modes()
    for rel in EXECUTABLE_SCRIPTS:
        if modes.get(rel) != "100755":
            errors.append(f"active maintenance script is not executable in Git: {rel}")

    pyproject = (ROOT / "tool/source/pyproject.toml").read_text(encoding="utf-8")
    catalog = json.loads(
        (ROOT / "tool/source/tool-catalog.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (ROOT / "tool/source/agent-contract.json").read_text(encoding="utf-8")
    )
    if f'version = "{VERSION}"' not in pyproject:
        errors.append("pyproject version is not RC6")
    if catalog.get("kit_version") != VERSION:
        errors.append("tool catalog version is not RC6")
    if contract.get("kit", {}).get("version") != VERSION:
        errors.append("agent contract version is not RC6")

    catalog_tools = catalog.get("tools", [])
    script_names = _project_scripts(pyproject)
    if len(catalog_tools) != 139 or len(script_names) != 139:
        errors.append(
            "RC6 command count drift: "
            f"catalog={len(catalog_tools)}, project.scripts={len(script_names)}, expected=139"
        )
    elif {item.get("name") for item in catalog_tools} != set(script_names):
        errors.append("tool catalog names do not match [project.scripts]")

    active_doc_contract = {
        "tool/source/README.md": ("v3.3.0 RC6", "EA-IR compiler"),
        "tool/source/docs/COMMANDS.md": (
            "Command catalog (139 commands)",
            "v3.3.0rc6 baseline contains 139 public entry",
        ),
        "tool/source/docs/USAGE-en.md": (
            "v3.3.0rc6 Usage Guide",
            "139-command RC6 catalog",
        ),
        "tool/source/docs/USER-GUIDE-en.md": (
            "current `v3.3.0rc6` baseline: **139 CLI entry points**",
            "selftest 13/13 invariants passed",
        ),
        "tool/source/docs/HUONG-DAN-TOAN-TAP-vi.md": (
            "kit_version: 3.3.0rc6",
            "139 console entry",
        ),
        "tool/source/docs/CODEX-SETUP-PROMPT.md": (
            "Setup & Build System Prompt (v3.3.0rc6)",
            "Require: 13/13 invariants passed.",
        ),
        "tool/source/docs/DOC-MAP.md": (
            "Documentation map — v3.3.0rc6",
            "Historical snapshots",
        ),
    }
    for rel, required_fragments in active_doc_contract.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for fragment in required_fragments:
            if fragment not in text:
                errors.append(f"active documentation contract drift: {rel}: {fragment}")

    missing_links = _missing_relative_doc_links(tracked)
    for finding in missing_links:
        errors.append(f"broken relative documentation link: {finding}")

    canonical_scaffolds = ROOT / "tool/source/scaffolds"
    packaged_scaffolds = (
        ROOT / "tool/source/scripts/vibecodekit_mql5/resources/scaffolds"
    )
    for packaged in packaged_scaffolds.rglob("*"):
        if not packaged.is_file():
            continue
        rel = packaged.relative_to(packaged_scaffolds)
        canonical = canonical_scaffolds / rel
        if not canonical.is_file() or canonical.read_bytes() != packaged.read_bytes():
            errors.append(f"packaged scaffold resource drift: {rel.as_posix()}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    structure = (ROOT / "STRUCTURE.md").read_text(encoding="utf-8")
    if "v3.3.0rc6" not in readme or "release_eligible=false" not in readme:
        errors.append("root README does not state RC6 and fail-closed release status")
    if "v3.3.0rc6" not in structure or "Task 18" not in structure:
        errors.append("STRUCTURE.md does not describe the RC6 native gate")

    for rel in (
        ".github/workflows/release-gate.yml",
        ".github/workflows/rc6-native-evidence-verify.yml",
        ".github/workflows/rc6-package-integration.yml",
        ".github/workflows/rc6-prerelease-publish.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "RC6" not in text:
            errors.append(f"active workflow is not labeled RC6: {rel}")
    return {
        "ok": not errors,
        "version": VERSION,
        "tracked_files": len(tracked),
        "required_paths": len(REQUIRED_PATHS),
        "command_count": len(catalog_tools),
        "documentation_links_checked": sum(
            1
            for rel in tracked
            if (ROOT / rel).suffix.lower() in {".md", ".rst", ".html"}
        ),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(
            f"RC6 repository hygiene: PASS "
            f"({result['tracked_files']} tracked files; {result['required_paths']} required paths)"
        )
    else:
        print("RC6 repository hygiene: FAIL")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
