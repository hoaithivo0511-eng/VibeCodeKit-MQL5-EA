"""Deterministic HMAC-SHA256 signing for ship manifests.

The signing key is read from the ``VCK_SIGNING_KEY`` environment variable
(or passed explicitly). Signatures are computed over a *canonical* JSON
encoding (sorted keys, no whitespace) so two runs over the same payload
produce the same signature. When no key is configured the document is
left unsigned and callers record ``signed=false`` -- the tool never
fabricates a signature.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

ENV_KEY = "VCK_SIGNING_KEY"
ALGORITHM = "HMAC-SHA256"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Stable, whitespace-free JSON encoding for signing."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def resolve_key(explicit: str | None = None) -> str | None:
    """Return the signing key from the explicit arg or the environment."""
    if explicit:
        return explicit
    val = os.environ.get(ENV_KEY, "").strip()
    return val or None


def sign_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    digest = hmac.new(
        key.encode("utf-8"), canonical_bytes(payload), hashlib.sha256
    ).hexdigest()
    return {"algorithm": ALGORITHM, "signature": digest}


def verify_payload(payload: dict[str, Any], signature: dict[str, Any], key: str) -> bool:
    if not isinstance(signature, dict):
        return False
    expected = sign_payload(payload, key)
    return hmac.compare_digest(
        expected["signature"], str(signature.get("signature", ""))
    )


def sign_document(document: dict[str, Any], *, key: str) -> dict[str, Any]:
    """Return a copy of ``document`` with a ``signature`` block attached.

    The signature covers every field except an existing ``signature``.
    """
    payload = {k: v for k, v in document.items() if k != "signature"}
    signed = dict(document)
    signed["signature"] = sign_payload(payload, key)
    return signed


def verify_document(document: dict[str, Any], *, key: str) -> bool:
    sig = document.get("signature")
    if not isinstance(sig, dict):
        return False
    payload = {k: v for k, v in document.items() if k != "signature"}
    return verify_payload(payload, sig, key)
