# VibeCodeKit MQL5 v3.3.0rc7 — integrated candidate status

Status date: **2026-08-12**

## Verdict

`v3.3.0rc7` is the **current integrated source/tool line** in the repository. It has passed repository integrity, source regression, package reproducibility, installed-wheel verification and Windows-native MetaEditor compilation on the audited runtime baseline.

It is **not a production/live release claim**.

```text
repository/source/package/native-compile  VERIFIED
Strategy Tester                           NOT PROVEN
restart/recovery                          NOT PROVEN
broker parity                             NOT PROVEN
walk-forward / forward                    NOT PROVEN
live readiness                            NOT PROVEN
release_eligible                          false
```

Latest published GitHub tester pre-release remains `v3.3.0rc6`. RC7 has not yet been promoted to a GitHub Release/tag.

## Audited runtime baseline

PR #12 merged the RC7 audit-remediation line into `main`.

```text
main commit : 44d449eefde51446a1006f583017d2741c57f7df
source tree : 21079e4d6e6c43954e1b90b119ae34e24073e1d8
version     : 3.3.0rc7
```

A later docs-only audit branch may have a different Git tree SHA while leaving runtime compile code unchanged. Exact run provenance is always recorded with the run that produced the evidence.

## Source regression evidence

Post-merge `main` Development Gate:

```text
workflow run : 31615494049
Python       : 3.10 / 3.11 / 3.12
result       : PASS
```

Package/full candidate gate on the same runtime code line:

```text
workflow run : 31615250775
source tests : 283 PASS
selftest     : 13/13 PASS
catalog      : 139 tools consistent
entrypoints  : 139 callable
JUnit        : failures=0 errors=0 skipped=0
```

The package gate built the RC7 wheel twice under the same deterministic epoch and obtained the same wheel SHA-256:

```text
d55725c7c9f7be614e2757e2c7bacd100bb39f1ab609facdfbcc1695ea5399a3
```

It then installed the wheel in a clean venv outside the checkout and reran selftest successfully.

## Repository integrity evidence

Post-merge Repository Manifest Check:

```text
workflow run : 31615493890
result       : PASS
```

Repository hygiene verifies frozen historical artefacts, derived distribution mirrors and duplicate-content policy without treating intended mirrors as junk.

## Exact candidate Windows-native compile

Exact candidate before merge:

```text
candidate commit : b85b97c263d31668f5ca4e21dcf9cac372841a08
candidate tree   : 21079e4d6e6c43954e1b90b119ae34e24073e1d8
workflow run     : 31614944493
job              : 94175295785
runner           : Windows 2022
MetaEditor       : 5.0.0.6111
Result           : 0 errors, 0 warnings
EX5 size         : 5674 bytes
EX5 SHA-256      : 7b54945f56d5aea156e30a15ed6dcd4fa3662e48ae1944ee6356911d49efa1f5
validator        : PASS
```

## Exact merged-main Windows-native compile

After PR #12 merged, a second isolated harness checked out the exact `main` merge commit and ran that commit's own composite native action:

```text
source commit : 44d449eefde51446a1006f583017d2741c57f7df
source tree   : 21079e4d6e6c43954e1b90b119ae34e24073e1d8
workflow run  : 31615667887
job           : 94177720870
runner        : Windows 2022
MetaEditor    : 5.0.0.6111
Result        : 0 errors, 0 warnings
EX5 size      : 5302 bytes
EX5 SHA-256   : 39fbcc2b15ff304c01e9ef87907e855b0dbef29e3f25d0bcff0776dc1115a7f8
validator     : PASS
installer SHA : a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93
```

The raw MetaEditor target process can return a non-zero process code even when its compile log says `Result: 0 errors, 0 warnings` and the EX5 is present. RC7 therefore treats parsed compile result + artefact evidence as compile authority, not process code alone.

## Native workflow secret semantics

The canonical PR workflow uses repository secrets:

- `MT5_INSTALLER_URL`;
- `MT5_INSTALLER_SHA256` (recommended as a release trust pin).

When `MT5_INSTALLER_URL` is absent, the canonical Windows stage is intentionally `SKIPPED`/`UNTESTABLE`; its fast/static gate may still PASS but must not be reported as a native compile PASS.

The exact Windows runs above used isolated audit harnesses to obtain real native evidence without adding smoke workflows to the production tree.

## RC7 remediation already integrated

- removed accidental `demo/rc7` / `demo/final` smoke projects and their workflows;
- classified intended duplicate content and fails closed on unclassified byte-identical files;
- made `Prepare-VKMql5Toolchain.ps1` the sole toolchain install/stdlib owner;
- reduced `Invoke-VKMql5Compile.ps1` to prepared-toolchain compile/evidence execution;
- made `compile_runner` a compatibility/evidence wrapper around canonical compile truth;
- restored canonical `scripts/native/ProbeEA.mq5` and regression coverage;
- synchronized derived distribution snapshot + repository manifest;
- updated RC7 native/backend documentation.

## Full E2E audit follow-up

The 2026-08-12 Full VibecodeV5 audit found two additional items:

1. **Docs truth drift** — active root/English docs still contained RC6 and legacy 8-step wording even though runtime was RC7. This is being corrected by the docs-sync audit branch.
2. **GitHub-native release-provenance parity** — `EvidenceManifestV2` correctly validates a `github_actions_metaeditor` record before trusting it, but the canonical `validate_release_provenance()` path did not propagate that verification into `assess_compile_source`. A valid GitHub native compile could therefore be rejected by the final ship provenance path. Regression coverage is added with the fix.

The same audit also records a release-hardening recommendation: a GitHub-native compile used as release authority should use a pre-known `MT5_INSTALLER_SHA256` trust pin; merely recording the downloaded installer hash is not equivalent to pinning it before execution.

## What remains blocked

RC7 compile evidence does **not** satisfy these independent runtime stages:

- MT5 Strategy Tester for the target EA;
- quality/stress evidence derived from real tester runs;
- abrupt terminal kill + restart/reconcile + no-duplicate-order recovery evidence;
- broker/profile and cross-broker parity appropriate to the target;
- walk-forward / forward deployment evidence;
- owner/release approval bound to the final evidence set.

Until the selected release target requires and passes those gates, `release_eligible=false` is the correct state.
