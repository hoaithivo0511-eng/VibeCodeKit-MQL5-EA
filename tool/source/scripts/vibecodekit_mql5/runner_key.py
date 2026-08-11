"""Native-runner signing key management (``mql5-runner-key``).

The release gate demands a detached Ed25519 signature over the canonical
evidence payload, produced by the machine that actually ran MetaEditor and the
Strategy Tester. This CLI is the operator-side half of that contract.

Design constraints that matter for security:

* ``generate`` writes the private key with mode 0600 and prints only the public
  half. The private key is never echoed, never copied into evidence, and never
  travels with the project.
* ``sign`` runs **on the runner**, reads the project's evidence manifest, and
  embeds the signature plus ``key_id``. It refuses to sign a manifest whose
  artifact hashes do not match the files on disk, so an operator cannot be
  tricked into signing a payload that describes different bytes than the ones
  actually produced.
* ``fingerprint`` prints the value to paste into ``RELEASE-TRUST.yaml``.

Subcommands::

    mql5-runner-key generate --key-id windows-runner-01 --out ~/.vck/runner.key
    mql5-runner-key fingerprint --key ~/.vck/runner.key
    mql5-runner-key sign <project_dir> --key ~/.vck/runner.key --key-id windows-runner-01
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
from pathlib import Path

from .release_policy import sha256_file
from .trust_root import fingerprint

TOOL = "mql5-runner-key"
CORE_ARTIFACTS = (
    "evidence/compile/compile-log.txt",
    "evidence/compile/ea.ex5",
    "evidence/backtest/report.xml",
    "evidence/stress/stress-matrix-report.json",
    "evidence/review/deep-review.json",
)


def _require_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )

        return serialization, Ed25519PrivateKey, Ed25519PublicKey
    except ImportError:
        sys.stderr.write(
            "cryptography is required for runner signing: pip install 'cryptography>=42'\n"
        )
        raise SystemExit(2)


def _load_private(path: Path):
    _serialization, Ed25519PrivateKey, _ = _require_crypto()
    raw = base64.b64decode(path.read_text(encoding="utf-8").strip())
    return Ed25519PrivateKey.from_private_bytes(raw)


def _public_raw(private) -> bytes:
    serialization, _, _ = _require_crypto()
    return private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def cmd_generate(args: argparse.Namespace) -> int:
    serialization, Ed25519PrivateKey, _ = _require_crypto()
    out = Path(args.out).expanduser()
    if out.exists() and not args.force:
        sys.stderr.write(f"refusing to overwrite existing key at {out} (use --force)\n")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    raw_priv = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    out.write_text(base64.b64encode(raw_priv).decode() + "\n", encoding="utf-8")
    try:
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # non-POSIX filesystem; ownership still restricts access
    pub_raw = _public_raw(private)
    payload = {
        "key_id": args.key_id,
        "algorithm": "Ed25519",
        "private_key_path": str(out),
        "public_key_b64": base64.b64encode(pub_raw).decode(),
        "public_key_sha256": fingerprint(pub_raw),
    }
    print(json.dumps(payload, indent=2))
    sys.stderr.write(
        "\nNext steps:\n"
        f"  1. Pin this in RELEASE-TRUST.yaml:\n"
        f"       - key_id: {args.key_id}\n"
        f"         algorithm: Ed25519\n"
        f'         public_key_sha256: "{payload["public_key_sha256"]}"\n'
        f"  2. Export for the verifier:\n"
        f'       export VCK_RUNNER_PUBLIC_KEY_B64="{payload["public_key_b64"]}"\n'
        f"  3. Keep {out} on this machine only. Never commit it.\n"
    )
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    private = _load_private(Path(args.key).expanduser())
    pub_raw = _public_raw(private)
    print(
        json.dumps(
            {
                "public_key_b64": base64.b64encode(pub_raw).decode(),
                "public_key_sha256": fingerprint(pub_raw),
            },
            indent=2,
        )
    )
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    from .provenance import artifact_paths_for_manifest, attestation_payload

    project = Path(args.project_dir)
    manifest_path = project / "evidence/manifest.json"
    if not manifest_path.is_file():
        sys.stderr.write(f"no evidence manifest at {manifest_path}\n")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Refuse to sign a manifest that misdescribes the bytes on disk. Signing is
    # an assertion about reality, so verify reality first.
    records = {str(a.get("path")): a for a in manifest.get("artifacts", []) if isinstance(a, dict)}
    hashes: dict[str, str] = {}
    problems: list[str] = []
    try:
        paths_to_sign = artifact_paths_for_manifest(manifest)
    except (TypeError, ValueError) as exc:
        sys.stderr.write(f"refusing to sign: {exc}\n")
        return 1
    for rel in paths_to_sign:
        path = project / rel
        if not path.is_file() or path.is_symlink():
            problems.append(f"missing artifact {rel}")
            continue
        actual = sha256_file(path)
        record = records.get(rel)
        if not record or record.get("exists") is not True or record.get("sha256") != actual:
            problems.append(f"manifest hash does not match bytes on disk for {rel}")
            continue
        hashes[rel] = actual
    if problems:
        sys.stderr.write("refusing to sign:\n" + "\n".join(f"  - {p}" for p in problems) + "\n")
        return 1

    private = _load_private(Path(args.key).expanduser())
    signature = private.sign(attestation_payload(manifest, hashes))
    manifest["runner_attestation"] = {
        "algorithm": "Ed25519",
        "key_id": args.key_id,
        "signature_b64": base64.b64encode(signature).decode(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pub_raw = _public_raw(private)
    print(
        json.dumps(
            {
                "ok": True,
                "signed": str(manifest_path),
                "key_id": args.key_id,
                "public_key_sha256": fingerprint(pub_raw),
                "artifacts_signed": len(hashes),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)

    g = sub.add_parser("generate", help="Generate a runner signing keypair.")
    g.add_argument("--key-id", required=True)
    g.add_argument("--out", default="~/.vck/runner.key")
    g.add_argument("--force", action="store_true")
    g.set_defaults(fn=cmd_generate)

    f = sub.add_parser("fingerprint", help="Print the public key and its pin fingerprint.")
    f.add_argument("--key", required=True)
    f.set_defaults(fn=cmd_fingerprint)

    s = sub.add_parser("sign", help="Sign a project's evidence manifest on the runner.")
    s.add_argument("project_dir")
    s.add_argument("--key", required=True)
    s.add_argument("--key-id", required=True)
    s.set_defaults(fn=cmd_sign)

    args = ap.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
