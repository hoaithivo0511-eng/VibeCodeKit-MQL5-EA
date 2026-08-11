# Task 15 Completion — Native Provenance

Status: `PASS`

## Delivered

- Added evidence schema `2.1` while retaining schema `2.0` compatibility for
  historical RC4/RC5 evidence.
- Bound every declared evidence artifact into the runner signature and hash
  chain, including EA-IR, generated MQL5 source, source manifest, `.set`,
  `tester.ini`, tester result and restart/recovery logs.
- Required the compiled entrypoint and source manifest to prove generation by
  the installed candidate wheel.
- Required tester configuration and structured tester results to match the
  signed symbol, timeframe, date range and non-zero trade report.
- Required restart cases to reference real signed files and the deep review to
  bind the exact generated source manifest.
- Added an RC6 Windows runner and repository verifier without changing the
  historical RC5 runner.

## Verification

- RC6 adversarial provenance suite: `9/9 PASS`.
- RC5 compatibility suite: `8/8 PASS`.
- Full source regression: `246/246 PASS`, zero failures, errors or skips.
- Source selftest: `13/13 PASS`, including `39` shipped test modules.
- Canonical distribution snapshot: `46/46 files PASS`.
- Touched Python Ruff gate: `PASS`.

## Release state

`release_eligible=false`. The Windows runner contract is implemented, but a
real MetaEditor/MT5/restart run remains mandatory in Task 18.
