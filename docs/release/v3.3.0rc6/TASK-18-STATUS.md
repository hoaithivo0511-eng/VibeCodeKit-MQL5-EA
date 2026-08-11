# Task 18 Status — Trusted Native Execution

**Status:** BLOCKED / NATIVE EVIDENCE PENDING
**Candidate:** `6dc50827c64bac426e0092291e1dc27330fecf55`
**Source tree:** `53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`
**Release eligible:** `false`

## Verified state

- The RC6 candidate manifest and all candidate artifact hashes pass local
  verification.
- `verify_rc6_native_evidence.py` reports `candidate_ok=true`,
  `native_status=PENDING` and `release_eligible=false`.
- `RELEASE-TRUST.yaml` contains no pinned runner key (`runner_keys: []`).
- No trusted Windows MetaEditor/MT5 project evidence exists at
  `docs/release/v3.3.0rc6/native-evidence/project`.

## Why execution cannot be completed here

Task 18 requires an operator-controlled Windows host with the approved
MetaEditor/MT5 installation, broker/test data, the private Ed25519 runner key
and permission to run real termination/restart scenarios. None of those
external trust inputs can be simulated or fabricated by the repository test
environment.

## Unblock procedure

1. Generate and approve the Windows runner key, then pin its public-key
   fingerprint in `RELEASE-TRUST.yaml` without committing the private key.
2. Follow `TASK-18-NATIVE-EVIDENCE-RUNBOOK.md` using the exact Task 17 wheel,
   EA-IR, `.set` and tester configuration.
3. Capture real MetaEditor compile, Strategy Tester and all four restart case
   logs; sign the schema 2.1 manifest and hash chain.
4. Import the evidence and require
   `verify_rc6_native_evidence.py --require-pass` to return PASS.

Until all four steps pass, Task 18 remains pending and no release claim is
permitted.
