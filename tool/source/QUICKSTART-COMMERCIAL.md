# Quick start (commercial bundle)

Three commands take you from this zip to a verified Expert Advisor build.

```bash
# 1. Verify the bundle imports cleanly on your machine
python3 -m vibecodekit_mql5.selftest

# 2. Build an EA from a preset into ./MyEA
python3 -m vibecodekit_mql5.build grid --name MyEA --symbol XAUUSD --tf M5 --out ./MyEA

# 3. See where the build stands in the golden flow
python3 -m vibecodekit_mql5.golden_flow --out-dir ./MyEA
```

Everything else (compile, backtest, gate, ship) is described in `docs/COMMANDS.md`.
