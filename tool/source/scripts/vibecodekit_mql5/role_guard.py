"""mql5-role-guard -- enforce role ownership + blueprint sign-off.

The v2.x review noted the three-role model (Homeowner / Contractor /
Builder) was philosophy-only: nothing actually *stopped* EA source from
being changed before the Homeowner approved the blueprint. This guard
closes that hole. Given a set of changed files, it:

1. Attributes each file to an owning role via ``ownership.yaml``.
2. For files whose rule sets ``requires_approval: true`` (EA sources),
   it refuses the change unless the canonical role-state reports the
   blueprint as APPROVED.

It is git-independent: pass ``--files`` explicitly, or ``--staged`` to
read ``git diff --cached`` when a repo is present. ``--emit-hook`` /
``--install-hook`` wire it into a pre-commit hook (optional).
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from .rri import role_state

TOOL = "mql5-role-guard"
DEFAULT_OWNERSHIP_NAMES = ("ownership.yaml", "ownership.yml")
VALID_OWNERS = {"chu-nha", "chu-thau", "tho-thi-cong"}


@dataclass(frozen=True)
class Rule:
    path: str
    owner: str
    requires_approval: bool


def _resolve_ownership(repo_root: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    for name in DEFAULT_OWNERSHIP_NAMES:
        cand = repo_root / name
        if cand.is_file():
            return cand
    return None


def load_rules(path: Path) -> tuple[list[Rule], str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default_owner = str(raw.get("default_owner", "chu-thau"))
    rules: list[Rule] = []
    for item in raw.get("rules", []) or []:
        rules.append(Rule(
            path=str(item["path"]),
            owner=str(item.get("owner", default_owner)),
            requires_approval=bool(item.get("requires_approval", False)),
        ))
    return rules, default_owner


def match_glob(rel_path: str, pattern: str) -> bool:
    """Glob match tolerant of leading ``**/`` and bare basename patterns."""
    rel = rel_path.replace("\\", "/")
    if fnmatch.fnmatch(rel, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:]):
        return True
    if "/" not in pattern and fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pattern):
        return True
    return False


def attribute(rel_path: str, rules: list[Rule], default_owner: str) -> Rule:
    for rule in rules:
        if match_glob(rel_path, rule.path):
            return rule
    return Rule(path="<default>", owner=default_owner, requires_approval=False)


def blueprint_approved(repo_root: Path) -> tuple[bool, dict]:
    """Best-effort canonical blueprint approval state."""
    try:
        st = role_state.compute_state(search_root=repo_root, require_contract=False)
        return bool(st.get("blueprint", {}).get("approved")), st.get("blueprint", {})
    except (OSError, ValueError, KeyError):
        return False, {}


def _git_staged(repo_root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True, timeout=15,
        )
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


def check_files(
    files: list[str], rules: list[Rule], default_owner: str, *, approved: bool,
) -> tuple[bool, list[dict]]:
    """Return (ok, findings). A finding with blocking=True fails the guard."""
    findings: list[dict] = []
    ok = True
    for f in files:
        rule = attribute(f, rules, default_owner)
        blocking = bool(rule.requires_approval and not approved)
        if blocking:
            ok = False
        findings.append({
            "file": f,
            "owner": rule.owner,
            "requires_approval": rule.requires_approval,
            "blocking": blocking,
            "reason": ("EA artefact changed before blueprint APPROVED" if blocking
                       else "ok"),
        })
    return ok, findings


HOOK_SCRIPT = """#!/usr/bin/env bash
# Installed by `mql5-role-guard --install-hook`.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
export PYTHONPATH="$ROOT/scripts:$ROOT"
python3 -m vibecodekit_mql5.role_guard --staged --repo-root "$ROOT"
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Enforce role ownership + blueprint sign-off.")
    ap.add_argument("--files", nargs="*", default=None, help="Explicit changed-file list.")
    ap.add_argument("--staged", action="store_true", help="Use git staged files.")
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--ownership", type=Path, default=None, help="Path to ownership.yaml.")
    ap.add_argument("--assume-approved", dest="assume_approved", action="store_true",
                    help="Override: treat blueprint as APPROVED (testing/escape hatch).")
    ap.add_argument("--emit-hook", action="store_true", help="Print the pre-commit hook script.")
    ap.add_argument("--install-hook", type=Path, nargs="?", const=Path(".git/hooks/pre-commit"),
                    default=None, help="Write the pre-commit hook (default .git/hooks/pre-commit).")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.emit_hook:
        sys.stdout.write(HOOK_SCRIPT)
        return 0
    if args.install_hook is not None:
        args.install_hook.parent.mkdir(parents=True, exist_ok=True)
        args.install_hook.write_text(HOOK_SCRIPT, encoding="utf-8")
        args.install_hook.chmod(0o755)
        if not args.emit_json:
            sys.stderr.write(f"installed hook -> {args.install_hook}\n")
        return 0

    repo_root = args.repo_root
    own_path = _resolve_ownership(repo_root, args.ownership)
    if own_path is None:
        sys.stderr.write(f"error: ownership.yaml not found under {repo_root}\n")
        return 2
    rules, default_owner = load_rules(own_path)

    if args.files is not None:
        files = list(args.files)
    elif args.staged:
        files = _git_staged(repo_root)
    else:
        sys.stderr.write("error: provide --files or --staged\n")
        return 2

    approved, bp = (True, {"source": "override"}) if args.assume_approved else blueprint_approved(repo_root)
    ok, findings = check_files(files, rules, default_owner, approved=approved)
    blocking = [f for f in findings if f["blocking"]]

    if not args.emit_json:
        for f in findings:
            mark = "BLOCK" if f["blocking"] else "ok"
            sys.stdout.write(f"[{mark}] {f['file']}  owner={f['owner']}  {f['reason']}\n")
        if blocking:
            sys.stderr.write(
                f"\nrole-guard: {len(blocking)} EA artefact(s) changed before blueprint "
                f"APPROVED (blueprint.approved={approved}). Get Homeowner sign-off first.\n")

    env = Envelope(
        tool=TOOL,
        ok=ok,
        exit_code=0 if ok else 1,
        summary=(f"{len(files)} file(s); {len(blocking)} blocking; "
                 f"blueprint.approved={approved}"),
        data={"approved": approved, "blueprint": bp, "findings": findings,
              "ownership": str(own_path)},
    )
    maybe_emit(args, env)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
