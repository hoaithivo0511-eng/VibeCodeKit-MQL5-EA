# SCAN Report — RC7 release hardening

- Baseline commit: `c4924211d3dee507957c6ec2590c21d0563cfc59`
- Baseline tree: `c444cfc3389719ac5ef8a5aaf32d2f1eed6c287d`
- Mode: Full, because the work affects packaging parity, static release gates,
  protocol adapters, CI isolation and release claims.
- Trading semantics: unchanged.
- Golden-fixture boundary: CCBSN remains test-only; no CCBSN defaults, command
  values or architecture may enter production code.

## Confirmed baseline defects

1. The package-local `agent-contract.json` says `3.3.0rc6`; canonical RC7
   metadata says `3.3.0rc7`.
2. Project lint/review scans every copied optional header, including headers
   unreachable from an EA entrypoint. Public preset builds therefore fail on
   false AP-18/UX-09 blockers.
3. Ruff may create `.ruff_cache` inside the immutable verification snapshot;
   snapshot verification then fails depending on command order.
4. `backtest._number` references `Any` without importing it, which breaks
   runtime annotation introspection.
5. Three MCP bridges do not validate required tool arguments before dispatch.
6. Active RC7 status and Retro reference documents drift from current runtime.

## Environment boundary

Linux/Python verification is available. Windows MetaEditor and MT5 Strategy
Tester are unavailable in this workspace. Their states remain `UNTESTABLE`
until trusted evidence is bound to the final source tree.
