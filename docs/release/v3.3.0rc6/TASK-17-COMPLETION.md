# Task 17 Completion — RC6 Package Integration

**Status:** PACKAGE INTEGRATION PASS — OWNER REVIEW REQUIRED
**Generated:** 2026-08-11T14:43:32.316810+00:00
**Workflow run:** `local-task17-6dc5082`
**Build input commit:** `6dc50827c64bac426e0092291e1dc27330fecf55`
**Source tree SHA:** `53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`
**Release eligible:** `false` — Task 18 trusted native evidence remains mandatory.

## Parity evidence

| Channel | Tests | Failures | Errors | Skips | Selftest |
|---|---:|---:|---:|---:|---:|
| live source | 252 | 0 | 0 | 0 | 13/13 PASS |
| source ZIP | 252 | 0 | 0 | 0 | 13/13 PASS |
| installed wheel | 252 | 0 | 0 | 0 | 13/13 PASS |

## Defects found and corrected during parity

- Repository-only path assumptions in phase 28, 32 and 33 tests were exposed
  by the standalone source ZIP channel and corrected without skips.
- Wheel tests now resolve version/catalog/contract inputs from the signed
  canonical distribution snapshot instead of assuming source-root metadata is
  present beside the extracted test suite.
- The final source ZIP and wheel imports were proven to resolve outside the
  repository checkout before JUnit evidence was accepted.

## Candidate contract

- `tool/source/` is the canonical RC6 source snapshot.
- Source ZIP file set and every file digest match the tracked source snapshot.
- Wheel regression executes the same shipped test suite outside the source checkout.
- Runtime candidate bundle contains the source ZIP, source manifest, wheel and candidate manifest with verified payload hashes.
- RC4 artifacts are not overwritten or repacked.
- Candidate manifest is fail-closed with `release_eligible=false` until Task 18 native compile/test/restart evidence is bound.

## Artifact SHA-256

```text
3bc4ce857613c7f82f2aecb0648b84e1971939f282a1fd056d93440d21305059  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
d95f49c0a7253a4d7ac29a3aaa4abb291a7bc21cb99a10bb27671015644e2373  tool/vibecodekit-mql5-v3.3.0rc6-source-full.manifest.json
a2ba69f0b568d7362017d3e81f28feea80ddb71f33494989089c4669136578d6  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
6e5e70a10869af8ccd2ae184226f85ef3ca2cc793ab014aaebf031c26cdc0ec1  docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json
f13cc038ce6187543e6e556b257ec109990a3646c3c16eea8ca67489c1ac9396  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

## Gate decision

Task 17 deterministic package integration is complete at source/ZIP/wheel/runtime-bundle level. Task 18 remains fail-closed until trusted native evidence is supplied.
