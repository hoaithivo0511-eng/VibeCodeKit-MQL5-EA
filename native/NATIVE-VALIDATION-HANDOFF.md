# Native validation handoff — VibecodeKit MQL5 3.3.0rc4 / CCBSN golden fixture

Canonical IR:

```text
940e5167d1b0b65655caefe1e2644896da6c2e67b6a4ed02bd3c25dce2dd2a5b
```

## Required environment

- Windows with the intended MT5 terminal and MetaEditor build.
- Hedging account/tester configuration.
- Broker symbol profile matching the preset.
- No live-account execution during validation.

## Mandatory sequence

1. Extract the source candidate under the terminal MQL5 directory.
2. Compile `Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5` in MetaEditor.
3. Preserve compiler version, command, return code, warning/error count and EX5 SHA-256.
4. Run Strategy Tester scenarios:
   - baseline;
   - spread spike;
   - tick burst;
   - gap;
   - restart/reconnect state recovery;
   - Hedge Zone manual-close/partial-fill reconciliation;
   - daily halt across day rollover/history synchronization;
   - broker stop/freeze/filling constraints.
5. Include event-ordering scenarios with partial close and multiple deal fragments.
6. Bind compile/tester evidence to both canonical IR hash and generated-source manifest hash.
7. Re-run `mql5-ir-verify`, `mql5-check-all`, deep review and release gate.
8. Ship `.ex5` only when `compile_verified=true`, `tester_verified=true` and `release_eligible=true`.

## Expected pre-native state

```text
static_verified = true
compile_verified = false
tester_verified = false
release_eligible = false
```
