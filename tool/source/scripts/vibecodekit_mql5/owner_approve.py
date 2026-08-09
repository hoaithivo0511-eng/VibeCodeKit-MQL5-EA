"""Owner approval artifact.

Approves a specific interview + blueprint + tip set by hashing all artifacts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .contract_utils import read_json, write_json, validation_report, now_iso, sha256_file


def make_approval(interview: str | Path, blueprint: str | Path, tip: str | Path, owner_name: str, force_draft_approval: bool = False) -> dict[str, Any]:
    tip_data = read_json(tip)
    interview_data = read_json(interview)
    owner_interview_approved = bool(interview_data.get('owner', {}).get('approved_to_build'))
    return {
        "schema_version": "1.0",
        "artifact_type": "owner_approval",
        "approved_at": now_iso(),
        "owner_name": owner_name,
        "owner_approved": bool(owner_interview_approved or force_draft_approval),
        "owner_interview_approved": owner_interview_approved,
        "force_draft_approval": bool(force_draft_approval),
        "interview": str(interview),
        "interview_sha256": sha256_file(interview),
        "blueprint": str(blueprint),
        "blueprint_sha256": sha256_file(blueprint),
        "blueprint_tip": str(tip),
        "blueprint_tip_sha256": sha256_file(tip),
        "tip_ok": bool(tip_data.get("ok")),
        "critical_count": int(tip_data.get("critical_count", 0)),
    }


def validate_approval(data: dict[str, Any]) -> dict[str, Any]:
    missing = []
    for k in ["owner_name", "interview", "interview_sha256", "blueprint", "blueprint_sha256", "blueprint_tip", "blueprint_tip_sha256"]:
        if not data.get(k):
            missing.append(k)
    if data.get("owner_approved") is not True:
        missing.append("owner_approved")
    if data.get("tip_ok") is not True or data.get("critical_count", 1) != 0:
        missing.append("blueprint_tip.ok")
    # Re-hash files when present
    for field in ["interview", "blueprint", "blueprint_tip"]:
        p = data.get(field)
        h = data.get(field + "_sha256")
        if p and Path(p).is_file() and h and sha256_file(p) != h:
            missing.append(field + "_sha256_mismatch")
    return validation_report(not missing, missing, [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create or validate owner approval artifact.")
    ap.add_argument("--interview", required=True)
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--tip", required=True)
    ap.add_argument("--owner-name", default="Owner")
    ap.add_argument("--out", required=True)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--force-draft-approval", action="store_true", help="Allow approval artifact for draft builds even if interview owner.approved_to_build is false")
    args = ap.parse_args(argv)

    if args.validate:
        data = read_json(args.out)
    else:
        data = make_approval(args.interview, args.blueprint, args.tip, args.owner_name, args.force_draft_approval)
        write_json(args.out, data)
    report = validate_approval(data)
    report["artifact"] = args.out
    print(__import__("json").dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
