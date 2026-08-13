# RC7 release-hardening report — 2026-08-13

## Outcome

VibecodeKit MQL5 `3.3.0rc7` is locally verified as a clean tool-distribution
candidate built from `tool/source` tree
`839828d45f29b0dcb0bef0f00bb6378038e66739`. The candidate is ready for user
installation and evaluation. It is not promoted as an EA live-release because
trusted MetaEditor and MT5 Strategy Tester evidence for this exact tree is not
available.

Baseline comparison:

- online `main`: `c4924211d3dee507957c6ec2590c21d0563cfc59`
- online tree: `c444cfc3389719ac5ef8a5aaf32d2f1eed6c287d`
- hardening branch: `fix/rc7-release-hardening`

## Closed findings

- synchronized all shipped RC7 contracts and made source-to-wheel sync
  deterministic;
- changed analyzer scope to entrypoint-reachable MQL include closures, retaining
  real async findings while removing optional-header and non-UI false positives;
- isolated named Ruff/pytest runtime state without allowing arbitrary rogue files;
- repaired runtime type-hint resolution and uniform MCP required-argument checks;
- synchronized active release/Retro documentation and added A13/A14 guard truth;
- pinned release dependencies and every GitHub Action to an immutable commit SHA;
- expanded the active RC7 package gate to run Ruff, source, source ZIP, wheel,
  selftests, reproducibility, clean JUnit assertions, and upload both artifacts.

Deep wheel E2E found and closed an additional recursion defect caused when
`pytest-of-root` was created inside the installed verification snapshot. The
snapshot now ignores that named runtime directory, copy tests exclude runtime
state, and undeclared non-runtime files still fail closed.

## Verification matrix

| Surface | Result |
|---|---|
| Ruff | PASS |
| Source selftest | 13/13 PASS |
| Source regression | 300/300 PASS; no failure, error, or skip |
| Source ZIP selftest | 13/13 PASS |
| Source ZIP regression | 300/300 PASS; no failure, error, or skip |
| Installed-wheel selftest | 13/13 PASS |
| Installed-wheel regression | 300/300 PASS; no failure, error, or skip |
| Reproducible wheel | PASS; two builds have identical SHA-256 |
| Public preset E2E | PASS: trend, mean-reversion, breakout, hedging-multi |
| MCP stdio E2E | PASS: 4/4 bridges initialize/list/error correctly |
| Source ZIP safety | PASS: 853 safe members |
| Wheel safety | PASS: 421 safe members; METADATA/RECORD valid |
| MetaEditor compile | UNTESTABLE |
| MT5 Strategy Tester | UNTESTABLE |

## Artifact hashes

- source ZIP: `342950acbb26deabc6d2f742819d78814750b3379a4707747614983e65b589db`
- wheel: `35b65abb0ebd088764346c28077e58aad1383951f1c3c617a4710d4913ed37e4`

The external `RC7-HARDENING-ARTIFACTS.sha256` file also binds all three JUnit
reports. CCBSN remains a golden fixture only; no production default or strategy
semantics were introduced.

## Release truth

`compile_verified=false`, `tester_verified=false`, and
`release_eligible=false`. The auto compile command returns `UNTESTABLE` because
no trusted backend is configured, and the ship dry-run exits non-zero without a
valid evidence manifest. This fail-closed result is intentional.
