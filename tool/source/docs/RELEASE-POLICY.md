---
id: release-policy
title: Release policy (v3; v2.6-compatible)
---

# Release policy v3 (v2.6-compatible)

The release gate has exactly one canonical predicate:
`release_policy.compute_release_eligible(...)`. Every verdict
(`vkmql-check all`, `verify_evidence`, `vkmql-ship`) routes through it so the
same inputs always produce the same answer.

## Valid statuses (ordered)

```text
DRAFT-NOT-VALIDATED
CONTRACT-PASSED
COMPILE-PASSED
BACKTEST-PASSED
STRESS-PASSED
REVIEW-PASSED
RELEASE-CANDIDATE
RELEASE-ELIGIBLE
```

## Forbidden claims

`READY`, `LIVE-READY`, `PRODUCTION-READY` are never valid statuses, and
`RELEASE-ELIGIBLE` is never allowed when any of the following is missing:

```text
compile evidence
EX5 hash
backtest report
stress report
deep review report
evidence manifest
hash chain
```

## Gate-pass keys

Release is eligible only when **all** of these hold:

| Key | Meaning |
| --- | --- |
| `contract_passed` | AI-BUILD-CONTRACT + risk contract satisfied |
| `compile_passed` | MetaEditor compile produced an EX5 |
| `backtest_passed` | Strategy Tester backtest evidence present |
| `stress_passed` | Stress matrix has zero FAIL scenarios |
| `doc_claims_verified` | No unproven ready-claims in docs |
| `risk_contract_satisfied` | Risk bounds enforced |
| `evidence_hash_chain_valid` | Attestation hash chain verifies |
| `manifest_release_eligible` | Manifest marks release eligible |

## Honesty invariants

- Anything not locally observable (real compile, real backtest, real broker
  stress) is reported as `UNTESTABLE`, never `PASS`.
- `UNTESTABLE` blocks release-eligibility just like `FAIL`.
- The verdict is idempotent: re-running `vkmql-check all` does not change a
  result without an input change.
- `compute_release_eligible` treats the newer `stress_ok` and `hash_chain_ok`
  keys as neutral `True` by default so pre-v2.6 callers keep working, while
  `vkmql-check all` always passes the real observed values.

## No evidence = no ready

If you have not produced compile + backtest + stress + review evidence and a
valid hash chain, the only honest status is `DRAFT-NOT-VALIDATED` (or the
highest gate actually passed). The toolkit will not let a project claim more.
# External runner attestation

`evidence/manifest.json` is not a trust root. A compile/backtest claim is
release-eligible only when the native Windows runner signs the canonical
manifest payload with Ed25519 and the verifier receives the runner public key
through `VCK_RUNNER_PUBLIC_KEY_B64` outside the project tree. Missing key or
signature is `UNTESTABLE`, never `PASS`.


> **The public key alone is not a trust root.** It must additionally match a
> fingerprint pinned in the project's `RELEASE-TRUST.yaml`. A key that verifies
> a signature but is not pinned is rejected with `FAIL`, not accepted. Without
> this pin, anyone able to set an environment variable could generate their own
> keypair and sign fabricated evidence (tracked as ADV-6). See
> [RELEASE-TRUST.md](RELEASE-TRUST.md) for the operator workflow, the exact
> failure taxonomy, and an honest statement of what pinning does and does not
> guarantee.