"""mql5-ship / vkmql-ship release - verify, package, and sign a release.

The former behaviour (``git tag`` + ``git push``) has been removed: git
release plumbing is a maintainer-only concern and no longer ships in the
end-user kit. The release verb now performs the auditable hand-off steps:

  1. **verify**  - evidence/manifest.json must be release-eligible
                   (release_policy.validate_release_manifest).
  2. **package** - package the build out-dir into manifest.json + zip
                   (package.package_out_dir, which enforces the doc gates).
  3. **sign**    - emit ship-manifest.json binding the evidence + package +
                   zip hash, signed with HMAC-SHA256 when VCK_SIGNING_KEY is
                   set (otherwise recorded as signed=false; never faked).

Nothing here is valid as a PASS/RELEASE unless the evidence manifest already
says release_eligible=true.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import package, release_policy, ship_signing

SHIP_MANIFEST_NAME = "ship-manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ship_manifest(
    out_dir: Path,
    package_manifest: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    evidence_path = out_dir / "evidence" / "manifest.json"
    zip_path = Path(package_manifest["zip_path"])
    return {
        "schema_version": "1.0",
        "kind": "ship-manifest",
        "created_at_utc": created_at or _now(),
        "out_dir": str(out_dir),
        "evidence": {
            "path": "evidence/manifest.json",
            "sha256": release_policy.sha256_file(evidence_path),
            "release_eligible": True,
        },
        "package": {
            "manifest": package_manifest.get("out_dir"),
            "zip_path": package_manifest["zip_path"],
            "zip_sha256": package.sha256_file(zip_path) if zip_path.is_file() else None,
            "artifact_count": len(package_manifest.get("artifacts", [])),
        },
    }


def release(
    out_dir: Path,
    *,
    spec_path: Path | None = None,
    manifest_path: Path | None = None,
    zip_path: Path | None = None,
    ship_manifest_path: Path | None = None,
    signing_key: str | None = None,
    created_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ok, reason = release_policy.validate_release_manifest(out_dir)
    if not ok:
        raise RuntimeError(f"blocked: not release eligible ({reason})")

    if dry_run:
        return {
            "status": "verified",
            "dry_run": True,
            "out_dir": str(out_dir),
            "release_eligible": True,
            "detail": "verify-only; no package or ship-manifest written",
        }

    pkg = package.package_out_dir(
        out_dir,
        manifest_path=manifest_path,
        zip_path=zip_path,
        spec_path=spec_path,
    )
    ship_manifest = build_ship_manifest(out_dir, pkg.to_dict(), created_at=created_at)

    key = ship_signing.resolve_key(signing_key)
    signed = bool(key)
    # Record signing metadata BEFORE signing so it is covered by the signature.
    ship_manifest["signed"] = signed
    ship_manifest["signing_env_key"] = ship_signing.ENV_KEY
    if key:
        ship_manifest = ship_signing.sign_document(ship_manifest, key=key)

    target = ship_manifest_path or (out_dir / SHIP_MANIFEST_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(ship_manifest, indent=2), encoding="utf-8")

    return {
        "status": "shipped",
        "out_dir": str(out_dir),
        "release_eligible": True,
        "signed": signed,
        "ship_manifest_path": str(target),
        "zip_path": ship_manifest["package"]["zip_path"],
        "zip_sha256": ship_manifest["package"]["zip_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-ship",
        description="Verify, package and sign a release (no git).",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=None)
    parser.add_argument("--ship-manifest", dest="ship_manifest_path", type=Path, default=None)
    parser.add_argument(
        "--signing-key",
        default=None,
        help=f"HMAC signing key (defaults to ${ship_signing.ENV_KEY}).",
    )
    parser.add_argument("--created-at", default=None, help="Fixed ISO-8601 UTC stamp.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify release eligibility only; write nothing.",
    )
    args = parser.parse_args(argv)
    try:
        result = release(
            args.out_dir,
            spec_path=args.spec,
            manifest_path=args.manifest,
            zip_path=args.zip_path,
            ship_manifest_path=args.ship_manifest_path,
            signing_key=args.signing_key,
            created_at=args.created_at,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"mql5-ship: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
