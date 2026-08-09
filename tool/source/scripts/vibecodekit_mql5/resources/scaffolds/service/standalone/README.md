# {{NAME}} — service / standalone

MQL5 Service-program scaffold (`#property service`, build 5320+).
Long-running background task with its own thread, no chart, no
symbol-bound `OnTick` — the ideal home for data collectors, LLM /
REST pollers, Telegram daemons, and VPS canaries that must not
block any chart EA's tick path.

## Build requirements

- MetaEditor ≥ build 5320 (Sep 2025). Older builds lack
  `#property service` and the platform service-thread loader.
- No `CRiskGuard` / `CPipNormalizer` wiring — services do not place
  orders, so the kit's lot-sizing / SL guards are deliberately out
  of scope. Use the standard EA scaffolds (`stdlib`, `wizard-
  composable`, …) for any code that calls `CTrade`.

## Wiring

- `InpPollIntervalMs` — main-loop cadence. Tune for your I/O —
  REST 1–5 s, in-process queue 10–50 ms.
- `InpServiceTag` — journal prefix; defaults to the EA name so
  multiple services on one VPS stay distinguishable.

## Next steps

1. Implement `DoOneCycle()` with the actual work unit. Keep it
   idempotent — services restart silently on terminal updates.
2. Confirm `IsStopped()` is checked at least once per loop body
   (the kit's lint will warn if not, planned).
3. `mql5-compile {{NAME}}.mq5 --build 5320` — service programs
   must compile on build ≥ 5320.
4. Deploy via `Navigator → Services → New service` in the terminal,
   point it at the compiled `.ex5`, and check the Journal tab for
   `heartbeat @ ...` lines from `DoOneCycle()`.
