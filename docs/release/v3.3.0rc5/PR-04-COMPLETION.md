# PR-04 Completion Report — runtime input contracts

Task: `04`

Status: **COMPLETE**

## Delivered

- Added a single contract registry covering more than 60 risk-sensitive MQL5
  inputs with source path, unit, allowed range, sign and zero semantics.
- Build planning rejects explicitly supplied values with the wrong type, sign
  or range before source generation.
- Generated projects contain `RUNTIME-INPUT-CONTRACTS.json`, bound to the
  canonical EA-IR SHA-256.
- Generated MQL5 runs `ValidateOperationalInputs()` before any symbol,
  indicator, state or trade initialization and returns
  `INIT_PARAMETERS_INCORRECT` on failure.
- Cross-field gates cover base/max lot, freeze/max drawdown, Hedge, Hedge Zone,
  Reverse Entry, Lot Balance and trailing prerequisites.

## Requirements

| Requirement | Result |
|---|---|
| REQ-010 — field-level unit/range/sign/zero contracts | PASS |
| REQ-011 — invalid operational configuration fails `OnInit` | PASS |
| REQ-026 — no fixture-specific production defaults | PASS |

## Verification

| Gate | Result |
|---|---|
| Focused runtime-contract tests | 6/6 PASS |
| Advanced generator coverage | 95% |
| Runtime-contract registry coverage | 100% |
| Combined touched-module coverage | 96.76% (minimum 95%) |
| Python 3.12 source regression | 169/169 PASS |
| JUnit cleanliness | 0 failures, 0 errors, 0 skipped |
| RC5 selftest | 13/13 PASS |
| Ruff | PASS |

The MQL5 contract was verified structurally from deterministic generated source.
Native MetaEditor compilation and Strategy Tester evidence remain deferred to
release Task 10.
