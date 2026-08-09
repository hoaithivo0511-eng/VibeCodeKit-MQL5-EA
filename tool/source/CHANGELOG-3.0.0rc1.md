# v3.0.0rc1 — release-trust hardening

Promotes `3.0.0a3` (R2) to release candidate. The theme of this release is
closing the last forgeable path in the release gate and making every remaining
claim checkable from the shipped artifact itself.

## Security

### ADV-6 self-signing bypass — closed (was P0)

**The defect.** R2 required an Ed25519 signature over the canonical evidence
payload, but loaded the verifying public key from `VCK_RUNNER_PUBLIC_KEY_B64`
and trusted it unconditionally. An attacker could generate their own keypair,
sign fabricated evidence, export the matching public key, and obtain
`release_eligible=True` over an `ea.ex5` that was an ASCII string. The signature
verified correctly — against a key nobody had authorised.

**The fix.**

- New `RELEASE-TRUST.yaml` project contract artifact pinning authorised runner
  keys by `key_id` **and** SHA-256 fingerprint of the raw public key.
- New `trust_root` module: strict parsing, placeholder/truncated fingerprints
  rejected, duplicate `key_id` rejected, a corrupt pin file fails closed.
- `provenance._verify_runner_attestation` now requires `key_id`, resolves it
  against the pin, and compares fingerprints before verifying the signature.
- Deliberate failure taxonomy: absent configuration is `INCOMPLETE`; a present
  but wrong or unpinned key is `FAIL`. An unpinned key is never a silent pass.
- New `mql5-runner-key` CLI (`generate` / `fingerprint` / `sign`). `sign` refuses
  to run when manifest hashes disagree with the bytes on disk.
- `cryptography>=42` promoted to a core dependency: the gate must not be able to
  skip its own signature check because a library is missing.

**Honest limitation, unchanged:** pinning raises detectability and blast radius;
it does not make forgery impossible, because whoever can write the repo can also
edit the pin. The irreducible root of trust is operator key custody. See
`docs/RELEASE-TRUST.md`.

## Verifiability

- **`tests/` now ships with the distribution.** Previous builds advertised a
  passing test count while excluding the suite from the package, leaving the
  claim unverifiable from the delivered artifact.
- New `tests/test_adversarial_release_gate.py`: ADV-1/2/4/6 regressions,
  including a positive control so the suite cannot be satisfied by a gate that
  always refuses.
- New `tests/test_ui_lint_detectors.py`: every UX / UI-PERF detector tested in
  both directions — fires on a violation, silent on compliant source.
- `mql5-selftest` grows from 10 to 12 invariants, adding `runner_key_pinning`
  (reproduces ADV-6 in-process) and `tests_shipped`.

## UI / UX lint

Three rules that were previously registry entries with no implementation now
have real source detectors:

- `UI-PERF-01` — panel work in `OnTick` without a cadence or budget guard.
- `UI-PERF-03` — resource lifecycle pairing (`EventSetTimer`/`EventKillTimer`,
  canvas create/destroy, `iCustom`/`IndicatorRelease`).
- `UI-PERF-04` — latency/FPS claims in source with no provenance sidecar.

## Documentation

- New `docs/RELEASE-TRUST.md` and `docs/DOC-MAP.md` (canonical-source map that
  names the ~149 KB of duplication instead of hiding it).
- Corrected two stale numeric claims: the "106 test cases" line in
  `V3-DELIVERY.md` and the "519 entries" line in `V3-ALPHA3-FIX-REPORT.md`.
- `dist-manifest.json` now ships, giving an authoritative file count and hashes.

## Corrections to the prior audit

- The claim that `mql5-lint` exits `0` despite ERROR findings was **wrong**. The
  original measurement piped output through `head`, so the observed exit status
  belonged to `head`. `lint` correctly returns `1`. A regression test now pins
  this behaviour so the claim stays checkable.

## Still not done — stated plainly

- Compile, backtest, forward and stress stages have **never** been executed
  against a real MetaEditor / MT5 terminal in any release so far. Every such
  stage reports `UNTESTABLE` and blocks release-eligibility by design.
- No end-to-end acceptance run of the signing workflow on a real Windows runner.
- Documentation consolidation is deferred to a docs-only release.

**This build is not evidence that any EA is live-ready.** It is a governance and
scaffolding kit whose gates are now considerably harder to forge.
