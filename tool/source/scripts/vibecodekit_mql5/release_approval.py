"""Approval bound to exact build and evidence hashes for forward/live targets."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVAL_NAME = "OWNER_APPROVAL.json"
LIVE_IDENTITY = {"authenticated-session", "cryptographic"}
FORWARD_IDENTITY = LIVE_IDENTITY | {"local-explicit"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ApprovalResult:
    ok: bool
    status: str
    errors: list[str] = field(default_factory=list)
    approval: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "errors": self.errors,
                "approval": self.approval}


def make_approval(*, owner_id: str, target: str, build: Path, evidence: Path,
                  environment: str, identity_assurance: str,
                  identity_assertion: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "approved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner_id": owner_id,
        "target": target,
        "risk_acknowledged": True,
        "environment_authority": environment,
        "identity_assurance": identity_assurance,
        "identity_assertion": identity_assertion,
        "build": str(build),
        "build_sha256": _sha256(build),
        "evidence_manifest": str(evidence),
        "evidence_manifest_sha256": _sha256(evidence),
        "notice": "Eligibility approval is not a profitability or safety guarantee.",
    }


def validate(project_dir: Path | str, target: str) -> ApprovalResult:
    project_dir = Path(project_dir)
    path = project_dir / APPROVAL_NAME
    if target not in {"forward", "live"}:
        return ApprovalResult(True, "NOT_REQUIRED")
    if not path.is_file():
        return ApprovalResult(False, "UNTESTABLE", [f"missing {APPROVAL_NAME}"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ApprovalResult(False, "FAIL", [f"invalid approval JSON: {exc}"])
    errors: list[str] = []
    if data.get("target") != target:
        errors.append(f"approval target {data.get('target')!r} does not match {target!r}")
    if not data.get("owner_id") or data.get("risk_acknowledged") is not True:
        errors.append("owner_id and risk acknowledgement are required")
    assurance = data.get("identity_assurance")
    allowed = LIVE_IDENTITY if target == "live" else FORWARD_IDENTITY
    if assurance not in allowed:
        errors.append(f"identity assurance {assurance!r} is insufficient for {target}")
    if assurance in LIVE_IDENTITY and not data.get("identity_assertion"):
        errors.append("authenticated/cryptographic approval needs an identity assertion")
    if target == "live" and data.get("environment_authority") != "windows-native":
        errors.append("live approval requires windows-native release authority")
    for path_key, hash_key in (
        ("build", "build_sha256"),
        ("evidence_manifest", "evidence_manifest_sha256"),
    ):
        raw = data.get(path_key)
        artifact = Path(raw) if isinstance(raw, str) else Path("__missing__")
        if not artifact.is_absolute():
            artifact = project_dir / artifact
        if not artifact.is_file():
            errors.append(f"missing approval artifact: {raw}")
        elif _sha256(artifact) != data.get(hash_key):
            errors.append(f"approval hash mismatch: {raw}")
    return ApprovalResult(not errors, "PASS" if not errors else "FAIL", errors, data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-release-approve")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--owner-id", required=True)
    ap.add_argument("--target", choices=("forward", "live"), required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--environment", choices=("windows-native", "wine-development"),
                    required=True)
    ap.add_argument("--identity-assurance", choices=tuple(sorted(FORWARD_IDENTITY)),
                    default="local-explicit")
    ap.add_argument("--identity-assertion")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args(argv)
    out = args.project_dir / APPROVAL_NAME
    if not args.validate:
        approval = make_approval(
            owner_id=args.owner_id, target=args.target, build=args.build,
            evidence=args.evidence, environment=args.environment,
            identity_assurance=args.identity_assurance,
            identity_assertion=args.identity_assertion,
        )
        out.write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    result = validate(args.project_dir, args.target)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
