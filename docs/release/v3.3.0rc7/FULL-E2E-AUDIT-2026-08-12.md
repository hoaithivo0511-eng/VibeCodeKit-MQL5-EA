# Full E2E Audit — VibeCodeKit MQL5 v3.3.0rc7

Audit date: **2026-08-12**  
Methodology: **VibecodeV5 Full**  
Baseline: `main` commit `44d449eefde51446a1006f583017d2741c57f7df`, tree `21079e4d6e6c43954e1b90b119ae34e24073e1d8`

## 1. Executive verdict

The latest integrated RC7 tool is healthy at the repository, Python source, package, installed-wheel and Windows-native MetaEditor compile layers. It remains intentionally fail-closed at runtime-release layers that have no trusted MT5/broker/restart evidence.

```text
SOURCE_CORE                 PASS
PYTHON_3.10                 PASS
PYTHON_3.11                 PASS
PYTHON_3.12                 PASS
SELFTEST                    PASS
ENTRYPOINTS                 PASS
PACKAGE_REPRO               PASS
INSTALLED_WHEEL             PASS
REPOSITORY_HYGIENE          PASS
DUPLICATE_POLICY            PASS
REPOSITORY_MANIFEST         PASS
NATIVE_METAEDITOR           PASS
DOCS_TRUTH                  FAIL -> FIXED IN AUDIT BRANCH
GITHUB_RELEASE_PROV_PARITY  FAIL -> FIXED IN AUDIT BRANCH
STRATEGY_TESTER             UNTESTABLE / NOT PROVEN
RESTART_RECOVERY            UNTESTABLE / NOT PROVEN
BROKER_PARITY               UNTESTABLE / NOT PROVEN
FORWARD_LIVE                NOT PROVEN
RELEASE_ELIGIBLE            FALSE
```

## 2. VibecodeV5 audit loop

### SCAN

Locked the exact `main` commit/tree and inspected:

- canonical package source under `tool/source/`;
- public CLI router and 139-entry catalog;
- compile router/backends/evidence validators;
- release policy/provenance/ship path;
- CI workflows and native composite action;
- repository manifest, duplicate policy, fixtures and historical artefacts;
- root docs plus the five end-user docs scanned by selftest.

### RRI

Primary risk questions:

1. Can a false compile/backtest/evidence artefact become a release claim?
2. Do all compile backends converge on one compile truth policy?
3. Does GitHub-native evidence remain trusted through the final ship provenance path?
4. Can build/cache/smoke artefacts contaminate production source?
5. Are package and installed-wheel behaviours equivalent to source checkout?
6. Do docs describe the current tool rather than a prior release?
7. Are environment gaps reported as UNTESTABLE instead of PASS?

### SPECIFY / DECIDE

Audit target is the **tool itself**, not any demo strategy. CCBSN and generic acceptance projects are fixtures/evidence only.

Release semantics chosen for this audit:

- compile readiness can be proven independently;
- Strategy Tester/restart/broker/forward/live cannot inherit compile PASS;
- docs-only truth fixes must not rewrite historical point-in-time reports;
- functional issues on a release trust path require regression coverage.

### CONTRACT

No PASS/READY/RELEASE statement is accepted solely from a filename, source label, process exit code or parseable report. Required authority comes from the corresponding parser + hashes + provenance + policy gate.

### PLAN / BUILD

Changes produced by this audit:

- synchronize README/STRUCTURE/RC7 status with current RC7 truth;
- replace stale RC6/8-step English operator docs with RC7 10-step guidance;
- update current documentation map;
- preserve historical HTML reports as historical snapshots;
- fix GitHub-native release-provenance classification parity;
- add regression tests preventing both provenance and docs regression;
- regenerate installed-wheel distribution snapshot and repository manifest.

### VERIFY

Baseline CI evidence:

- Development Gate run `31615494049`: PASS on Python 3.10/3.11/3.12;
- Repository Manifest run `31615493890`: PASS;
- Package Integration run `31615250775`: PASS;
- source test baseline: 283 PASS;
- selftest: 13/13 PASS;
- 139 catalog entries consistent and callable;
- deterministic wheel built twice with identical SHA-256;
- installed wheel verified outside checkout.

Windows native evidence:

- exact candidate run `31614944493`, job `94175295785`: PASS;
- exact merged-main run `31615667887`, job `94177720870`: PASS;
- MetaEditor `5.0.0.6111`;
- `Result: 0 errors, 0 warnings`;
- EX5 physically present and hash-verified.

### EVIDENCE

Exact merged-main native record:

```text
commit      44d449eefde51446a1006f583017d2741c57f7df
tree        21079e4d6e6c43954e1b90b119ae34e24073e1d8
run         31615667887
job         94177720870
EX5 sha256  39fbcc2b15ff304c01e9ef87907e855b0dbef29e3f25d0bcff0776dc1115a7f8
installer   a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93
```

The audit does not promote this compile record into Strategy Tester or live evidence.

### RETRO

Two gaps escaped the previous RC7 remediation:

