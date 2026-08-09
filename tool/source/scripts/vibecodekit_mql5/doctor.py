"""/mql5-doctor — kit installation + environment health check.

Validates that everything the kit needs is reachable
on the current machine: Python toolchain, Wine when running MetaEditor
through Wine, ``MetaEditor.exe`` itself, the kit's package
importability, the presence of the 28+ reference docs, and that **every
scaffold archetype** under ``scaffolds/<preset>/<stack>/`` ships its
``EAName.mq5`` (auto-derived at run time so new archetypes are picked
up without code edits).

Exit code 0 = healthy.  Non-zero = at least one check failed.  The
JSON output enumerates every check so a CI workflow can decide which
to treat as fatal.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._resources import asset_root, kit_flavor

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_MODULES = [
    "vibecodekit_mql5.compile",
    "vibecodekit_mql5.lint",
    "vibecodekit_mql5.build",
    "vibecodekit_mql5.pip_normalize",
]

# Checks that depend on a working Wine + MetaEditor + terminal stack.
# In soft mode (``--soft``) these are surfaced as warnings instead of
# failures so docs-only / lint-only CI environments without Wine can still
# exit 0. Python toolchain, kit-package imports, references, and scaffolds
# remain hard checks under both modes.
_OPTIONAL_CHECKS: frozenset[str] = frozenset({
    "wine", "metaeditor-bin", "terminal-bin",
})

# Standard MetaTrader 5 binary locations Devin's setup-wine-metaeditor.sh leaves
# behind. Doctor uses these as a fallback when the corresponding env var is not
# set, so a fresh shell that hasn't sourced ~/.mql5-env still gets a green check.
_METAEDITOR_PROBES: tuple[str, ...] = (
    "$METAEDITOR_PATH",
    "$METAEDITOR64",
    "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
    "$HOME/.wine-mql5/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
)
_TERMINAL_PROBES: tuple[str, ...] = (
    "$MQL5_TERMINAL_PATH",
    "$MT5_TERMINAL_PATH",
    "$MT5_TERMINAL64",
    "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine-mql5/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe",
)


def _probe(paths: tuple[str, ...]) -> Path | None:
    """Return the first existing path after expanding env vars / ``~``.

    Empty / unset env vars (e.g. ``$METAEDITOR_PATH`` when never exported) are
    skipped so they don't show up in the report as a bogus failure detail.
    """
    for raw in paths:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if expanded == raw and raw.startswith("$"):
            continue  # env var unset
        p = Path(expanded)
        if p.is_file():
            return p
    return None

# Baseline list of scaffolds that MUST exist for the kit to be coherent.
# These are the original 11 archetypes shipped in early releases. They stay
# explicit here so removals of any of them is caught even if the
# ``scaffolds/`` directory listing accidentally regresses.
_BASELINE_SCAFFOLDS: tuple[str, ...] = (
    "stdlib/netting", "stdlib/hedging", "stdlib/python-bridge",
    "wizard-composable/netting", "portfolio-basket/netting",
    "portfolio-basket/hedging", "ml-onnx/python-bridge",
    "hft-async/netting",
    "service-llm-bridge/cloud-api",
    "service-llm-bridge/self-hosted-ollama",
    "service-llm-bridge/embedded-onnx-llm",
)


def discover_scaffolds(repo_root: Path | None = None) -> list[str]:
    """Return every ``<preset>/<stack>`` pair under ``scaffolds/``.

    Auto-derived from the filesystem so new archetypes are validated by
    doctor without requiring a code edit here. The baseline 11 from
    ``_BASELINE_SCAFFOLDS`` are union-merged in case the directory walk
    misses something (e.g. broken symlinks). The result is sorted for
    deterministic output.
    """
    found: set[str] = set(_BASELINE_SCAFFOLDS)
    # Scaffolds are packaged runtime assets; resolve wheel-safely via
    # asset_root. An explicit repo_root with a scaffolds/ dir still wins for
    # dev / source checkouts.
    scaffolds_root = asset_root("scaffolds")
    if repo_root is not None and (repo_root / "scaffolds").is_dir():
        scaffolds_root = repo_root / "scaffolds"
    if scaffolds_root.is_dir():
        for preset_dir in scaffolds_root.iterdir():
            if not preset_dir.is_dir():
                continue
            for stack_dir in preset_dir.iterdir():
                if not stack_dir.is_dir():
                    continue
                found.add(f"{preset_dir.name}/{stack_dir.name}")
    return sorted(found)


# Backwards-compat module-level constant. Older callers (tests, MCP) may
# still ``import REQUIRED_SCAFFOLDS``; keep it pointing at the discovered
# list so they automatically pick up newly added archetypes too.
REQUIRED_SCAFFOLDS: list[str] = discover_scaffolds()


@dataclass
class DoctorReport:
    checks: list[dict] = field(default_factory=list)
    ok: bool = True

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.ok = False

    def is_ok(self, *, soft: bool = False) -> bool:
        """Aggregate health across checks.

        In soft mode the Wine / MetaEditor / terminal checks no longer
        flip the report. Every other check still does. This lets
        docs-only or lint-only CI jobs that don't ship Wine pass the
        doctor gate without ignoring failures elsewhere.
        """
        if not soft:
            return self.ok
        for c in self.checks:
            if c["ok"]:
                continue
            if c["name"] not in _OPTIONAL_CHECKS:
                return False
        return True


def run_doctor(repo_root: Path = REPO_ROOT) -> DoctorReport:
    rep = DoctorReport()
    rep.add("python-version", sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}")

    metaeditor = _probe(_METAEDITOR_PROBES)
    needs_wine = not sys.platform.startswith("win") or (
        metaeditor is not None
        and ".wine" in metaeditor.as_posix().lower()
    )
    wine = shutil.which("wine")
    rep.add(
        "wine",
        wine is not None if needs_wine else True,
        str(wine) if wine else ("not required on Windows native" if not needs_wine else "PATH"),
    )
    rep.add(
        "metaeditor-bin",
        metaeditor is not None,
        str(metaeditor) if metaeditor else "not found in any of: "
        + ", ".join(_METAEDITOR_PROBES),
    )
    terminal = _probe(_TERMINAL_PROBES)
    rep.add(
        "terminal-bin",
        terminal is not None,
        str(terminal) if terminal else "not found in any of: "
        + ", ".join(_TERMINAL_PROBES),
    )
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            rep.add(f"import:{mod}", True)
        except ImportError as exc:
            rep.add(f"import:{mod}", False, str(exc))
    flavor = kit_flavor()
    rep.add("flavor", True, flavor)
    if flavor == "full":
        refs_dir = repo_root / "docs" / "references"
        rep.add("references-dir", refs_dir.exists(), str(refs_dir))
        if refs_dir.exists():
            n = len(list(refs_dir.glob("*.md")))
            rep.add("references-count", n >= 28, f"{n} refs")
    else:
        rep.add("references", True,
                "skipped (slim flavor — docs repo not shipped)")
    # Scaffolds ship as packaged assets; check them wheel-safely.
    scaffolds_root = asset_root("scaffolds")
    if (repo_root / "scaffolds").is_dir():
        scaffolds_root = repo_root / "scaffolds"
    for scaffold in discover_scaffolds(repo_root):
        p = scaffolds_root / scaffold / "EAName.mq5"
        rep.add(f"scaffold:{scaffold}", p.exists(), str(p))
    return rep


_ARCHAEOLOGY_TOKENS = (
    re.compile(r"Wave[\s-]?\d"),
    re.compile(r"Plan v[0-9]"),
    re.compile(r"vibecodekit-mql5-ea-25\." + "5"),
)
_SCAN_SUFFIXES = {".py", ".md", ".toml", ".json"}


def check_version(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str]]:
    """Verify a single source of truth for the version + no archaeology.

    Returns ``(ok, problems)``. Checks:
      * pyproject ``[project].version`` == ``_version.get_version()``
      * no stray ``VERSION`` file (would be a competing source)
      * tool-catalog.json ``kit_version`` (if present) matches
      * no Wave / Plan / pinned-repo archaeology tokens in shipped files
    """
    from . import _version

    canonical = _version.get_version()
    problems: list[str] = []

    pp = repo_root / "pyproject.toml"
    if pp.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pp.read_text(encoding="utf-8"), re.M)
        if not m:
            problems.append("pyproject.toml: no [project].version found")
        elif m.group(1) != canonical:
            problems.append(f"pyproject version {m.group(1)} != canonical {canonical}")

    if (repo_root / "VERSION").exists():
        problems.append("stray VERSION file present (competing source of truth)")

    mf = repo_root / "tool-catalog.json"
    if mf.exists():
        import json
        try:
            kv = json.loads(mf.read_text(encoding="utf-8")).get("kit_version")
            if kv and kv != canonical:
                problems.append(f"tool-catalog.json kit_version {kv} != canonical {canonical}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"tool-catalog.json unreadable: {exc}")

    skip = {".git", "node_modules", "__pycache__", "evidence"}
    for path in repo_root.rglob("*"):
        if path.suffix not in _SCAN_SUFFIXES or not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(repo_root).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for rx in _ARCHAEOLOGY_TOKENS:
            if rx.search(text):
                rel = path.relative_to(repo_root)
                problems.append(f"{rel}: archaeology token /{rx.pattern}/")
                break
    return (not problems, problems)



def check_signoff_consistency(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str]]:
    """Markdown sign-off must agree with the canonical JSON approval.

    Delegates to :mod:`rri.role_state`. Returns ``(ok, problems)``. When
    only one of the two systems (markdown / JSON) is present there is
    nothing to contradict, so it passes.
    """
    from .rri import role_state as rs
    state = rs.compute_state(
        state_dir=repo_root / ".rri-state",
        search_root=repo_root,
    )
    cons = state["consistency"]
    if not cons["checked"]:
        return True, []
    return cons["ok"], list(cons["mismatches"])


def check_role_consistency(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str]]:
    """Escalation audit log integrity (valid actors / levels / ids).

    Returns ``(ok, problems)``. A missing log is fine (nothing escalated
    yet). Each record must reference known actors and levels, carry a
    unique id, and -- when RESOLVED -- name a resolver.
    """
    from .rri import escalation as esc
    problems: list[str] = []
    log = repo_root / esc.DEFAULT_LOG
    if not log.exists():
        return True, []
    try:
        records = esc.load_log(log)
    except (ValueError, OSError, KeyError) as exc:
        return False, [f"escalation log unreadable/corrupt: {exc}"]
    seen: set[str] = set()
    for r in records:
        rid = getattr(r, "id", None) or getattr(r, "escalation_id", "?")
        frm = getattr(r, "from_actor", None)
        to = getattr(r, "to_actor", None)
        lvl = getattr(r, "level", None)
        status = getattr(r, "status", None)
        resolved_by = getattr(r, "resolved_by", None)
        if frm is not None and frm not in esc.ACTORS:
            problems.append(f"{rid}: unknown from_actor {frm!r}")
        if to is not None and to not in esc.ACTORS:
            problems.append(f"{rid}: unknown to_actor {to!r}")
        if lvl is not None and lvl not in esc.LEVELS:
            problems.append(f"{rid}: invalid level {lvl!r}")
        if rid in seen:
            problems.append(f"{rid}: duplicate escalation id")
        seen.add(rid)
        if status == "RESOLVED" and not resolved_by:
            problems.append(f"{rid}: RESOLVED but no resolver recorded")
    return (not problems), problems


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    parser = argparse.ArgumentParser(prog="mql5-doctor")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--check-version",
        action="store_true",
        help=(
            "Only verify the single source of truth for the version and that "
            "no Wave / Plan / pinned-repo archaeology tokens remain in shipped files. "
            "Exit 0 when consistent, 1 otherwise."
        ),
    )
    parser.add_argument(
        "--check-signoff-consistency",
        action="store_true",
        help=(
            "Only verify that markdown sign-off lines agree with the "
            "canonical JSON approval (rri.role_state). Exit 0 when "
            "consistent or only one system present, 1 on mismatch."
        ),
    )
    parser.add_argument(
        "--check-role-consistency",
        action="store_true",
        help=(
            "Only verify escalation audit-log integrity (known actors / "
            "levels, unique ids, resolved entries name a resolver). "
            "Exit 0 when clean, 1 otherwise."
        ),
    )
    parser.add_argument(
        "--soft",
        action="store_true",
        help=(
            "Treat Wine / MetaEditor / terminal probes as warnings instead "
            "of failures. Exit 0 when only those optional checks fail. "
            "Useful for docs-only or lint-only CI environments."
        ),
    )
    parser.add_argument(
        "--check-io-contract",
        action="store_true",
        help=(
            "Only verify the stdout/stderr I/O contract: no diagnostic "
            "line (error/warning/unknown/...) may be printed to stdout, "
            "which is reserved for a tool's machine payload. Exit 0 when "
            "clean, 1 on any violation."
        ),
    )
    _agent_io.add_json_flag(parser)
    _agent_io.add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if args.check_io_contract:
        from . import io_contract
        violations = io_contract.scan_package()
        for v in violations:
            print(f"io-contract:error: {v.format()}", file=sys.stderr)
        print(
            f"mql5-doctor --check-io-contract: "
            f"{'PASS' if not violations else 'FAIL'} "
            f"({len(violations)} violation(s))"
        )
        if args.emit_json:
            envelope = _agent_io.Envelope(
                tool="mql5-doctor",
                ok=not violations,
                exit_code=0 if not violations else 1,
                summary=(
                    f"io-contract {'clean' if not violations else 'FAIL'}: "
                    f"{len(violations)} diagnostic-on-stdout violation(s)"
                ),
                data={"violations": [v.format() for v in violations]},
            )
            _agent_io.emit(envelope)
        return 0 if not violations else 1

    if args.check_version:
        from . import _version
        ok, problems = check_version(Path(args.repo_root))
        for prob in problems:
            print(f"version:error: {prob}", file=sys.stderr)
        print(
            f"mql5-doctor --check-version: {'PASS' if ok else 'FAIL'} "
            f"(canonical {_version.get_version()}, {len(problems)} problem(s))"
        )
        return 0 if ok else 1

    if args.check_signoff_consistency:
        ok, problems = check_signoff_consistency(Path(args.repo_root))
        for prob in problems:
            print(f"signoff:error: {prob}", file=sys.stderr)
        print(
            f"mql5-doctor --check-signoff-consistency: "
            f"{'PASS' if ok else 'FAIL'} ({len(problems)} problem(s))"
        )
        return 0 if ok else 1

    if args.check_role_consistency:
        ok, problems = check_role_consistency(Path(args.repo_root))
        for prob in problems:
            print(f"role:error: {prob}", file=sys.stderr)
        print(
            f"mql5-doctor --check-role-consistency: "
            f"{'PASS' if ok else 'FAIL'} ({len(problems)} problem(s))"
        )
        return 0 if ok else 1

    rep = run_doctor(Path(args.repo_root))
    ok = rep.is_ok(soft=args.soft)
    payload: dict[str, object] = {"ok": ok, "checks": rep.checks}
    if args.soft:
        payload["soft"] = True
        payload["strict_ok"] = rep.ok

    envelope = _agent_io.Envelope(
        tool="mql5-doctor",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=(f"doctor: {len(rep.checks)} checks, "
                 f"{'PASS' if ok else 'FAIL'}"
                 + (" (soft)" if args.soft else "")),
        data=payload,
        evidence=[str(args.repo_root)],
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(payload, indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
