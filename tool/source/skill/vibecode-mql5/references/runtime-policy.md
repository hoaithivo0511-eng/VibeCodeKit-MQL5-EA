# Runtime Policy

## Environment authority

- Accept Windows-native MetaEditor/MT5 as release-authoritative in the initial product.
- A native MetaEditor execution may run locally, on an attested remote Windows worker, or through the VibeCodeKit GitHub Actions Windows backend when its run/repository/job/source/artifact provenance validates.
- A `github_actions_metaeditor` label by itself is never authority. Require a Windows runner, correlated workflow run and numeric job id, exact repository + commit/tree binding, MetaEditor/toolchain probe provenance, 0 errors, 0 warnings, the expected EX5, and verified artifact SHA-256/size records.
- Use Wine for development, diagnostics or CI unless an explicit policy validates parity.
- Keep absence of MetaEditor, GitHub native-runner configuration, terminal, market data or broker connectivity as `UNTESTABLE`.
- Backend auto-selection for compile is: native local Windows → configured GitHub Actions Windows → configured remote Windows worker → Wine development backend → `UNTESTABLE`.

## Native compile policy

The canonical compile surface is `vkmql-check compile` / `mql5-compile`. All execution backends must use the same MetaEditor result policy:

- `Result:` summary is required.
- errors allowed: `0`.
- warnings allowed: `0` by default.
- the expected `.ex5` must physically exist.
- stale compile logs and stale `.ex5` files must not satisfy a new run.
- infrastructure failures and source failures must remain distinguishable.

For GitHub Actions, source files may be copied into a temporary compiler staging tree and normalized to UTF-16 LE BOM, but the repository source must not be rewritten. Evidence must retain original source hash, staged hash and encoding transformation metadata.

Use a small ProbeEA before compiling project targets so installer/toolchain failures are classified independently from project MQL5 failures. Prefer one MT5 installation for a multi-target compile plan instead of reinstalling for each target.

GitHub compile artifacts are evidence inputs, not release decisions. Do not commit generated CI result files back to the source branch merely to report a compile. Use GitHub job summaries/artifacts and the canonical evidence pipeline instead.

## Backtest policy

Require backtests when `behavior_changed`, `trading_logic_changed`, `risk_changed`, or the target is forward/live. Do not require backtests for documentation-only changes or behavior-preserving refactors whose preservation is proven.

Execution or risk changes also require appropriate negative, stress, restart/recovery, spread/slippage and forward evidence.

A native GitHub compile PASS does **not** imply Strategy Tester, forward, restart/recovery, broker or live eligibility. Those stages remain independently gated and fail-closed.

## Broker portability

Use runtime capability detection and profile overrides for symbol aliases, digits, volume bounds and steps, stop/freeze levels, filling mode, account mode and sessions. Add broker-specific adapters only for behavior that a capability profile cannot represent.

## ONNX

Keep ONNX optional. Require a model manifest containing source, license, hash, size, quantization and input/output schema. Reject stub files as real inference evidence. Test action-label mapping end to end.

## MCP

Treat MCP as an internal experimental adapter. Keep CLI/schema logic as the source of truth. Publish a versioned MCP surface only after command names, schemas, authentication and compatibility policy stabilize.

## Evidence storage

Use local evidence by default. Make remote evidence optional for teams, CI or audits. Before remote sync, redact or encrypt accounts, broker identifiers, strategy source, trade history, personal paths, logs and credentials.

The canonical release manifest is `evidence/manifest.json` schema `2.0` (or a newer explicitly supported bound-input schema). A release-looking result also needs compile/backtest provenance fields (`source`, `command`, `tool_version`, `host`, `recorded_at_utc`), hashes for all required artifacts, a non-empty XML report with metrics, and a verified hash chain. File presence, imported logs, fixture reports, fake EX5 bytes, an uncorrelated GitHub artifact, and Wine-only compile are not release authority. `check_all`, attestation and ship validation must agree through this same fail-closed policy.

## Telemetry

Default telemetry to off. Offer `OFF`, `LOCAL_DIAGNOSTICS`, and explicit `ANONYMOUS_OPT_IN` modes. Remote telemetry may include tool version, broad OS family, canonical command, duration, mode, result state and sanitized error code.

Never transmit source code, strategy rules or parameters, account/broker identifiers, trade history, raw backtest reports, logs, Decision Ledger contents, approval signatures, prompts, local paths or secrets.