1. **Version/workflow docs drift**: code and Vietnamese master guide moved to RC7 while root/English docs retained RC6/8-step wording. Remedy: one current docs map, short operator docs, and a docs-truth regression.
2. **Two release-provenance paths disagreed**: `EvidenceManifestV2.evaluate()` passed `provenance_verified` for GitHub-native records, but final `validate_release_provenance()` did not. Remedy: route final classification through the same GitHub evidence validator and test valid/invalid records end-to-end.

## 3. Source and CLI audit

Canonical public surface is five commands:

```text
vkmql-new
vkmql-check
vkmql-ship
mql5-ea-deep-review
mql5-doctor
```

The 139-entry catalog remains available for advanced/internal compatibility use. `vkmql-check compile` is the canonical compile frontend.

Compile `auto` order:

```text
local native Windows
→ GitHub Actions Windows
→ remote Windows worker
→ Wine MetaEditor (dev/diagnostic)
→ UNTESTABLE
```

`compile_runner` is retained as compatibility/evidence wrapping, not a second compile-policy authority.

## 4. Native action audit

Toolchain preparation and compile are separated:

```text
Prepare-VKMql5Toolchain.ps1
  → resolve/install MetaEditor
  → optional installer hash verification
  → standard-library materialization/verification

Invoke-VKMql5Compile.ps1
  → stage source
  → ProbeEA
  → target compile
  → parse Result
  → emit log/EX5/result evidence

Finalize-VKMql5ToolchainEvidence.ps1
  → restore verified toolchain provenance
```

A prior bug that trusted installer process exit and a prior 20-second unverified standard-library warmup are no longer present in the invoke path.

## 5. Release provenance parity finding

### Finding

`EvidenceManifestV2` validates `github_actions_metaeditor` with `validate_github_compile_record()` and passes `provenance_verified=True` into `assess_compile_source()`.

The final `validate_release_provenance()` path previously classified the same source without that verified flag. Because `execution_sources` deliberately refuses to trust the GitHub source label alone, an otherwise valid GitHub-native compile could be rejected at the final ship provenance boundary.

### Severity

**P1 functional release-path inconsistency** (P0 if an operator depends exclusively on GitHub-native compile as release authority and expects the documented path to ship).

### Remediation

The audit branch validates the complete GitHub compile record in the final provenance path, propagates the verified result into source assessment, and rejects invalid GitHub records with explicit errors.

## 6. Supply-chain hardening observation

The reusable native action can verify an expected installer SHA-256 when supplied. The canonical workflow currently runs when `MT5_INSTALLER_URL` exists and treats `MT5_INSTALLER_SHA256` as optional.

Recording the installer SHA after download is useful provenance but is **not** equivalent to validating a pre-known trusted hash before execution.

Recommendation for release environments:

```text
require MT5_INSTALLER_URL
require pre-known MT5_INSTALLER_SHA256
reject release-trusted GitHub compile when pin policy is required but absent
```

This audit records the issue as release hardening, not as proof that the audited MetaQuotes installer was malicious.

## 7. Repository hygiene / duplicates

PASS. The repository distinguishes:

- intentional installed-wheel distribution mirrors;
- self-contained acceptance fixtures;
- frozen historical CCBSN input mirrors;
- historical report evidence;
- native-worker handoff mirrors;
- license copies;

from unclassified byte-identical duplicates, which fail the hygiene gate.

No RC7 temporary smoke workflow/project remains in production `main`.

## 8. Documentation audit

Stale active documents found:

- root `README.md` opened as RC6;
- `STRUCTURE.md` mixed RC6 boundary and RC7 candidate wording;
- `DOC-MAP.md` declared RC6 current truth;
- `USAGE-en.md` taught the legacy 8-step workflow;
- `USER-GUIDE-en.md` described RC6 and Wine-first compile assumptions;
- `COMMANDS.md` still called RC6 the current baseline;
- `RC7-CANDIDATE-STATUS.md` predated exact candidate/main native proof.

Canonical Vietnamese guide and GitHub native compile guide were already RC7-aware and are retained as authoritative detailed references.

Historical HTML E2E reports are not rewritten; their old version/test counts are point-in-time evidence.

## 9. Runtime gaps intentionally not faked

The following need target-EA/runtime evidence and remain outside the proven set:

- Strategy Tester result with trusted execution source;
- real trade count/performance metrics appropriate to the target;
- stress matrix backed by native restart/recovery cases;
- abrupt terminal kill and restart reconciliation;
- no-duplicate-order recovery;
- broker/profile parity;
- walk-forward/forward operation;
- final owner approval / live eligibility.

## 10. Release decision

RC7 is suitable as the current **build/audit tool source line** and has real Windows-native compile proof. It is not honest to label the kit or an EA built with it `LIVE_ELIGIBLE` solely from these results.

Current decision:

```text
repository-ready       yes
source-ready           yes
package-ready          yes
native-compile-ready   yes
runtime-release-ready  no evidence sufficient
release_eligible       false
```
