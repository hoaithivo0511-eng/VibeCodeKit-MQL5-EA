"""mql5-role-state -- unified role & sign-off state (single source of truth).

The canonical source of approval state is the JSON artifact
pair produced by the EA contract pipeline:

* ``owner-interview.json`` (mql5-owner-interview) -> ``owner.approved_to_build``
* ``owner-approval.json``  (mql5-owner-approve)   -> ``owner_approved`` + signer + date

The markdown sign-off lines audited by :mod:`rri.sign_off`
(``APPROVED by ...`` on the blueprint, ``CONFIRM by ...`` on the contract)
are treated as a *human-facing view* of the very same decision. When both
a JSON approval and a markdown sign-off line are present they MUST agree
on signer + date; a divergence is exactly the "two systems drift" smell
this workstream exists to kill, so it is reported as a mismatch and fails
``--check-consistency``.

This module is read-only: it never writes artifacts and never invents a
signature. ``mql5-doctor --check-signoff-consistency`` consumes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import sign_off as so
from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)

TOOL = "mql5-role-state"

DEFAULT_INTERVIEW_NAMES = (
    "owner-interview.json",
    "owner_interview.json",
    "interview.json",
)
DEFAULT_APPROVAL_NAMES = (
    "owner-approval.json",
    "owner_approval.json",
    "approval.json",
)


def _resolve(path: Path | None, candidates: tuple[str, ...], search_dirs: tuple[Path, ...]) -> Path | None:
    if path is not None and Path(path).is_file():
        return Path(path)
    for d in search_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for name in candidates:
            c = d / name
            if c.is_file():
                return c
    return None


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _search_dirs(state_dir: Path | None, search_root: Path | None) -> tuple[Path, ...]:
    dirs: list[Path] = []
    if state_dir is not None:
        dirs.append(Path(state_dir))
        dirs.append(Path(state_dir).parent)
    if search_root is not None:
        dirs.append(Path(search_root))
        dirs.append(Path(search_root) / "docs")
    dirs.append(Path("."))
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        k = str(d)
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return tuple(out)


def compute_state(
    *,
    interview_path: Path | None = None,
    approval_path: Path | None = None,
    blueprint_md: Path | None = None,
    contract_md: Path | None = None,
    state_dir: Path | None = None,
    search_root: Path | None = None,
    require_contract: bool = False,
) -> dict[str, Any]:
    """Compute the unified role / sign-off state. Canonical = JSON."""

    sdirs = _search_dirs(state_dir, search_root)
    interview_file = _resolve(interview_path, DEFAULT_INTERVIEW_NAMES, sdirs)
    approval_file = _resolve(approval_path, DEFAULT_APPROVAL_NAMES, sdirs)
    interview = _load_json(interview_file)
    approval = _load_json(approval_file)

    ok_md, md_audits = so.audit_sign_off(
        blueprint_path=Path(blueprint_md) if blueprint_md else None,
        contract_path=Path(contract_md) if contract_md else None,
        require_contract=require_contract,
        state_dir=Path(state_dir) if state_dir else None,
    )
    md = {a.artefact: a for a in md_audits}
    md_bp = md.get("blueprint")
    md_ct = md.get("contract")

    json_present = approval is not None
    json_signer = approval.get("owner_name") if approval else None
    json_at = approval.get("approved_at") if approval else None
    json_approved = bool(approval.get("owner_approved")) if approval else False
    json_bp_sha = approval.get("blueprint_sha256") if approval else None

    if json_present:
        canonical = "json"
    elif md_bp is not None and md_bp.found:
        canonical = "markdown"
    else:
        canonical = "none"

    blueprint = {
        "approved": json_approved if json_present else bool(md_bp and md_bp.found),
        "signer": json_signer if json_present else (md_bp.signer if md_bp else None),
        "signed_at": (json_at[:10] if (json_present and json_at) else (md_bp.signed_at if md_bp else None)),
        "source": "json" if json_present else ("markdown" if (md_bp and md_bp.found) else None),
        "json_blueprint_sha256": json_bp_sha,
    }
    contract = {
        "confirmed": json_approved if json_present else bool(md_ct and md_ct.found),
        "signer": json_signer if json_present else (md_ct.signer if md_ct else None),
        "signed_at": (json_at[:10] if (json_present and json_at) else (md_ct.signed_at if md_ct else None)),
        "source": "json" if json_present else ("markdown" if (md_ct and md_ct.found) else None),
    }

    mismatches: list[str] = []
    checked = False
    if json_present and md_bp is not None and md_bp.found:
        checked = True
        if (json_signer or "").strip().lower() != (md_bp.signer or "").strip().lower():
            mismatches.append(f"blueprint signer: json={json_signer!r} markdown={md_bp.signer!r}")
        if (json_at or "")[:10] != (md_bp.signed_at or ""):
            mismatches.append(f"blueprint date: json={(json_at or '')[:10]!r} markdown={md_bp.signed_at!r}")
        if json_approved is not True:
            mismatches.append("blueprint markdown APPROVED present but JSON owner_approved is not true")
    if json_present and md_ct is not None and md_ct.found:
        checked = True
        if (json_signer or "").strip().lower() != (md_ct.signer or "").strip().lower():
            mismatches.append(f"contract signer: json={json_signer!r} markdown={md_ct.signer!r}")
        if (json_at or "")[:10] != (md_ct.signed_at or ""):
            mismatches.append(f"contract date: json={(json_at or '')[:10]!r} markdown={md_ct.signed_at!r}")

    consistency = {"checked": checked, "ok": not mismatches, "mismatches": mismatches}

    return {
        "canonical": canonical,
        "interview_file": str(interview_file) if interview_file else None,
        "approval_file": str(approval_file) if approval_file else None,
        "interview_approved_to_build": (
            bool(interview.get("owner", {}).get("approved_to_build")) if interview else None
        ),
        "blueprint": blueprint,
        "contract": contract,
        "markdown": {
            "blueprint": (md_bp.to_dict() if md_bp else None),
            "contract": (md_ct.to_dict() if md_ct else None),
        },
        "consistency": consistency,
        "ok": consistency["ok"],
    }


def _render(state: dict[str, Any]) -> str:
    bp = state["blueprint"]
    ct = state["contract"]
    lines = [
        f"canonical source : {state['canonical']}",
        f"blueprint        : approved={bp['approved']} signer={bp['signer']} at={bp['signed_at']} (src={bp['source']})",
        f"contract         : confirmed={ct['confirmed']} signer={ct['signer']} at={ct['signed_at']} (src={ct['source']})",
        f"interview build  : approved_to_build={state['interview_approved_to_build']}",
    ]
    c = state["consistency"]
    if c["checked"] and c["ok"]:
        lines.append("consistency      : OK (markdown <-> json agree)")
    elif c["checked"]:
        lines.append("consistency      : MISMATCH")
        for m in c["mismatches"]:
            lines.append(f"  - {m}")
    else:
        lines.append("consistency      : not checked (only one system present)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Unified role & sign-off state (canonical=JSON).")
    ap.add_argument("--interview", type=Path, default=None)
    ap.add_argument("--approval", type=Path, default=None)
    ap.add_argument("--blueprint", type=Path, default=None, help="markdown blueprint (step-4-blueprint.md)")
    ap.add_argument("--contract", type=Path, default=None, help="markdown contract.md")
    ap.add_argument("--state-dir", type=Path, default=Path(".rri-state"))
    ap.add_argument("--search-root", type=Path, default=Path("."))
    ap.add_argument("--require-contract", action="store_true")
    ap.add_argument("--check-consistency", action="store_true",
                    help="Exit 1 when markdown and JSON sign-off disagree.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    state = compute_state(
        interview_path=args.interview,
        approval_path=args.approval,
        blueprint_md=args.blueprint,
        contract_md=args.contract,
        state_dir=args.state_dir,
        search_root=args.search_root,
        require_contract=args.require_contract,
    )
    ok = state["consistency"]["ok"]
    fail = bool(args.check_consistency and not ok)
    if not getattr(args, "emit_json", False):
        sys.stdout.write(_render(state))
    env = Envelope(
        tool=TOOL,
        ok=(not fail),
        exit_code=(1 if fail else 0),
        summary=("sign-off consistency " + ("ok" if ok else "MISMATCH") + f" (canonical={state['canonical']})"),
        data=state,
        evidence=[p for p in [state["approval_file"], state["interview_file"]] if p],
    )
    maybe_emit(args, env)
    return 1 if fail else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
