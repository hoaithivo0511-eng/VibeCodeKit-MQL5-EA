# Deep Review — CCBSN_GoldenFixture

- Readiness: **release-blocked**  |  Score: **0/100**
- Strategy: grid-hedge (grid, hedge, dca/martingale-like sizing, indicator-driven)
- Files scanned: 12
- Code metrics: 181 functions, max complexity 23, 1 dead-code findings

## Checked categories
- strategy/signals (Stage 1)
- anti-patterns (Stage 2)
- structure & complexity (Stage 3)
- dead-code / dead-logic (Stage 4)
- risk / execution / state / release (Stage 5)
- modernization (Stage 6)
- grounded line review (Stage 7)

## Issue summary
- Critical: 2
- Error: 0
- Warn: 22
- Info: 0

### By category
- code_quality: 22
- release: 2

## Findings

### CRITICAL
- **No compile evidence** — Manifest does not prove a real compile (compile_ok missing/false).
  - Fix: Run the real compile pipeline and record compile_ok=true.
- **No backtest evidence** — Manifest does not prove a real backtest (backtest_ok missing/false).
  - Fix: Run the real backtest pipeline and record backtest_ok=true.

### WARN
- **High cyclomatic complexity: Collect()** (line 6) — [Include/CCBSN_GoldenFixture/Core/PositionBook.mqh] Collect has approx. complexity 12 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: FindLive()** (line 11) — [Include/CCBSN_GoldenFixture/Core/TradeIntentLedger.mqh] FindLive has approx. complexity 13 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: Engulfing()** (line 15) — [Include/CCBSN_GoldenFixture/Signal/EntryEngine.mqh] Engulfing has approx. complexity 15 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **Too many parameters: SaveExtended()** (line 16) — [Include/CCBSN_GoldenFixture/State/PersistentStateStore.mqh] SaveExtended takes 11 parameters (>= 7).
  - Fix: Group related parameters into a struct/config object.
- **High cyclomatic complexity: LoadExtended()** (line 18) — [Include/CCBSN_GoldenFixture/State/PersistentStateStore.mqh] LoadExtended has approx. complexity 13 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **Too many parameters: LoadExtended()** (line 18) — [Include/CCBSN_GoldenFixture/State/PersistentStateStore.mqh] LoadExtended takes 11 parameters (>= 7).
  - Fix: Group related parameters into a struct/config object.
- **High cyclomatic complexity: Open()** (line 20) — [Include/CCBSN_GoldenFixture/Core/AsyncTradeExecutor.mqh] Open has approx. complexity 18 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **Too many parameters: Open()** (line 20) — [Include/CCBSN_GoldenFixture/Core/AsyncTradeExecutor.mqh] Open takes 8 parameters (>= 7).
  - Fix: Group related parameters into a struct/config object.
- **High cyclomatic complexity: EMAFilterAllow()** (line 22) — [Include/CCBSN_GoldenFixture/Signal/EntryEngine.mqh] EMAFilterAllow has approx. complexity 17 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageBasketExit()** (line 71) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageBasketExit has approx. complexity 12 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageTrailing()** (line 72) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageTrailing has approx. complexity 19 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageSniper()** (line 74) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageSniper has approx. complexity 13 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageCrossChainSniper()** (line 75) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageCrossChainSniper has approx. complexity 19 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageHedge()** (line 77) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageHedge has approx. complexity 15 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **Unused function: ManagedPositionExists()** (line 80) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManagedPositionExists is defined at line 80 but never called.
  - Fix: Remove it or wire it into the call graph.
- **High cyclomatic complexity: ReconcileHedgeZoneState()** (line 84) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ReconcileHedgeZoneState has approx. complexity 16 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageHedgeZone()** (line 85) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageHedgeZone has approx. complexity 23 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: DCACondition()** (line 86) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] DCACondition has approx. complexity 20 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageDCA()** (line 87) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageDCA has approx. complexity 23 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ManageInitialEntry()** (line 88) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ManageInitialEntry has approx. complexity 13 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: ProcessRemoteCommands()** (line 91) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] ProcessRemoteCommands has approx. complexity 19 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.
- **High cyclomatic complexity: OnChartEvent()** (line 94) — [Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5] OnChartEvent has approx. complexity 12 (>= 12).
  - Fix: Reduce branching; extract decision logic into helpers.

## Grounded line review
- Skipped (--fast).