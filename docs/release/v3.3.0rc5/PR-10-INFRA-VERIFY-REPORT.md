# PR-10 Infrastructure Verify Report — Trusted Native Evidence

**Branch:** `native-evidence/v3.3.0rc5-pr10`
**Base:** `hardening/v3.3.0rc5@66a4914469614253a0f493b47a6daeb9b3d8aed6`
**Verified owner head:** `5649e75152ed99b3d3a3340de89ec232393e3336`
**Decision:** `INFRASTRUCTURE PASS / NATIVE EXECUTION BLOCKED`
**Release eligible:** `false`

## Verify evidence

| Gate | Result | Evidence |
|---|---|---|
| Task-09 source immutability | PASS | `tool/source` exactly matches every path and SHA-256 in the Task-09 RC5 source manifest |
| Release tooling compile | PASS | `scripts/release/rc5_native_gate.py`, `native_evidence_collector.py`, and `verify_rc5_candidate_source.py` compile successfully |
| Native evidence contract | PASS | 10/10 adversarial tests |
| RC5 source regression | PASS | 220/220, 0 failures, 0 errors, 0 skipped on Python 3.10/3.11/3.12 |
| RC5 selftest | PASS | 13/13 on Python 3.10/3.11/3.12 |
| Repository manifest | PASS | current owner-head manifest check |
| Repository hygiene | PASS | current owner-head development gate |
| Frozen RC4 artifacts | PASS | current owner-head development gate |
| Trusted MetaEditor/MT5 evidence | BLOCKED | canonical native evidence manifest absent |
| Runner public trust root | PENDING | configure only after reviewed native runner key is generated/pinned |

## Refine finding closed

The first PR-10 draft placed RC5-specific validators under `tool/source`. That would have changed the canonical Task-09 source snapshot and made the already verified source ZIP/wheel candidate stale. Before merge, all Task-10-specific orchestration/tests were moved to release-only paths under `scripts/release/` and `tool/native/`; the temporary shipped-source additions were removed.

The native CI now proves `tool/source` is byte-for-byte identical to the Task-09 source manifest before it evaluates any native evidence. This preserves the package identity that the native runner must sign.

## Fail-closed decision

The `trusted-native-evidence` job intentionally exits with `BLOCKED_NATIVE_EXECUTION` when `release-evidence/v3.3.0rc5/evidence/manifest.json` is absent. The deeper validator is skipped in that condition rather than accepting a fixture, imported report, Wine run, or synthesized result.

PR-10 remains draft and MUST NOT be merged while this blocker exists. The RC5 candidate manifest remains `release_eligible=false`.

## Required native completion evidence

1. Actual MetaEditor compile log and EX5 with zero compile errors.
2. Actual MT5 Strategy Tester XML report plus the exact tester.ini used.
3. Actual async partial-fill evidence: partial fill observed, unique intent ids, `SUBMITTED → PARTIAL → COMPLETED`, zero duplicate orders.
4. Actual restart/crash-recovery evidence: interruption observed, persisted intent reloaded, zero duplicate orders, resolution `TERMINAL_PROOF` or `OPERATOR_REQUIRED`.
5. Ed25519 runner signature whose public-key fingerprint is pinned in `RELEASE-TRUST.yaml` and whose public key is independently supplied to GitHub verification.

Only after all five are independently accepted may a separate reviewed change consider setting `release_eligible=true`.
