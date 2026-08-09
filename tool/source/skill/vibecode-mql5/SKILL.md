---
name: vibecode-mql5
description: Plan, build, review, verify, or govern MQL5 Expert Advisors with a risk-scaled Vibecode workflow and machine-verifiable evidence. Use for MQL5 EA bug fixes, strategy changes, new EAs, audits, backtest or release preparation, EA-SPEC and AI-BUILD-CONTRACT work, Decision Ledger updates, Retro Guardrails, broker portability, or investigation of trading-runtime failures. Use Lite for non-behavioral edits, Standard for bounded strategy/module work, and Full for risk, execution, architecture, forward-test, or live-release scope.
---

# Vibecode MQL5

Apply product reasoning without weakening the MQL5 runtime gates. Treat the owner-approved specification as the semantic source of truth and runtime evidence as the source of release claims.

## Respect scope and authority

- Follow system, user, repository, security, and tool instructions before this skill.
- Never claim production-ready, release-eligible, or live-ready without a verified evidence manifest whose `release_eligible` value is true and whose relevant artifact hashes exist.
- Treat `LIVE_ELIGIBLE` as permission to consider deployment, not as proof of profitability or safety.
- Do not install Wine, MetaTrader, models, system packages, or remote services unless the user explicitly requests that operation.
- Do not activate live trading or modify a live account.

## Select the operating mode

Choose the smallest mode that covers the risk. State the selected mode and why.

### Lite

Use only for documentation, comments, logging, display-only UI, typo fixes, or behavior-preserving refactors. Ask no more than three high-leverage questions. Produce a short task note and focused verification.

Automatically promote out of Lite when a change may affect entry, exit, indicators, position sizing, risk, SL/TP, order lifecycle, retry, units, persistence, broker behavior, or generated trading signals.

### Standard

Use for bounded feature or strategy-module work, multi-file changes, indicator calculations, non-live broker compatibility, or focused audits. Perform a focused scan and RRI, create or update the contract and task graph, then verify affected behavior.

### Full

Use for new EAs, architecture changes, money/risk logic, execution and recovery, platform porting, forward-test preparation, or any live-release scope. Require formal specification, Decision Ledger, owner approval, task graph, complete evidence gates, and retro review.

Read [references/operating-loop.md](references/operating-loop.md) for mode artefacts and phase exits.

## Run the workflow

1. **SCAN** — inspect the repository, instructions, environment, current evidence, and affected trading behavior.
2. **RRI** — propose likely defaults, then ask only unresolved high-impact questions.
3. **SPECIFY** — create or update `EA-SPEC.yaml`; distinguish semantic fields from generated metadata.
4. **DECIDE** — record approved semantic decisions in `DECISIONS.yaml`, including examples and locking tests.
5. **CONTRACT** — generate `AI-BUILD-CONTRACT.json`/`.md`, allowed paths, forbidden paths and claims, required evidence, and triggered behavioral guards.
6. **PLAN** — create a risk-ordered task graph and acceptance commands.
7. **BUILD** — implement only approved scope. Propose semantic spec changes instead of silently applying them.
8. **VERIFY** — run available deterministic checks and preserve `FAIL`, `UNTESTABLE`, and `SKIPPED` honestly.
9. **EVIDENCE** — bind results to artifact and environment hashes.
10. **RETRO** — record repeated failure patterns and promote universal recurring items into guard rules.

## Panel / UI mode

Use `[PANEL]` for MT5 chart-panel design and review. Default to `chart_objects`; use `canvas` only for dense custom graphics. Non-trivial panels require `UI-CONTRACT.yaml` with semantic sources, refresh cadence, anchor/DPI strategy, destructive-control confirmation, and performance budgets.

- `OnTick` may publish a cheap snapshot and dirty flags, but never render or call `ChartRedraw`.
- `OnChartEvent` records intent only; execution remains behind the async/risk executor.
- A bounded `OnTimer` renderer reads the snapshot and renders only when dirty and cadence allows. It is not a parallel thread; events for one EA remain sequential.
- Renderer code must not call trading, network, file, indicator-creation, or full account/position scan APIs.
- Non-visual tester runs skip UI unless explicitly required. Full panel work requires static lint, contract conformance, runtime render profile, and Windows-native visual evidence before live eligibility.

Apply `RETRO-A13` for UI claim provenance and `RETRO-A14` for UI performance integrity. Read [UI Panel Governance](../../docs/UI-PANEL-GOVERNANCE.md) and [UI Contract Template](../../docs/UI-CONTRACT.yaml.tmpl).

When one agent performs multiple roles, explicitly switch hats:

- `[CONTRACTOR]`: clarify, specify, propose, and request semantic approval.
- `[BUILDER]`: implement the approved contract without changing architecture or owner decisions.
- `[VERIFIER]`: independently compare implementation and evidence to the approved contract.

## Protect approved semantics

After owner approval, permit automatic edits only to formatting, timestamps, generated identifiers, hashes, paths, or fields explicitly marked `derived`. For any change to strategy, execution, risk, error policy, release gates, symbol/timeframe, or behavior, create a change request with current value, proposed value, reason, affected tests, and required owner approval.

Treat clear affirmative natural-language approval as approval when the scope is unambiguous. Ask a short clarification when the approved artefact or scope is ambiguous.

Read [references/decisions-and-release.md](references/decisions-and-release.md) before modifying approved specs, recording waivers, or evaluating forward/live eligibility.

## Apply Retro Guards

Before producing a TIP or code, detect whether the task involves counting/state semantics, runtime failure policy, prior decisions, test expected values, dynamic caches, async side effects, persistent test state, retry events, unit conversion, platform parity, benchmarks, or multi-file edit matching.

Attach every triggered guard to the contract with an ID, severity, required evidence, checker, remediation, and waiver policy. Prose-only rules are not enforcement.

Initialize evidence with `mql5-retro-init <project>`; it creates only
`UNTESTABLE` records. Run `vkmql-check retro <project>` after adding hashed
artifacts and checker results. The runtime checker is conservative: missing
semantic proof remains `UNTESTABLE`, never an inferred `PASS`.

Read [references/retro-guards.md](references/retro-guards.md) whenever any guard trigger is present.

## Use runtime gates correctly

- Prefer the high-level canonical CLI surface for common flows; use lower-level commands only for diagnosis or capabilities not exposed by the high-level surface.
- Treat Windows native MetaEditor/MT5 evidence as the release authority for the initial product. Treat Wine evidence as development or CI evidence unless policy explicitly says otherwise.
- Require backtest evidence for behavior, strategy, execution, or risk changes and for forward/live eligibility. Do not require backtests for documentation-only or proven behavior-preserving changes.
- Use broker capability detection and profiles before adding broker-specific code.
- Keep ONNX inference optional. Never treat a stub model as a real model, and verify action-label mappings end to end.
- Treat MCP as an internal/experimental adapter until its schemas and command catalog are versioned and stable.
- Keep telemetry off by default. Never transmit source, strategy parameters, accounts, trade history, decisions, prompts, paths, logs, credentials, or signatures.

Read [references/runtime-policy.md](references/runtime-policy.md) before compile/backtest, broker, Wine, ONNX, MCP, evidence-store, telemetry, or live-release work.

## Report outcomes

Always separate:

- what changed;
- what was verified locally;
- what remains `UNTESTABLE` in the current environment;
- whether the change is draft, backtest-eligible, forward-eligible, or live-eligible;
- which owner approvals or real-environment evidence remain required.

Do not turn a successful internal unit-test run into a live-release claim.
