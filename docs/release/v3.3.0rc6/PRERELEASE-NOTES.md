# VibeCodeKit MQL5 v3.3.0rc6 — tester pre-release

> **PRE-RELEASE / TEST CANDIDATE — NOT FOR LIVE TRADING**

This package-integrated RC6 build is published for the final independent Opus
review. It deliberately remains `release_eligible=false`. Trusted Windows
MetaEditor/MT5 compile, Strategy Tester and restart/recovery evidence are
deferred and remain mandatory before any production promotion.

## Frozen identity

- Candidate build input commit:
  `6dc50827c64bac426e0092291e1dc27330fecf55`
- Canonical source tree:
  `53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`
- Candidate status: `package-integrated-native-pending`
- Production release eligibility: `false`

## Verified package gates

- Live source: 252/252 tests PASS; selftest 13/13 PASS.
- Standalone source ZIP: 252/252 tests PASS; selftest 13/13 PASS.
- Installed wheel outside the checkout: 252/252 tests PASS; selftest 13/13
  PASS.
- Reproducible normalized wheel: byte-for-byte PASS.
- Source snapshot, candidate bundle, artifact inventory and repository manifest:
  PASS.

## Artifact SHA-256

```text
3bc4ce857613c7f82f2aecb0648b84e1971939f282a1fd056d93440d21305059  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
d95f49c0a7253a4d7ac29a3aaa4abb291a7bc21cb99a10bb27671015644e2373  tool/vibecodekit-mql5-v3.3.0rc6-source-full.manifest.json
a2ba69f0b568d7362017d3e81f28feea80ddb71f33494989089c4669136578d6  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
6e5e70a10869af8ccd2ae184226f85ef3ca2cc793ab014aaebf031c26cdc0ec1  docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json
f13cc038ce6187543e6e556b257ec109990a3646c3c16eea8ca67489c1ac9396  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

## Tester handoff

1. Verify `RC6-ARTIFACTS.sha256` before extraction or installation.
2. Run the shipped regression suite and `mql5-selftest` from both the source ZIP
   and installed wheel.
3. Review generic code generation, runtime safety, provenance fail-closed
   behavior and cross-project isolation.
4. Record MT5-dependent findings separately; absence of native evidence must
   not be converted into PASS.

Report any defect against the tag and include the affected artifact SHA-256.
