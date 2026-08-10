#!/usr/bin/env python3
"""Build and verify the self-contained v3.3.0rc5 SHIP bundle.

SHIP means the tool/package is materially complete and installable. It does
NOT mean native MetaEditor/MT5 validation has passed. The bundle intentionally
ships with ``release_eligible=false`` and PENDING native evidence templates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION = "3.3.0rc5"
RELEASE_DIR = ROOT / "docs/release/v3.3.0rc5"
CANDIDATE_MANIFEST = RELEASE_DIR / "RC5-CANDIDATE-MANIFEST.json"
CANDIDATE_SUMS = RELEASE_DIR / "RC5-ARTIFACTS.sha256"
SHIP_ZIP = ROOT / "VibeCodeKit-MQL5-v3.3.0rc5-SHIP.zip"
SHIP_MANIFEST = RELEASE_DIR / "RC5-SHIP-MANIFEST.json"
SHIP_SUMS = RELEASE_DIR / "RC5-SHIP.sha256"
SHIP_COMPLETION = RELEASE_DIR / "SHIP-COMPLETION.md"
TEMPLATE_DIR = RELEASE_DIR / "native-evidence/templates"
CONTENTS_MEMBER = "SHIP-CONTENTS.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

BASE_PAYLOAD = (
    "RELEASE-TRUST.yaml",
    "tool/vibecodekit-mql5-v3.3.0rc5-source-full.zip",
    "tool/vibecodekit-mql5-v3.3.0rc5-source-full.manifest.json",
    "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl",
    "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip",
    "docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json",
    "docs/release/v3.3.0rc5/RC5-ARTIFACTS.sha256",
    "docs/release/v3.3.0rc5/PR-09-COMPLETION.md",
    "docs/release/v3.3.0rc5/PR-10-STATUS.md",
    "docs/release/v3.3.0rc5/TASK-10-NATIVE-EVIDENCE-RUNBOOK.md",
    "docs/release/v3.3.0rc5/SHIP-README.md",
    "docs/release/v3.3.0rc5/native-evidence/templates/restart-recovery.template.json",
    "docs/release/v3.3.0rc5/native-evidence/templates/deep-review.template.json",
    "scripts/native/Invoke-RC5NativeEvidence.ps1",
    "scripts/maintenance/verify_rc5_native_evidence.py",
)
REQUIRED_RESTART_CASES = (
    "abrupt_terminal_kill",
    "restart_reconcile",
    "no_duplicate_order",
    "legacy_v1_migration_restart",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_candidate() -> dict[str, Any]:
    data = json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    if data.get("kit_version") != VERSION:
        raise SystemExit("candidate kit_version mismatch")
    if data.get("release_eligible") is not False:
        raise SystemExit("SHIP must be cut from a native-pending candidate with release_eligible=false")
    tree = str(data.get("source_tree_sha") or "").strip()
    if not tree:
        raise SystemExit("candidate source_tree_sha missing")
    return data


def tracked_source_members() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z", "tool/source"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    items = [p.decode("utf-8") for p in proc.stdout.split(b"\0") if p]
    if not items:
        raise SystemExit("tracked tool/source tree is empty")
    return sorted(items)


def payload_members() -> list[str]:
    return sorted(set(BASE_PAYLOAD) | set(tracked_source_members()))


def write_templates(candidate: dict[str, Any]) -> None:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    tree = str(candidate["source_tree_sha"])
    restart = {
        "schema_version": "1.0",
        "status": "PENDING",
        "source": "actual_mt5_restart_recovery",
        "candidate_source_tree_sha": tree,
        "restart_recovery_cases": [
            {"id": case_id, "status": "PENDING", "evidence": ""}
            for case_id in REQUIRED_RESTART_CASES
        ],
    }
    review = {
        "schema_version": "1.0",
        "status": "PENDING",
        "candidate_source_tree_sha": tree,
        "reviewer": "",
        "reviewed_at_utc": "",
        "release_blockers": ["Complete native-candidate deep review before release certification"],
        "findings": [],
    }
    (TEMPLATE_DIR / "restart-recovery.template.json").write_text(
        json.dumps(restart, indent=2) + "\n", encoding="utf-8"
    )
    (TEMPLATE_DIR / "deep-review.template.json").write_text(
        json.dumps(review, indent=2) + "\n", encoding="utf-8"
    )


def member_record(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    if not path.is_file():
        raise SystemExit(f"SHIP payload missing: {rel}")
    return {"path": rel, "size": path.stat().st_size, "sha256": sha256_file(path)}


def contents_document(candidate: dict[str, Any], members: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "rc5-ship-contents",
        "kit_version": VERSION,
        "ship_ready": True,
        "native_validation_status": "PENDING",
        "release_eligible": False,
        "candidate_source_tree_sha": candidate["source_tree_sha"],
        "candidate_build_input_commit": candidate.get("build_input_commit", ""),
        "members": [member_record(rel) for rel in members],
    }


def zip_write_bytes(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    zf.writestr(info, data)


def build(run_id: str = "") -> None:
    candidate = load_candidate()
    write_templates(candidate)
    members = payload_members()
    contents = contents_document(candidate, members)
    contents_bytes = (json.dumps(contents, indent=2, sort_keys=True) + "\n").encode("utf-8")

    if SHIP_ZIP.exists():
        SHIP_ZIP.unlink()
    with zipfile.ZipFile(SHIP_ZIP, "w") as zf:
        for rel in members:
            zip_write_bytes(zf, rel, (ROOT / rel).read_bytes())
        zip_write_bytes(zf, CONTENTS_MEMBER, contents_bytes)

    outer = {
        "schema_version": "1.0",
        "kind": "rc5-ship",
        "kit_version": VERSION,
        "ship_ready": True,
        "native_validation_status": "PENDING",
        "release_eligible": False,
        "release_blockers": [
            "Trusted native MetaEditor compile evidence pending",
            "Trusted native MT5 Strategy Tester evidence pending",
            "Crash/restart recovery evidence pending",
            "Native deep-review evidence pending",
        ],
        "candidate_source_tree_sha": candidate["source_tree_sha"],
        "candidate_build_input_commit": candidate.get("build_input_commit", ""),
        "bundle": {
            "path": SHIP_ZIP.relative_to(ROOT).as_posix(),
            "size": SHIP_ZIP.stat().st_size,
            "sha256": sha256_file(SHIP_ZIP),
        },
        "contents_manifest_sha256": sha256_bytes(contents_bytes),
        "payload_member_count": len(members),
    }
    SHIP_MANIFEST.write_text(json.dumps(outer, indent=2) + "\n", encoding="utf-8")
    SHIP_SUMS.write_text(
        f"{sha256_file(SHIP_ZIP)}  {SHIP_ZIP.relative_to(ROOT).as_posix()}\n"
        f"{sha256_file(SHIP_MANIFEST)}  {SHIP_MANIFEST.relative_to(ROOT).as_posix()}\n",
        encoding="utf-8",
    )
    SHIP_COMPLETION.write_text(
        "# RC5 SHIP Completion\n\n"
        "Status: `SHIP-READY / NATIVE-VALIDATION-PENDING`\n\n"
        f"- Kit: `{VERSION}`\n"
        f"- Candidate source tree: `{candidate['source_tree_sha']}`\n"
        f"- Candidate build input: `{candidate.get('build_input_commit', '')}`\n"
        f"- SHIP bundle SHA-256: `{outer['bundle']['sha256']}`\n"
        f"- Payload members: `{len(members)}` plus `{CONTENTS_MEMBER}`\n"
        f"- Package integration workflow run: `{run_id or 'not-recorded'}`\n"
        "- `ship_ready`: `true`\n"
        "- `native_validation_status`: `PENDING`\n"
        "- `release_eligible`: `false`\n\n"
        "The tool/package is complete and materialized for installation and later native validation. "
        "MetaEditor/MT5 certification is deliberately deferred and cannot be inferred from SHIP readiness.\n",
        encoding="utf-8",
    )


def verify() -> None:
    candidate = load_candidate()
    if not SHIP_ZIP.is_file() or not SHIP_MANIFEST.is_file() or not SHIP_SUMS.is_file():
        raise SystemExit("SHIP artifacts are incomplete")
    manifest = json.loads(SHIP_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("ship_ready") is not True:
        raise SystemExit("SHIP manifest ship_ready is not true")
    if manifest.get("native_validation_status") != "PENDING":
        raise SystemExit("SHIP manifest must remain native PENDING before owner validation")
    if manifest.get("release_eligible") is not False:
        raise SystemExit("SHIP manifest must remain release_eligible=false")
    if manifest.get("candidate_source_tree_sha") != candidate.get("source_tree_sha"):
        raise SystemExit("SHIP/candidate source tree mismatch")
    bundle = manifest.get("bundle") or {}
    if bundle.get("sha256") != sha256_file(SHIP_ZIP) or bundle.get("size") != SHIP_ZIP.stat().st_size:
        raise SystemExit("SHIP bundle size/hash mismatch")

    expected = payload_members()
    expected_set = set(expected) | {CONTENTS_MEMBER}
    with zipfile.ZipFile(SHIP_ZIP) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("SHIP bundle contains duplicate members")
        if set(names) != expected_set:
            missing = sorted(expected_set - set(names))
            extra = sorted(set(names) - expected_set)
            raise SystemExit(f"SHIP member mismatch missing={missing} extra={extra}")
        contents_bytes = zf.read(CONTENTS_MEMBER)
        if manifest.get("contents_manifest_sha256") != sha256_bytes(contents_bytes):
            raise SystemExit("SHIP contents manifest hash mismatch")
        contents = json.loads(contents_bytes.decode("utf-8"))
        if contents.get("ship_ready") is not True or contents.get("release_eligible") is not False:
            raise SystemExit("SHIP internal state flags invalid")
        records = {item["path"]: item for item in contents.get("members", [])}
        if set(records) != set(expected):
            raise SystemExit("SHIP internal member records do not match payload")
        for rel in expected:
            data = zf.read(rel)
            rec = records[rel]
            if rec.get("size") != len(data) or rec.get("sha256") != sha256_bytes(data):
                raise SystemExit(f"SHIP internal hash mismatch: {rel}")
            if data != (ROOT / rel).read_bytes():
                raise SystemExit(f"SHIP payload differs from repository file: {rel}")

    for template_name in ("restart-recovery.template.json", "deep-review.template.json"):
        data = json.loads((TEMPLATE_DIR / template_name).read_text(encoding="utf-8"))
        if data.get("status") != "PENDING":
            raise SystemExit(f"native template must ship PENDING: {template_name}")
        if data.get("candidate_source_tree_sha") != candidate.get("source_tree_sha"):
            raise SystemExit(f"native template candidate binding mismatch: {template_name}")

    sums = SHIP_SUMS.read_text(encoding="utf-8")
    if sha256_file(SHIP_ZIP) not in sums or sha256_file(SHIP_MANIFEST) not in sums:
        raise SystemExit("SHIP checksum file is stale")
    print(json.dumps({
        "status": "PASS",
        "ship_ready": True,
        "native_validation_status": "PENDING",
        "release_eligible": False,
        "bundle_sha256": sha256_file(SHIP_ZIP),
        "payload_members": len(expected),
    }, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run-id", default="")
    sub.add_parser("verify")
    args = ap.parse_args()
    if args.cmd == "build":
        build(args.run_id)
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
