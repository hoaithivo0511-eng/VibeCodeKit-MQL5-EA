"""Pinned release trust root for native-runner attestations.

Why this module exists
----------------------
v3.0.0a3-R2 introduced an Ed25519 signature requirement over the canonical
release-evidence payload.  That closed the "write the magic source string"
forgery (ADV-4), but it left a strictly weaker hole open (ADV-6): the verifier
read the *public key itself* from ``VCK_RUNNER_PUBLIC_KEY_B64`` and trusted
whatever it found there.  An attacker who can set an environment variable in
the build process could therefore generate a fresh keypair, sign the forged
payload with the matching private key, export the matching public key, and
obtain ``release_eligible=True`` over an ``ea.ex5`` that is literally an ASCII
string.  The signature verified perfectly -- against a key nobody had ever
authorised.

A signature is only worth the provenance of the key that made it.  This module
supplies the missing half: an **in-repo pin** naming exactly which runner keys
may sign a release.

Threat model, stated honestly
-----------------------------
Pinning does not make forgery impossible -- nothing a repo-local checker does
can, because the repo writer can also edit the pin file.  What pinning buys is
**detectability and blast radius**:

* ``RELEASE-TRUST.yaml`` is a top-level project contract artifact.  It is
  covered by the contract stage, by owner approval, and by the evidence hash
  chain.  Editing it is a visible, reviewable, hash-breaking act, whereas
  setting an environment variable leaves no trace in the artifact at all.
* An unpinned key is now a hard ``FAIL`` (an active, reported rejection),
  not a quiet ``PASS``.
* Key rotation becomes an explicit, auditable change to a reviewed file.

The irreducible root of trust remains operator key custody: the private key
must live on the native Windows runner and nowhere else.  This module makes
that assumption explicit and machine-checked instead of implicit and silent.

File format (``RELEASE-TRUST.yaml`` at the project root)::

    schema_version: 1
    policy:
      require_pinned_runner_key: true
    runner_keys:
      - key_id: windows-runner-01
        algorithm: Ed25519
        public_key_sha256: "9f86d081..."   # SHA-256 of the 32 raw pubkey bytes
        owner: ops@example.com
        note: "MT5 build box, key generated in TPM 2024-11"
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRUST_FILE = "RELEASE-TRUST.yaml"
SCHEMA_VERSION = 1
SUPPORTED_ALGORITHMS = {"Ed25519"}


def fingerprint(public_key_raw: bytes) -> str:
    """SHA-256 fingerprint of the 32 raw Ed25519 public-key bytes.

    We fingerprint the *raw* key bytes rather than a base64 or PEM encoding so
    the pin is stable across encodings and cannot be evaded by re-wrapping the
    same key in a different container format.
    """
    return hashlib.sha256(public_key_raw).hexdigest()


@dataclass
class PinnedKey:
    key_id: str
    public_key_sha256: str
    algorithm: str = "Ed25519"
    owner: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "public_key_sha256": self.public_key_sha256,
            "owner": self.owner,
            "note": self.note,
        }


@dataclass
class TrustRoot:
    present: bool = False
    path: str = ""
    keys: list[PinnedKey] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    require_pinned_runner_key: bool = True

    def by_key_id(self, key_id: str) -> PinnedKey | None:
        for key in self.keys:
            if key.key_id == key_id:
                return key
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "path": self.path,
            "require_pinned_runner_key": self.require_pinned_runner_key,
            "keys": [k.to_dict() for k in self.keys],
            "errors": list(self.errors),
        }


def _parse(text: str) -> Any:
    """Parse YAML when PyYAML is present, else fall back to JSON.

    PyYAML is a declared core dependency, but the verifier must never crash
    open just because an environment is missing it -- a parse failure has to
    surface as a refusal, not as a skipped check.
    """
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return json.loads(text)


def load_trust_root(project_dir: Path | str) -> TrustRoot:
    """Load and validate the pinned trust root for a project.

    A missing file yields ``present=False`` with no errors: that is an
    *incomplete* configuration (release stays UNTESTABLE), not an attack.  A
    malformed or empty file yields errors, which callers must treat as FAIL --
    a corrupt pin must never degrade into "no pin required".
    """
    root = Path(project_dir)
    path = root / TRUST_FILE
    trust = TrustRoot(path=str(path))
    if not path.is_file():
        return trust

    trust.present = True
    try:
        data = _parse(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        trust.errors.append(f"{TRUST_FILE} is not parseable: {exc}")
        return trust
    if not isinstance(data, dict):
        trust.errors.append(f"{TRUST_FILE} must be a mapping")
        return trust
    if data.get("schema_version") != SCHEMA_VERSION:
        trust.errors.append(f"{TRUST_FILE} schema_version must be {SCHEMA_VERSION}")

    policy = data.get("policy")
    if isinstance(policy, dict) and "require_pinned_runner_key" in policy:
        trust.require_pinned_runner_key = bool(policy.get("require_pinned_runner_key"))

    entries = data.get("runner_keys")
    if not isinstance(entries, list) or not entries:
        trust.errors.append(f"{TRUST_FILE} declares no runner_keys")
        return trust

    seen: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            trust.errors.append(f"runner_keys[{index}] is not a mapping")
            continue
        key_id = str(raw.get("key_id") or "").strip()
        digest = str(raw.get("public_key_sha256") or "").strip().lower()
        algorithm = str(raw.get("algorithm") or "Ed25519").strip()
        if not key_id:
            trust.errors.append(f"runner_keys[{index}] is missing key_id")
            continue
        if key_id in seen:
            trust.errors.append(f"duplicate key_id {key_id!r} in {TRUST_FILE}")
            continue
        seen.add(key_id)
        if algorithm not in SUPPORTED_ALGORITHMS:
            trust.errors.append(f"runner_keys[{index}] unsupported algorithm {algorithm!r}")
            continue
        # A fingerprint must be a full SHA-256 hex digest. Truncated or
        # placeholder pins ('TBD', 'changeme', a short prefix) are rejected
        # rather than silently matching nothing -- or, worse, matching loosely.
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            trust.errors.append(
                f"runner_keys[{index}] public_key_sha256 must be a 64-char SHA-256 hex digest"
            )
            continue
        trust.keys.append(PinnedKey(
            key_id=key_id,
            public_key_sha256=digest,
            algorithm=algorithm,
            owner=str(raw.get("owner") or ""),
            note=str(raw.get("note") or ""),
        ))
    return trust


def template(key_id: str = "windows-runner-01") -> str:
    """Render a starter RELEASE-TRUST.yaml with no usable key pinned.

    The template deliberately ships **empty of real fingerprints**. A scaffold
    that pre-filled a placeholder digest would be a trap: projects would carry
    a file that looks configured but pins nothing. Instead the commented block
    forces a deliberate operator action, and until that happens the release
    gate reports INCOMPLETE.
    """
    return f"""# Release trust root -- which native runner keys may sign release evidence.
#
# The release gate requires a detached Ed25519 signature over the canonical
# evidence payload, produced by the machine that actually ran MetaEditor and
# the MT5 Strategy Tester. This file pins WHICH key is allowed to do that.
#
# Without this pin, any keypair that can be injected through the environment
# would be accepted -- including one generated by whoever is producing the
# evidence. That is the ADV-6 self-signing bypass.
#
# To configure:
#   1. On the native Windows runner:  mql5-runner-key generate --key-id {key_id}
#   2. Copy the printed public_key_sha256 into runner_keys below.
#   3. Keep the private key on the runner. Never commit it, never export it.
#   4. Provide the public key to the verifier via VCK_RUNNER_PUBLIC_KEY_B64.
#
# Until a real fingerprint is pinned, release evidence stays INCOMPLETE and
# the project can never be marked release-eligible. That is intended.
schema_version: {SCHEMA_VERSION}
policy:
  require_pinned_runner_key: true
runner_keys: []
#  - key_id: {key_id}
#    algorithm: Ed25519
#    public_key_sha256: "<64-char sha256 of the raw 32-byte public key>"
#    owner: "ops@example.com"
#    note: "MT5 build box; key generated on the runner, never exported"
"""
