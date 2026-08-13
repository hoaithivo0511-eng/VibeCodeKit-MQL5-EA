"""Adversarial regression tests for the release-evidence gate.

Each test encodes a real bypass that was found by audit against a shipped
build. They are written as attacks, not as happy paths, because the gate's
entire value proposition is what it *refuses*. If any of these ever go green
in the "attack succeeded" direction again, the kit has regressed to shipping
forgeable release claims.

History:
  ADV-1/ADV-2  v3.0.0a2  forged hash chain / tampered evidence     -- blocked
  ADV-4        v3.0.0a3  magic provenance strings, no signature    -- blocked in R2
  ADV-6        R2        self-generated signing key (self-signing) -- blocked here
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from _util import (  # type: ignore
    build_forged_project, generate_keypair, pin_key, sign_manifest,
)


class _EnvGuard(unittest.TestCase):
    """Isolate VCK_RUNNER_PUBLIC_KEY_B64 so tests cannot leak state."""

    def setUp(self) -> None:
        self._saved = os.environ.pop("VCK_RUNNER_PUBLIC_KEY_B64", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.pop("VCK_RUNNER_PUBLIC_KEY_B64", None)
        if self._saved is not None:
            os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = self._saved
        self._tmp.cleanup()

    def validate(self, project: Path):
        from vibecodekit_mql5.provenance import validate_release_provenance
        return validate_release_provenance(project)


class TestAdv4NoSignature(_EnvGuard):
    def test_perfect_manifest_without_signature_is_not_pass(self) -> None:
        """ADV-4: complete evidence + correct hashes + plausible provenance
        strings must still not pass without a runner signature."""
        project = build_forged_project(self.root)
        result = self.validate(project)
        self.assertNotEqual(result.status, "PASS")
        self.assertFalse(result.ok)
        self.assertIn("external runner Ed25519 attestation", result.missing)


class TestAdv6SelfSigning(_EnvGuard):
    def test_self_generated_key_is_rejected_when_unpinned(self) -> None:
        """ADV-6 (the headline bypass): an attacker generates their own
        keypair, signs the forged payload correctly, and exports the matching
        public key. The signature is cryptographically valid -- and must still
        be refused, because that key was never authorised."""
        project = build_forged_project(self.root)
        attacker, raw_pub, b64_pub = generate_keypair()
        sign_manifest(project, attacker, key_id="attacker-key")
        pin_key(project, "windows-runner-01", generate_keypair()[1])  # a DIFFERENT key
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = b64_pub

        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("not pinned" in e for e in result.errors),
            f"expected an unpinned-key rejection, got {result.errors}",
        )

    def test_pinned_key_id_with_swapped_key_material_is_rejected(self) -> None:
        """Subtler variant: the attacker reuses the *authorised key_id* but
        supplies their own key material. Matching on key_id alone would pass
        this; only a fingerprint comparison catches it."""
        project = build_forged_project(self.root)
        attacker, _, attacker_b64 = generate_keypair()
        _, honest_pub, _ = generate_keypair()
        sign_manifest(project, attacker, key_id="windows-runner-01")
        pin_key(project, "windows-runner-01", honest_pub)
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = attacker_b64

        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("does not match the pin" in e for e in result.errors),
            f"expected a fingerprint-mismatch rejection, got {result.errors}",
        )

    def test_missing_pin_file_is_incomplete_not_pass(self) -> None:
        """An unconfigured project must degrade to INCOMPLETE, never to PASS.
        Absence of a trust root is not permission to trust anything."""
        project = build_forged_project(self.root)
        signer, _, b64 = generate_keypair()
        sign_manifest(project, signer, key_id="windows-runner-01")
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = b64

        result = self.validate(project)
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertTrue(any("RELEASE-TRUST.yaml" in m for m in result.missing))

    def test_correctly_pinned_signature_passes(self) -> None:
        """The positive control. Without this, every test above could be
        satisfied by a gate that simply always says no -- which would be a
        useless gate, not a secure one."""
        project = build_forged_project(self.root)
        signer, raw_pub, b64 = generate_keypair()
        sign_manifest(project, signer, key_id="windows-runner-01")
        pin_key(project, "windows-runner-01", raw_pub)
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = b64

        result = self.validate(project)
        self.assertEqual(result.status, "PASS", f"errors={result.errors} missing={result.missing}")
        self.assertEqual(result.signed_by_key_id, "windows-runner-01")

    def test_signature_does_not_survive_artifact_tampering(self) -> None:
        """ADV-2 in the signed world: swap the EX5 after signing. The payload
        binds artifact hashes, so the signature must break."""
        project = build_forged_project(self.root)
        signer, raw_pub, b64 = generate_keypair()
        sign_manifest(project, signer, key_id="windows-runner-01")
        pin_key(project, "windows-runner-01", raw_pub)
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = b64
        self.assertEqual(self.validate(project).status, "PASS")

        (project / "evidence/compile/ea.ex5").write_bytes(b"DIFFERENT_BYTES_ENTIRELY_0987654321_PADDED")
        result = self.validate(project)
        self.assertNotEqual(result.status, "PASS")


class TestTrustRootParsing(_EnvGuard):
    def test_placeholder_fingerprint_is_rejected(self) -> None:
        """A pin file containing 'TBD' must error, not silently pin nothing.
        Half-configured security is the most dangerous state."""
        from vibecodekit_mql5.trust_root import load_trust_root

        project = build_forged_project(self.root)
        (project / "RELEASE-TRUST.yaml").write_text(
            "schema_version: 1\nrunner_keys:\n  - key_id: a\n    algorithm: Ed25519\n"
            '    public_key_sha256: "TBD"\n', encoding="utf-8")
        trust = load_trust_root(project)
        self.assertTrue(trust.errors)
        self.assertEqual(trust.keys, [])

    def test_empty_template_pins_nothing_and_blocks_release(self) -> None:
        """The scaffolded template must not accidentally authorise a key."""
        from vibecodekit_mql5.trust_root import load_trust_root, template

        project = build_forged_project(self.root)
        (project / "RELEASE-TRUST.yaml").write_text(template(), encoding="utf-8")
        trust = load_trust_root(project)
        self.assertEqual(trust.keys, [])


if __name__ == "__main__":
    unittest.main()
