# Runtime Policy

## Environment authority

- Accept Windows-native MetaEditor/MT5 as release-authoritative in the initial product.
- Use Wine for development, diagnostics or CI unless an explicit policy validates parity.
- Keep absence of MetaEditor, terminal, market data or broker connectivity as `UNTESTABLE`.

## Backtest policy

Require backtests when `behavior_changed`, `trading_logic_changed`, `risk_changed`, or the target is forward/live. Do not require backtests for documentation-only changes or behavior-preserving refactors whose preservation is proven.

Execution or risk changes also require appropriate negative, stress, restart/recovery, spread/slippage and forward evidence.

## Broker portability

Use runtime capability detection and profile overrides for symbol aliases, digits, volume bounds and steps, stop/freeze levels, filling mode, account mode and sessions. Add broker-specific adapters only for behavior that a capability profile cannot represent.

## ONNX

Keep ONNX optional. Require a model manifest containing source, license, hash, size, quantization and input/output schema. Reject stub files as real inference evidence. Test action-label mapping end to end.

## MCP

Treat MCP as an internal experimental adapter. Keep CLI/schema logic as the source of truth. Publish a versioned MCP surface only after command names, schemas, authentication and compatibility policy stabilize.

## Evidence storage

Use local evidence by default. Make remote evidence optional for teams, CI or audits. Before remote sync, redact or encrypt accounts, broker identifiers, strategy source, trade history, personal paths, logs and credentials.

The canonical release manifest is `evidence/manifest.json` schema `2.0`. A
release-looking result also needs compile/backtest provenance fields
(`source`, `command`, `tool_version`, `host`, `recorded_at_utc`), hashes for
all core artifacts, a non-empty XML report with metrics, and a verified hash
chain. File presence, imported logs, fixture reports, fake EX5 bytes, and
Wine-only compile are not release authority. `check_all`, attestation and
ship validation must agree through this same gate.

## Telemetry

Default telemetry to off. Offer `OFF`, `LOCAL_DIAGNOSTICS`, and explicit `ANONYMOUS_OPT_IN` modes. Remote telemetry may include tool version, broad OS family, canonical command, duration, mode, result state and sanitized error code.

Never transmit source code, strategy rules or parameters, account/broker identifiers, trade history, raw backtest reports, logs, Decision Ledger contents, approval signatures, prompts, local paths or secrets.
