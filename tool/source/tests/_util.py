"""Shared fixtures for the shipped regression suite.

These helpers build *complete, physically present* evidence trees so that the
tests exercise the real gate logic rather than the trivial "nothing exists"
rejection path. A gate that only refuses empty projects proves nothing; the
interesting question is whether it refuses a project that looks complete.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

CORE_ARTIFACTS = (
    "evidence/compile/compile-log.txt",
    "evidence/compile/ea.ex5",
    "evidence/backtest/report.xml",
    "evidence/stress/stress-matrix-report.json",
    "evidence/review/deep-review.json",
)

FAKE_EX5 = b"TOTALLY_FAKE_BINARY_PADDED_PAST_32_BYTES_1234567890"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_forged_project(root: Path) -> Path:
    """Create a project whose evidence is fabricated but structurally perfect.

    Every core artifact exists, every hash in the manifest matches the bytes on
    disk, and the backtest report claims a profitable strategy. Nothing here
    was produced by MetaEditor or the Strategy Tester -- which is precisely the
    condition the release gate must detect.
    """
    project = root / "MyEA"
    for rel in CORE_ARTIFACTS:
        (project / rel).parent.mkdir(parents=True, exist_ok=True)

    (project / "evidence/compile/compile-log.txt").write_text(
        "0 errors, 0 warnings\n", encoding="utf-8")
    (project / "evidence/compile/ea.ex5").write_bytes(FAKE_EX5)
    (project / "evidence/backtest/report.xml").write_text(
        '<?xml version="1.0"?><report>'
        "<TotalTrades>412</TotalTrades>"
        "<ProfitFactor>2.31</ProfitFactor><NetProfit>18422.50</NetProfit>"
        "<ExpectedPayoff>44.7</ExpectedPayoff></report>\n", encoding="utf-8")
    (project / "evidence/stress/stress-matrix-report.json").write_text(
        json.dumps({"status": "PASS", "scenarios": 24, "failed": 0}), encoding="utf-8")
    (project / "evidence/review/deep-review.json").write_text(
        json.dumps({"status": "PASS", "findings": []}), encoding="utf-8")

    artifacts = [
        {"path": rel, "exists": True,
         "sha256": sha256_bytes((project / rel).read_bytes())}
        for rel in CORE_ARTIFACTS
    ]
    stamp = {
        "command": "metaeditor64.exe /compile:MyEA.mq5",
        "tool_version": "5.0.0.4620",
        "host": "WIN-RUNNER-01",
        "recorded_at_utc": "2026-08-02T00:00:00Z",
        "returncode": 0,
    }
    manifest = {
        "schema_version": "2.0",
        "release_eligible": True,
        "summary": {"release_eligible": True},
        "artifacts": artifacts,
        "compile": dict(stamp, source="actual_metaeditor"),
        "backtest": dict(
            stamp,
            source="actual_mt5_strategy_tester",
            command="terminal64.exe /config:tester.ini",
        ),
    }
    (project / "evidence/manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return project


def write_manifest(project: Path, manifest: dict) -> None:
    (project / "evidence/manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")


def read_manifest(project: Path) -> dict:
    return json.loads((project / "evidence/manifest.json").read_text(encoding="utf-8"))


def artifact_hashes(project: Path) -> dict[str, str]:
    return {rel: sha256_bytes((project / rel).read_bytes()) for rel in CORE_ARTIFACTS}


def generate_keypair():
    """Return (private_key, raw_public_bytes, base64_public)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, raw, base64.b64encode(raw).decode()


def sign_manifest(project: Path, private, key_id: str) -> None:
    """Attach a syntactically valid Ed25519 attestation to the manifest."""
    from vibecodekit_mql5.provenance import attestation_payload

    manifest = read_manifest(project)
    signature = private.sign(attestation_payload(manifest, artifact_hashes(project)))
    manifest["runner_attestation"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature_b64": base64.b64encode(signature).decode(),
    }
    write_manifest(project, manifest)


def pin_key(project: Path, key_id: str, raw_public: bytes) -> None:
    from vibecodekit_mql5.trust_root import TRUST_FILE, fingerprint

    (project / TRUST_FILE).write_text(
        "schema_version: 1\n"
        "policy:\n  require_pinned_runner_key: true\n"
        "runner_keys:\n"
        f"  - key_id: {key_id}\n"
        "    algorithm: Ed25519\n"
        f'    public_key_sha256: "{fingerprint(raw_public)}"\n',
        encoding="utf-8",
    )
