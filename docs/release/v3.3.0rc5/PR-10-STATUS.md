# PR-10 Status — Trusted Native Evidence

**State:** HARNESS IMPLEMENTED — TRUSTED NATIVE EXECUTION PENDING

**Base:** `hardening/v3.3.0rc5@66a4914469614253a0f493b47a6daeb9b3d8aed6`

## Implemented in this branch

- Fail-closed Task-10 candidate/evidence verifier.
- Windows native operator runner for MetaEditor + MT5 Strategy Tester.
- Exact Task-09 package-candidate hash binding inside signed compile provenance.
- Required restart/crash recovery case schema and enforcement.
- Existing Ed25519 native-runner trust model reused; no parallel trust mechanism.
- Native evidence CI contract distinguishes `PENDING` from `PASS` and refuses to promote a missing native run.
- Development gate and repository-manifest refresh are enabled on `release/**` branches.
- Source contract tests lock trusted execution source classifications and signed core artifact set.

## Deliberately not claimed

The current ChatGPT/GitHub execution environment does not expose an installed Windows MetaEditor/MetaTrader 5 terminal or a previously pinned private native-runner key. Therefore this branch does **not** claim:

- MetaEditor native compile PASS,
- MT5 Strategy Tester native PASS,
- abrupt-kill/restart/no-duplicate/migration recovery PASS,
- signed native runner attestation PASS,
- `release_eligible=true`.

These remain P0/P1 release blockers until the native runbook is executed on a trusted Windows/MT5 runner and the resulting evidence is verified.

## Release decision

`release_eligible` MUST remain `false` until trusted native evidence is present and `scripts/maintenance/verify_rc5_native_evidence.py --require-pass` succeeds against the evidence project.
