# VibeCodeKit MQL5 v3.3.0rc6 — audit closeout plan

Plan ID: `VCK-RC6-AUDIT-CLOSEOUT-V1`

Baseline: `673c8a1e6b482e32f9e5734978bce51a2796bff2`

Working branch: `hardening/v3.3.0rc6`

Method: VibeCodeMaster `SCAN → RRI → VISION → BLUEPRINT → TASK GRAPH → BUILD → VERIFY → REFINE`

## Release contract

- RC4 and RC5 artifacts are historical, immutable inputs. RC6 uses new names
  and hashes and never overwrites those artifacts.
- Generic output must pass the kit's own lint and senior-review gates.
- The packaged distribution snapshot must match canonical source inputs.
- Candidate wheels must build byte-for-byte reproducibly.
- Native evidence must bind the generated source, EA-IR, set file, tester
  configuration and exact package candidate.
- `release_eligible` remains `false` until trusted native evidence passes.

## Task graph

| Order | Task | Scope | Gate |
|---:|---|---|---|
| 11 | RC6 baseline | Version, requirements and regression contracts | Source gate |
| 12 | Generator-review parity | Refactor generated runtime complexity | Four-archetype gate |
| 13 | Snapshot parity | Canonical distribution inventory and hashes | Package source gate |
| 14 | Reproducible wheel | Deterministic wheel normalization | Double-build gate |
| 15 | Native provenance | Bind source/config/evidence artifacts | Adversarial gate |
| 16 | Docs and hygiene | Version, lint, modes and traceability | Hygiene gate |
| 17 | Candidate integration | Source/ZIP/wheel parity and artifacts | Package gate |
| 18 | Trusted native execution | MetaEditor, MT5 and restart recovery | Native gate |
| 19 | Release promotion | Final predicate, protection, merge and tag | Owner/release gate |

## Verification policy

- P0/P1 requirements require PASS. SKIPPED, UNTESTABLE, MISSING or PAINFUL
  blocks release.
- Python source regression runs on 3.10, 3.11 and 3.12 with zero failures,
  errors and skips.
- Advanced generator touched-module coverage remains at least 95%.
- Every completed task has a completion report and an online commit.

## Current gate

Tasks 11 through 15 passed. Task 16 documentation and repository hygiene is
next. Native execution and release promotion remain pending.
