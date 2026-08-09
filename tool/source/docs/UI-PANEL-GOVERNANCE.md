# VibeCodeKit MQL5 EA — UI/Panel Governance

Panel UI is optional and risk-scaled. `chart_objects` is the default renderer; `canvas` is opt-in for dense custom graphics.

## Runtime boundary

`OnTick` performs strategy/execution only and may publish a cheap snapshot plus dirty flags. `OnChartEvent` records intent only. A bounded `OnTimer` renderer reads the snapshot and renders only when dirty and cadence allows. All events for one EA are sequential; `OnTimer` is not a parallel thread.

## Required contract

Every non-trivial panel declares source, freshness, layout/DPI behavior, destructive-control confirmation, and performance budgets in `UI-CONTRACT.yaml`. Lite visual-only work may use a compact inline contract; Full mode requires static and runtime evidence.

## Performance rules

- Never render, call `ChartRedraw`, perform I/O/network, create indicators, or execute trades from `OnTick`.
- Renderer is data-pure: snapshot + tokens + layout → visual output.
- Use dirty flags, bounded timer cadence, stable object prefix, and deterministic cleanup.
- Skip UI in non-visual tester mode unless explicitly required.
- Measure p95/p99 render time and incremental OnTick overhead.

## Retro

`RETRO-A13` checks claim provenance and freshness. `RETRO-A14` checks render cost, hot-path isolation, queue safety, and evidence provenance.
