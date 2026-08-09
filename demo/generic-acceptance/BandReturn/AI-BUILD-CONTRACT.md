# AI-BUILD-CONTRACT — BandReturn

- Project: **BandReturn** v0.1.0
- Status: `DRAFT-NOT-VALIDATED`
- Generated: 2026-08-06T17:00:54Z
- Schema: 3.0
- Workflow mode: `full`
- Release target: `draft`

> This contract governs what an AI coding tool (Claude Code / Codex /
> Cursor) is allowed to do in this project. Violating it invalidates
> the build. **No evidence = no ready.**

## Allowed paths (AI may edit)
- `Experts/`
- `Include/`
- `Presets/`
- `Tester/`
- `README.md`

## Forbidden paths (AI must NEVER edit)
- `evidence/`
- `release/`
- `review/`
- `AI-BUILD-CONTRACT.md`
- `AI-BUILD-CONTRACT.json`
- `EA-SPEC.yaml`
- `DECISIONS.yaml`
- `OWNER_APPROVAL.json`

## Forbidden claims (never without evidence)
- `READY`
- `LIVE-READY`
- `LIVE READY`
- `PRODUCTION-READY`
- `PRODUCTION READY`

## Risk contract
- Max drawdown: `20.0%`
- Max daily loss: `5.0%`
- Max positions: `3`
- Stop-loss required: `False`
- Forbidden logic: `unbounded_martingale`

## Release evidence required
- compile log + EX5 hash
- evidence manifest
- evidence hash chain
- backtest report
- stress matrix report
- deep review report

## Behavioral guards
- `A1` [P1/waivable]: count-order-state-semantics — checker `retro.count_semantics`
- `A2` [P0/hard]: runtime-error-policy — checker `retro.error_policy`
- `A3` [P1/waivable]: owner-decision-lock — checker `retro.owner_decision`
- `A4` [P1/waivable]: independent-test-oracle — checker `retro.expected_value`
- `A5` [P0/hard]: dynamic-cache-freshness — checker `retro.dynamic_cache`
- `A7` [P1/waivable]: test-environment-isolation — checker `retro.environment_isolation`
- `A9` [P0/hard]: single-unit-conversion — checker `retro.unit_scale`
- `A10` [P1/waivable]: port-parity — checker `retro.port_parity`
- `A12` [P1/waivable]: edit-target-discipline — checker `retro.tool_discipline`
- `A13` [P1/waivable]: ui-claim-provenance — checker `retro.ui_claim_provenance`

## Semantic decision policy
- Ledger: `DECISIONS.yaml`
- Semantic changes require owner approval: `true`
- Evidence hashes do not replace human approval.

## Rules
1. The AI coding tool MUST NOT edit any forbidden_paths.
2. The AI coding tool MUST NOT write forbidden_claims without evidence.
3. No status above DRAFT-NOT-VALIDATED without the required evidence.
4. Every change must stay within allowed_paths.
5. Unbounded martingale / unbounded lot scaling is forbidden.
6. The AI MUST propose semantic changes and wait for owner approval.
7. FAIL, UNTESTABLE, SKIPPED and WAIVED MUST remain distinct.
