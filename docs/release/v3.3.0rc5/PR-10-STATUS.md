# PR-10 Status — RC5 Native Evidence

**Status:** `INFRASTRUCTURE PASS / BLOCKED_NATIVE_EXECUTION`

**Release eligible:** `false`

**Draft PR:** `#3` — `native-evidence/v3.3.0rc5-pr10 → hardening/v3.3.0rc5`

## Infrastructure completed and verified

- RC5-specific Task-10 tooling lives only under release paths (`scripts/release/` and `tool/native/`), not inside the shipped `tool/source/` candidate.
- `tool/source/` is verified byte-for-byte against the immutable Task-09 RC5 source manifest before every native-evidence evaluation.
- Native evidence binds the exact Task-09 build input, source tree, source ZIP, source manifest, wheel and runtime-bundle hashes.
- Canonical finalization reuses the existing trusted execution-source policy, Ed25519 runner-key primitive, pinned trust root, provenance validator and evidence hash chain.
- Actual tester identity is read back from the produced `tester.ini`; operator labels cannot override the executed Symbol/Period/FromDate/ToDate/Model.
- Async partial-fill evidence requires a real partial fill, unique intent ids, `SUBMITTED → PARTIAL → COMPLETED` and zero duplicate orders.
- Restart/crash recovery requires a real interruption, persisted-intent reload, zero duplicate orders and `TERMINAL_PROOF` or `OPERATOR_REQUIRED`; blind retry is rejected.
- Adversarial Task-10 contract suite: **10/10 PASS**.
- RC5 shipped source regression: **220/220 PASS, 0 skipped** on Python 3.10/3.11/3.12.
- RC5 selftest: **13/13 PASS** on Python 3.10/3.11/3.12.
- Repository manifest, hygiene and frozen RC4 gates: **PASS** on the verified owner head.

## Native blocker

The `trusted-native-evidence` job is intentionally red with `BLOCKED_NATIVE_EXECUTION` because `release-evidence/v3.3.0rc5/evidence/manifest.json` has not yet been produced by a real Windows MetaEditor/MT5 run. GitHub-hosted Linux CI is explicitly forbidden from fabricating that evidence.

The remaining required evidence is:

1. Actual MetaEditor compile of the generated RC5 probe EA with zero errors.
2. Actual MT5 Strategy Tester report from the compiled EX5 and the exact tester.ini.
3. Actual async partial-fill lifecycle proof.
4. Actual interruption/restart or crash-recovery proof.
5. Native runner Ed25519 signature from a reviewed pinned key, plus its public key for independent GitHub verification.

Until all five are committed and independently accepted, Task 10 remains incomplete, PR #3 remains draft/unmerged, and `docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json` remains `release_eligible=false`.
