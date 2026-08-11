# Native validation handoff — VibeCodeKit MQL5 v3.3.0rc6

The active native workflow is generic and accepts an approved `EA-IR.json`.
CCBSN remains a golden fixture only; it is never injected as a production
default. Follow the exact RC6 runbook:

```text
docs/release/v3.3.0rc6/TASK-18-NATIVE-EVIDENCE-RUNBOOK.md
```

## Required environment

- Windows with the intended MT5 terminal and MetaEditor build.
- Hedging account/tester configuration.
- Broker symbol profile matching the preset.
- No live-account execution during validation.

## Mandatory sequence

1. Verify and install the exact RC6 candidate wheel.
2. Generate the EA project from the approved EA-IR with that installed wheel.
3. Compile only the generated entrypoint in MetaEditor.
4. Preserve compiler version, command, return code, warning/error count and EX5 SHA-256.
5. Run Strategy Tester scenarios:
   - baseline;
   - spread spike;
   - tick burst;
   - gap;
   - restart/reconnect state recovery;
   - Hedge Zone manual-close/partial-fill reconciliation;
   - daily halt across day rollover/history synchronization;
   - broker stop/freeze/filling constraints.
6. Include event-ordering scenarios with partial close and multiple deal fragments.
7. Bind the candidate wheel, EA-IR, generated source, `.set`, tester config,
   tester result, restart logs and review into schema 2.1 signed evidence.
8. Run `verify_rc6_native_evidence.py --require-pass`.
9. Ship `.ex5` only after Task 18 and the final Task 19 predicate pass.

## Expected pre-native state

```text
static_verified = true
compile_verified = false
tester_verified = false
release_eligible = false
```
