# VibeCodeKit MQL5 v3.3.0rc5 — hardening plan

Plan ID: `VCK-RC5-HARDENING-V1`

Baseline: `2e6b2c7d76d49e7a3c23d0bc737acdec6a1239ed`

Working branch: `hardening/v3.3.0rc5`

Method: VibeCodeMaster `SCAN → RRI → VISION → BLUEPRINT → TASK GRAPH → BUILD → VERIFY → REFINE`

## Release contract

- RC4 artifacts and their hashes are immutable historical evidence.
- `tool/source/` is the active RC5 source and may diverge from the RC4 source
  archive until the RC5 candidate package gate.
- CCBSN remains a golden fixture. No CCBSN-specific values, command vocabulary
  or strategy assumptions may enter generic production modules.
- No generated EA or kit release may claim production readiness without a
  manifest whose `release_eligible` value is true and whose artifact hashes are
  bound to trusted native evidence.
- Every implementation task ends with a Completion Report and owner gate.

## Task graph

| Order | Task | Scope | Gate |
|---:|---|---|---|
| 00 | RC5 foundation | Version, dependencies, CI split, docs and traceability | Owner review |
| 01 | Worker artifact security | Path containment, staging, hash and symlink guards | Wave 0 |
| 02 | Canonical EA-IR quickstart | IR default, explicit legacy compatibility | Wave 0 |
| 03 | Input semantics | `input`/`sinput` parsing and exact-count fixtures | Wave 1 |
| 04 | Runtime units | Per-field sign/unit contracts and `OnInit` validation | Wave 1 |
| 05 | Remote command lifecycle | Ownership, claim/delete/apply and replay safety | Wave 1 |
| 06 | Trade lifecycle | Intent v2, operation retcodes, async state and durability | Wave 1 |
| 07 | Audit gate | Real lint/review and canonical release predicate | Wave 2 |
| 08 | Review precision | Truthful stages and feature-aware strategy detection | Wave 2 |
| 09 | RC5 package integration | Snapshot sync, source/ZIP/wheel parity and hashes | Wave 3 |
| 10 | Native evidence | MetaEditor/MT5 compile, tester and crash recovery | Release |

Tasks 04, 05 and 06 modify generated runtime code and must be implemented
sequentially. Tasks 01, 02/03 and 07/08 may proceed in separate work lanes only
after Task 00 is reviewed.

## Verification policy

The deterministic source gate runs on Python 3.10, 3.11 and 3.12. Test JUnit
reports must contain zero failures, zero errors and zero skips. Frozen RC4
artifacts are hash-checked independently from active RC5 source.

Touched-module coverage targets:

| Module group | Minimum |
|---|---:|
| Worker protocol/client | 90% |
| Release policy | 90% |
| Check-all/deep-review/analyzers | 80% |
| Prompt intake/auto-build touched branches | 80% / 75% |
| Advanced code generator | Preserve at least 95% plus generated-contract tests |

P0/P1 requirements require 100% PASS. A `SKIPPED`, `UNTESTABLE`, `MISSING` or
`PAINFUL` P0/P1 result blocks the next release gate.

## Current gate

The owner approved Wave 1 after reviewing the Wave 0 Completion Reports.
Tasks 01, 02 and 03 are complete. Runtime Tasks 04, 05 and 06 must now be
implemented and verified sequentially; do not start the Wave 2 audit changes
until the Wave 1 owner gate.
