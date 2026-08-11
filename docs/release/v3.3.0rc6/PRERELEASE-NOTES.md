# VibeCodeKit MQL5 v3.3.0rc6 — tester candidate notes

> **PRE-RELEASE / TEST CANDIDATE — NOT FOR LIVE TRADING**

RC6 remains deliberately fail-closed with `release_eligible=false`. Trusted
Windows MetaEditor/MT5 compile, Strategy Tester and restart/recovery evidence
remain mandatory before production promotion.

## Published immutable tag

The GitHub pre-release tag `v3.3.0rc6` identifies the original Task 17
candidate:

- build input `6dc50827c64bac426e0092291e1dc27330fecf55`;
- source tree `53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`;
- source/ZIP/wheel parity 252/252; selftest 13/13.

Its tag and assets are historical and are not retargeted or overwritten.

## Current documentation-sync candidate

The candidate integrated after Task 20 uses:

- build input `3d83321e48196ec8b5ea165afaf05412406d99ff`;
- source tree `507eb8dae02a47d41a86d224fc8d4d567d06c691`;
- live source, standalone source ZIP and installed wheel: 254/254 tests PASS;
- all three selftests: 13/13 PASS;
- documentation scan: 204 tracked documents, zero broken relative links;
- MCP bridge: 30 tools with functional HTML/Markdown documentation rendering;
- reproducible normalized wheel: byte-for-byte PASS.

## Current artifact SHA-256

```text
166462a71b14a0e9623b2cac8aa9c7a316d0b7a7318fb4663ee026dd221fa5f9  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
6fca0b2424008279044a37e9c39a4a5df4099af5e7fd1e364ce98109494b3eaa  tool/vibecodekit-mql5-v3.3.0rc6-source-full.manifest.json
4c98c71f66c185b24f526034d9df7d7484e25fa2164e7af87225b230397cf408  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
10ea6d8bdafaf1a43cee370dce93d3c010bb436c1cd597fbb84ec2440d37a2dc  docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json
1b3cfec599a09a9adb3075c74d38d87058d4a056ff9183d7ac5dc3240e5e4a52  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

## Tester handoff

1. Verify `RC6-ARTIFACTS.sha256` before extraction or installation.
2. Run the shipped regression suite and `mql5-selftest` from both the source ZIP
   and installed wheel.
3. Review generic code generation, runtime safety, documentation rendering,
   provenance fail-closed behavior and cross-project isolation.
4. Record MT5-dependent findings separately; absence of native evidence must
   not be converted into PASS.

Report defects against the exact commit and artifact SHA-256 being tested.
