# PR-10 Status — RC5 Native Evidence

**Status:** `BUILDING_INFRASTRUCTURE / NATIVE EXECUTION PENDING`

**Release eligible:** `false`

## Completed in this branch

- Dedicated Task-10 branch from the merged Task-09 hardening head.
- RC5 candidate-binding validator.
- Canonical native evidence finalizer using existing provenance, runner-key and hash-chain primitives.
- Native Windows PowerShell collection wrapper.
- Adversarial unit tests for candidate drift, compile errors, duplicate orders, restart blind retry and scenario tampering.
- GitHub fail-closed native evidence gate.

## Still blocked

The following cannot be claimed from a GitHub-hosted Linux runner and require a real trusted MetaEditor/MT5 execution environment:

1. MetaEditor compile of the generated RC5 probe EA.
2. MT5 Strategy Tester report from the compiled EX5.
3. Actual async partial-fill lifecycle proof.
4. Actual interruption/restart or crash-recovery proof.
5. Native runner Ed25519 signature from a reviewed pinned key.

Until all five are committed and independently verified, Task 10 remains incomplete and `docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json` must remain `release_eligible=false`.

## Next gate

After infrastructure CI is green, open PR-10 as a draft into `hardening/v3.3.0rc5`. The native-evidence job is expected to remain red/BLOCKED until the real Windows evidence set is supplied. Do not merge a red/BLOCKED PR-10.
