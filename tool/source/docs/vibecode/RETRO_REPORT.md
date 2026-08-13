# Retro report

Status: `COMPLETE`.

## Promoted guards

- **A7 — persisted test state:** package inventories now ignore named runtime
  cache directories while continuing to reject every arbitrary undeclared file.
  Regression coverage exercises both sides of the rule.
- **A12 — multi-file edit-by-match:** source and packaged distribution metadata
  are synchronized by one maintenance command and verified by selftest plus a
  snapshot manifest.
- **A13 — visible claim freshness:** active RC7 status and README claims now bind
  to the current baseline and explicitly separate local verification from native
  evidence.

## Recurrence locks

- Version drift is locked by explicit tests over all three shipped contracts.
- Analyzer contamination is locked by reachable/unreachable include tests and a
  four-preset public builder matrix.
- Protocol drift is locked by one invalid-parameter test across all four MCP
  bridges.
- Supply-chain drift is locked by exact CI dependency versions and immutable
  GitHub Action commit pins.

## Residual risk

Native compile, Strategy Tester, broker portability, forward, and live evidence
remain `UNTESTABLE`. They are not converted to PASS, and the release gate remains
closed with `release_eligible=false`.
