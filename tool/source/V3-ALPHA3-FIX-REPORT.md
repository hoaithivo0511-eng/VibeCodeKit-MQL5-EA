# VibeCodeKit MQL5 EA v3.0.0-alpha.3 — Fix & E2E Report

Date: 2026-08-02

## Result

The alpha.2 deep-review P0 finding was reproduced and fixed. A file-presence
check or a self-declared `release_eligible` value is no longer sufficient for
release evidence.

## Fixes applied

- Added `scripts/vibecodekit_mql5/provenance.py` as the canonical release
  validator.
- Routed `check_all`, `evidence_attestation` and `release_policy` through the
  same validator.
- Required trusted compile/backtest source, producer metadata, core artifact
  hashes, non-empty MT5 XML metrics, valid stress/review JSON and verified
  chain integrity.
- Classified Wine MetaEditor as development/CI evidence, not release authority.
- Added adversarial fake-evidence regression coverage.
- Slim distribution now excludes tests, fixtures, evidence, generated Retro
  temp trees, `.bak` files and generated smoke state.
- Removed stale `_p03_gate.py`, `scan_ea.py.bak` and the two fake ONNX stubs;
  ONNX remains an optional plugin requiring a real model and manifest.
- Updated AGENTS, anti-pattern, governance, README, changelog and delivery
  docs to match the runtime.

## Verification

| Check | Result |
|---|---|
| Unit/regression discovery | 107/107 PASS (source checkout); slim selftest 10/10 |
| Python compileall | PASS |
| Catalog import sweep | 133/133 PASS |
| Runtime selftest | 10/10 PASS |
| Golden scaffold → contract → task graph → Retro → aggregate gate | PASS with honest offline blockers |
| Fake evidence attestation | BLOCKED |
| Slim package hygiene | see `dist-manifest.json` for the authoritative file count and hashes; no evidence/Retro temp/.bak/ONNX stubs. The regression suite is now shipped on purpose. |

## Environment boundary

No Windows-native MetaEditor or MT5 Strategy Tester is available in this
environment. Compile, backtest, forward and live evidence therefore remain
`UNTESTABLE`; this report validates gate honesty and packaging, not EA
profitability, broker compatibility or live readiness.

## Deliverables

- `docs/E2E-AUDIT-REPORT.html` — self-contained report for Notion/external sharing.
- `vibecodekit-mql5-v3-alpha.3.zip` — deterministic slim distribution.
- `dist-manifest-alpha3.json` — source-checkout file-level SHA-256 manifest (not included in the slim user package by design).
