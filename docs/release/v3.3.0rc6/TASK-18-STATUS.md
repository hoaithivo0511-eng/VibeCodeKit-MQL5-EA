# Task 18 Status — Trusted Native Execution

**Status:** BLOCKED / NATIVE EVIDENCE PENDING
**Candidate build input:** `3d83321e48196ec8b5ea165afaf05412406d99ff`
**Source tree:** `507eb8dae02a47d41a86d224fc8d4d567d06c691`
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
2. Follow `TASK-18-NATIVE-EVIDENCE-RUNBOOK.md` using the exact current RC6 wheel,
   EA-IR, `.set` and tester configuration.
3. Capture real MetaEditor compile, Strategy Tester and all four restart case
   logs; sign the schema 2.1 manifest and hash chain.
4. Import the evidence and require
   `verify_rc6_native_evidence.py --require-pass` to return PASS.

Until all four steps pass, Task 18 remains pending and no release claim is
permitted.
