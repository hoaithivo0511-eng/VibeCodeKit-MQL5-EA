---
id: migrate-vps
title: MetaQuotes Native VPS migration checklist
---

# MetaQuotes Native VPS migration checklist

Emitted by `/mql5-deploy-vps`. The MetaQuotes Native VPS rents a
remote terminal that mirrors your local broker login. The migration is
**not scriptable** — it lives behind the broker login + the
MetaQuotes account UI — so this file is the canonical handoff to a
human operator.

## Pre-flight

- [ ] EA passes Layer 7 (broker-safety) of the kit's permission
      pipeline.
- [ ] EA passes Trader-17 ≥ 15/17 in ENTERPRISE mode.
- [ ] EA has run on at least one demo account for 5 trading days with
      stable equity curve.
- [ ] `eurusd-h1.set` (or equivalent) committed to the repo.

## Activation

1. In your local terminal: right-click the chart → **Register a
   Virtual Server** → MetaQuotes-ID-Server.
2. Choose **MetaQuotes Native VPS** (not "Forex VPS Pro").
3. Pick the data center closest to your broker's matching engine
   (London for EURUSD, NY4 for US equities, etc.).
4. Select **Migrate Experts and Indicators**.
5. Pay (USD 10/month → 30/month tier).

## Post-activation

- [ ] Confirm chart icon in terminal turns green (VPS attached).
- [ ] Confirm the EA appears in the VPS's Experts list.
- [ ] Set up `/mql5-canary` to monitor the first 30 minutes:
      ```
      python -m vibecodekit_mql5.canary <EA>.ex5 --duration 30m
      ```
- [ ] Within 24 h: verify the equity curve on the VPS matches the
      local terminal's curve to ±0.1%.

## Rollback

- Right-click the chart → **Unregister a Virtual Server**.
- The local terminal resumes trading immediately. No data loss; the
  VPS retains the open positions until the local terminal reconnects.

## Known limitations

- Pure ONNX EAs work, but model size > 50MB may cause migration
  rejection — split the model or move inference to a Python sidecar.
- LLM bridges using `WebRequest` to non-whitelisted hosts will silently
  fail on the VPS — re-whitelist via the broker terminal before
  migration.
- `OrderSendAsync` with `OnTradeTransaction` does work on the VPS but
  the transaction callback can lag by ~1 tick more than on the local
  terminal (network jitter).
