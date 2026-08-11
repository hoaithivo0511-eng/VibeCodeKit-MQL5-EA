# Task 20 Completion — RC6 Documentation Sync

**Status:** PASS / READY FOR FAIL-CLOSED MAIN INTEGRATION

**Date:** 2026-08-11

**Build input commit:** `3d83321e48196ec8b5ea165afaf05412406d99ff`

**Source tree SHA:** `507eb8dae02a47d41a86d224fc8d4d567d06c691`

**Release eligible:** `false` — Task 18 trusted native evidence is still pending.

## Completed scope

- Synchronized active RC6 guides to version `3.3.0rc6`, 139 public commands,
  selftest 13/13 and the current fail-closed release contract.
- Classified RC4/RC5 and earlier UI/audit reports as historical evidence
  instead of rewriting their original results.
- Repaired all tracked relative documentation links; 204 documentation files
  were scanned with zero unresolved relative targets.
- Kept all 11 canonical scaffold READMEs byte-identical to their packaged
  resource copies and replaced location-dependent links with stable targets.
- Restored the MCP documentation runtime used by `docs.ea_render`; the bridge
  exposes 30 tools and emits HTML/Markdown output. Missing optional PDF support
  returns an explicit error instead of a false PASS.
- Hardened source/wheel snapshot verification against installer-created Python
  caches and isolated wheel builds from untracked workspace caches.

## Parity evidence

| Channel | Tests | Failures | Errors | Skips | Selftest |
|---|---:|---:|---:|---:|---:|
| live source | 254 | 0 | 0 | 0 | 13/13 PASS |
| standalone source ZIP | 254 | 0 | 0 | 0 | 13/13 PASS |
| installed wheel | 254 | 0 | 0 | 0 | 13/13 PASS |

Additional gates:

- canonical packaged verification snapshot: 48/48 files PASS;
- candidate package/member verification: PASS;
- reproducible normalized wheel: PASS, SHA-256
  `4c98c71f66c185b24f526034d9df7d7484e25fa2164e7af87225b230397cf408`;
- RC6 repository hygiene: PASS;
- native predicate: PENDING, therefore `release_eligible=false`.

## Candidate SHA-256

```text
166462a71b14a0e9623b2cac8aa9c7a316d0b7a7318fb4663ee026dd221fa5f9  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
6fca0b2424008279044a37e9c39a4a5df4099af5e7fd1e364ce98109494b3eaa  tool/vibecodekit-mql5-v3.3.0rc6-source-full.manifest.json
4c98c71f66c185b24f526034d9df7d7484e25fa2164e7af87225b230397cf408  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
10ea6d8bdafaf1a43cee370dce93d3c010bb436c1cd597fbb84ec2440d37a2dc  docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json
1b3cfec599a09a9adb3075c74d38d87058d4a056ff9183d7ac5dc3240e5e4a52  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

## Decision

The owner authorized the verified candidate to be integrated into `main` for
tester handoff. This is a repository integration, not production promotion;
the existing `v3.3.0rc6` tag remains immutable and native MT5 gates remain
mandatory before any live-trading claim.
