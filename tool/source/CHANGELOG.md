## [3.3.0rc5] - Unreleased

### Hardening foundation

- Opened the RC5 hardening line from the immutable RC4 pre-release baseline.
- Made the PDF-ingest regression dependency part of the declared development
  environment so the full suite cannot silently skip after `.[dev]` install.
- Separated active RC5 source validation from frozen RC4 artifact validation;
  runtime/security fixes and RC5 candidate artifacts are delivered in later
  reviewed tasks.
- Production release remains blocked pending the planned security/runtime
  fixes and trusted MetaEditor plus MT5 Strategy Tester evidence.

### Worker artifact security

- Reject worker-controlled absolute, traversal, Windows drive/UNC/stream and
  duplicate artifact paths before network download.
- Reject source or destination paths that cross symlinks.
- Download into an isolated transaction directory, validate every declared
  artifact hash and size, then atomically replace destination files with batch
  rollback on commit failure.
- Apply the same path boundary to the deterministic mock transport used by
  regression tests.

### Canonical prompt quickstart

- Make `mql5-spec-from-prompt` emit complete EA-IR 3.1 JSON by default and
  preserve `--ir` as an alias for existing callers.
- Require `--legacy` for the older single-preset YAML view.
- Mark legacy prompt output as `legacy_scaffold` with
  `release_eligible: false` and propagate that marker into the canonical
  release blocker list.
- Reject attempts to convert a legacy mapping into EA-IR by adding only a
  `schema_version` field.
- Update quickstart and operator documentation to use the canonical
  `EA-IR.json → mql5-auto-build` flow.

### Input semantics

- Preserve `input` versus `sinput` storage semantics in generated parameter
  documentation.
- Ignore declarations inside line and block comments without corrupting quoted
  URL/comment markers, semicolons or arithmetic defaults.
- Bind parser behavior to exact-count regression fixtures.

### Runtime input contracts

- Define field-level units, ranges, sign conventions and zero behavior once and
  reuse them for EA-IR validation, generated project contracts and MQL5 runtime
  checks.
- Reject invalid explicitly supplied EA-IR values before code generation.
- Make generated EAs return `INIT_PARAMETERS_INCORRECT` with a structured
  `VCK_CONFIG_INVALID` diagnostic when operational inputs violate the contract.
- Emit `RUNTIME-INPUT-CONTRACTS.json` bound to the canonical EA-IR hash.

### Remote command lifecycle

- Require every pending-order command channel to declare a positive owner
  magic, portable comment prefix and managed-symbol scope.
- Match all ownership factors before claiming a command; price and order type
  alone are never authority.
- Persist a compare-and-swap command ledger across `CLAIMED`, `DELETED`,
  `APPLYING` and `APPLIED` boundaries.
- Delete a claimed pending order before applying its effect and verify effects
  without replaying an action after an uncertain interruption.

## [3.3.0rc4] - 2026-08-06

### Runtime-safety and semantic-isolation hardening

- Removed all vendor/demo-specific pending-order prices and fixed command
  vocabularies from production code. Remote controls are now fully data-driven
  EA-IR commands with explicit actions, collision checks and ownership gates.
- Added required semantic variants for recovery engines so generic feature
  labels cannot silently select one fixture-derived implementation.
- Centralized every exposure path behind direction, daily-halt, capacity,
  session, Hedge Zone and ownership admission policies; Stop Buy/Sell can no
  longer be bypassed by hedge, reverse-entry, balance or zone engines.
- Added a persistent trade-intent ledger. Unknown broker outcomes are blocked
  until terminal truth is reconciled; async timeout alone can never trigger a
  duplicate retry.
- Added lossless 64-bit event deduplication and position-identifier based final
  close detection, with aggregate realized P/L applied once per position.
- Added live-book Hedge Zone reconciliation and explicit exclusive/cooperative
  per-engine concurrency contracts.
- Unified daily/session clock contracts, explicit DST policy, two-stage history
  readiness, account-wide start-balance reconstruction and cash-flow exclusion.
- Added cross-feature invariant validation and cross-project acceptance tests
  for trend, breakout, mean-reversion and generic recovery EAs.
- Removed silent external-fixture test passes and improved lint precision for
  tick-based spread guards, entry-delay policies, utility Trade classes and
  non-color hexadecimal masks.

### Verification

- 126 source regression tests pass before distribution rebuild.
- CCBSN remains a golden acceptance fixture only; no CCBSN/Bo.Botfx literals,
  command prices or defaults exist in production modules.
- Native MetaEditor compilation and MT5 Strategy Tester evidence remain required
  before any generated EA is release-eligible.

## [3.2.0rc3] - 2026-08-06

### Added
- Provenance-preserving `mql5-ir-configure` profile overlay between document intake and planning.
- Generic ontology and capability registry for advanced DCA, recovery, hedge-zone, exit, session and control engines.
- Composable source modules for grid risk, async execution, basket exits, persistent state, structured telemetry and MFE/MAE.
- Governance contracts and truthful evidence-v2 manifests bound to the canonical EA-IR hash.
- Phase 13 ship-candidate regression tests and CCBSN manual acceptance coverage.

### Changed
- Document manuals are treated as functional specifications; operational values require an explicit profile.
- Code generation fails before source emission when capability or configuration is unresolved.
- Advanced signal dispatch and exit handling are decomposed to reduce cyclomatic complexity.

### Security
- Retains strict path containment, atomic project generation and evidence/spec hash binding.

# Changelog

## [3.1.0rc2] - 2026-08-06

### EA-IR compiler and lossless build pipeline

- Replaced first-hit single-preset intake with canonical EA-IR 3.1 carrying
  requirement provenance, confidence, ambiguity and conflict states.
- Added Vietnamese EA ontology and context-aware signal/filter extraction.
- Added PDF/DOCX/text document intake with PDF page provenance.
- Added capability registry, operational-configuration gate and dependency-
  ordered build planner. Unsupported features now block instead of becoming
  metadata-only output.
- Added composable MQL5 generator with real order path for supported trend,
  breakout, mean-reversion, DCA, sizing, basket exit, standard hedge, same-
  chain sniper, filters, risk and control components.
- Added canonical IR SHA-256 binding across source, plan, traceability matrix
  and artifact manifest; added native evidence verifier rejecting evidence from
  a different IR.
- Added lossless guards for multi-symbol, multi-timeframe and unresolved
  multi-signal composition.
- Closed path traversal/arbitrary-output issues and made writes atomic.
- Fixed repo-root pytest imports and wheel metadata/selftest portability.
- Added phased regression suites and generic archetype stress tests; CCBSN is
  used only as one golden fixture, not as a framework template.

### Known limits

- Native MetaEditor compilation and MT5 Strategy Tester still require a Windows
  or trusted remote runner.
- Multi-symbol runtime, multi-timeframe runtime, signal AND/OR composition,
  Hedge Zone, cross-chain sniper and several advanced recovery policies remain
  explicitly unsupported and block code generation.

## [3.0.0-alpha.3] - 2026-08-02

### Security / release-gate hardening

- Added one canonical provenance validator shared by `check_all`, evidence
  attestation and release-manifest validation. File presence, fake EX5 bytes,
  imported logs, empty XML and Wine-only compile can no longer produce a
  release-eligible result.
- Added adversarial fake-evidence regression coverage and updated attestation
  fixtures to include source, command, tool version, host, timestamp and
  artifact hashes.
- Slim distribution now excludes tests, fixtures, evidence, Retro temp trees,
  `.bak` files and generated smoke state; removed the shipped ONNX stubs and
  stale `_p03_gate.py` helper.
- Corrected maintainer docs that claimed the source checkout had no fixtures or
  enforced a strict 200-LOC ceiling.

## [3.0.0-alpha.2] - 2026-08-01

### Added / fixed

- Executable conservative Retro checker registry for A1–A12, with
  `mql5-retro-init` and `vkmql-check retro-init` skeleton generation.
- Canonical Retro aliases (`RETRO-A1` … `RETRO-A12`) while retaining A-ID
  compatibility for existing contracts and evidence.
- Runtime Retro guide and skill references updated to the actual v3 schema.
- Regenerated 133-command catalog and v3 agent contract; fixed optional
  `markdown-it-py` import so catalog/module audits remain usable when the
  docs-render extra is not installed.
- Removed stale claims that the absent `docs/agent-prompts/` tree ships in the
  v3 package; historical v2.6 docs are explicitly compatibility material.

## [3.0.0-alpha.1] - 2026-08-01

### Added

- Agent-native `skill/vibecode-mql5` router with Lite, Standard and Full modes.
- Additive v3 governance fields for `EA-SPEC.yaml` and `DECISIONS.yaml`.
- AI-BUILD-CONTRACT v3 semantic-change policy and structured Retro A1–A12 guards.
- Hashed guard-evidence checker and forward/live approval binding.
- Explicit Windows/Wine, optional ONNX, internal MCP, local evidence and opt-in telemetry policies.
- Missing XML backtest parser compatibility functions required by existing quality gates.
- Regenerated command catalog and agent contract from `pyproject.toml`.

All notable changes to VibeCodeKit MQL5 EA are documented here. This project
adheres to semantic versioning.

## [2.6.2] - 2026-06-10

### Fixed (QA-stress-test hardening — behavior-preserving for real projects)
Addresses the two findings from the v2.6 deep-dive QA stress test. Both fixes
are guards that only change behavior on test/fixture trees and on empty input;
normal build/gate runs on real projects are unchanged. Suite remains 85/85.

- **`check_all`: release gate no longer writes into test/fixture trees, nor
  overwrites a previously recorded stress verdict.** The `stress` and
  `evidence` stages now detect fixture/audit paths (via the release-policy
  fixture-path rule) and prior `stress-matrix-report.json` results: when a
  directory is a fixture tree, the stages run read-only and report
  `UNTESTABLE` instead of regenerating artifacts; when a real prior stress
  report exists, its counts are preserved and graded worst-wins rather than
  overwritten. This prevents an audit run from mutating shipped fixtures
  (which previously could perturb the test suite).
- **`check_all`: contract-stage failures now print the exact fix.** When the
  `contract` stage FAILs for missing governance artifacts, the report appends
  a hint to run `vkmql-new spec <dir>` then `vkmql-new contract <dir>` and
  re-run the gate (a bare `build` does not emit contract artifacts).
- **`mql5-spec-from-prompt`: empty prompt is now honest.** A blank prompt
  emits a warning that it is producing a generic placeholder spec, and under
  `--strict` it refuses (exit 1) instead of silently emitting a degenerate
  spec.
- **Docs**: Quickstart and the English user guide now state explicitly that
  `build` / `auto-build` do not run the full release gate and do not emit the
  contract artifacts, with the scaffold-then-gate sequence spelled out.

## [2.6.1] - 2026-06-09

### Added (quality-gate hardening — fully additive, non-breaking)
Implements the quality-gate improvements recommended in the MQL5-references deep
research report. Every addition is backward-compatible: new release-policy
gate keys default neutral, new check-all stages are UNTESTABLE (not FAIL)
without evidence, and new static findings are advisory (warn/info) only — so
the original methodology workflow and all 74 prior tests are unchanged (suite
now 85/85).

- **`mql5-backtest-quality`** (`backtest_quality.py`): grades a parsed
  Strategy Tester report against two-tier (PASS/WARN) thresholds — profit
  factor, recovery factor, Sharpe, expected payoff, max-drawdown%, plus the
  balance-curve **R² = LRCorrelation²** linearity check and a transparent
  0–100 complex-criterion score. Too-few-trades → `INSUFFICIENT` (never PASS);
  a fixture report is `release_trusted=false` so green metrics alone can never
  make a build release-eligible.
- **composite OnTester template** (`fitness.py`): new `composite` fitness
  template (Korotky §6.5.6 multi-factor criterion) + `ea_has_ontester()`
  helper.
- **forward/OOS stage**: `check_all` gains a `forward` stage that runs the
  pre-existing `walkforward` evaluator when both IS+OOS reports are present
  (UNTESTABLE otherwise) and a neutral-default `forward_ok` release-policy key.
- **`mql5-mt5-python`** (`mt5_python_worker.py`): import-guarded
  MetaTrader5 live-environment evidence worker (`probe`/`capture`/`order-check`).
  Honest by construction: returns UNTESTABLE + exit 3 when the package or a
  live terminal is unavailable, and makes no Strategy-Tester claims.
- **`mql5-trade-hygiene`** (`trade_hygiene.py`): advisory static
  checklist for OrderCheck-before-send, volume/price normalization,
  freeze/stops level, retcode handling, margin-mode (netting vs hedging)
  awareness and OnTradeTransaction reconciliation, reusing the existing
  `mq5_graphs` lifecycle/basket/risk detectors. Advisory-only (warn/info) so
  it never flips the scan gate.
- **Release policy**: `compute_release_eligible` adds neutral-default
  `quality_ok` and `forward_ok` keys; `check_all` adds `quality`+`forward`
  stages and `vkmql-check` adds `quality`/`hygiene` subcommands.

### Fixed (post-update sync audit)
- Removed two dead imports (`json`, `math`) left in `backtest_quality.py`.
- Documented the three new CLIs (`mql5-backtest-quality`,
  `mql5-trade-hygiene`, `mql5-mt5-python`) in `docs/COMMANDS.md` (Verify
  section + total count corrected to 129).
- Refreshed the stale `v2.6.0` version string in
  `docs/CODEX-SETUP-PROMPT.md` to `v2.6.1`.

## [2.6.0] - 2026-06-08

### Fixed (deep-audit release/evidence honesty pass)
Closed five findings from the v2.6.0 deep audit so that "release-eligible" can
never be claimed without real evidence:

- **Evidence attestation hardened** (`evidence_attestation.create_release_attestation`)
  — `release_eligible=true` now requires a verified hash chain **and** every
  core evidence file present (compile-log, ea.ex5, backtest report,
  stress-matrix report, deep-review, evidence manifest) **and**
  `evidence/manifest.json` asserting `release_eligible: true`. A valid chain
  over absent files can no longer flip the flag; `attest --release-eligible`
  exits non-zero when evidence is incomplete.
- **`vkmql-check evidence` is now a release-evidence gate** — it verifies
  hash-chain validity, core-evidence presence, manifest validity, and
  release-eligibility consistency; a chain over absent evidence reports
  `INCOMPLETE` and exits 1 instead of printing a bare `OK` (no longer
  contradicts `vkmql-check all`).
- **Contract checker validates READY claims** (`contract_check`) — a README
  claiming LIVE/PRODUCTION/READY now FAILs unless `evidence/manifest.json`
  exists, sets `release_eligible: true`, and carries artifact hashes.
- **Recursive EA scan** (`check_all._stage_scan`) — scans every `Experts/**/*.mq5`
  (e.g. `Experts/MyEA/MyEA.mq5`), all files, and FAILs on any HIGH-risk flag.
- **Nested stress-matrix schema** (`stress_matrix_v2._load_matrix`) — accepts
  both `scenarios:` and PRD-nested `stress_matrix.scenarios:`; a malformed
  matrix file is a hard error instead of a silent fallback to defaults.

### Added (v2.6 BIG HARDENING)
See `docs/V26-BIG-HARDENING.md` for the full guide. This release makes an
AI-built EA provably done instead of merely *claimed* done — without ever
inventing a PASS (anything not locally observable stays `UNTESTABLE`, which
blocks release-eligibility).

- **EA-SPEC v2.6 schema** (`spec_schema_v26`) — stricter spec with required
  `risk` bounds (incl. `max_drawdown_pct`), `execution` and `validation`
  blocks; forbidden "ready" statuses are rejected.
- **AI-BUILD-CONTRACT** (`ai_build_contract`, `mql5-ai-build-contract`) —
  generated edit/claim/evidence guard-rail (`.md` + `.json`); `evidence/` and
  `release/` are always forbidden paths.
- **Completion Report parser** (`completion_report_parser`,
  `mql5-completion-report-parse`) — deterministic, no-LLM parser; a `DONE`
  report with no test evidence is rejected.
- **TIP state machine** (`tip_state`, `mql5-tip-state`) — strict
  `planned→assigned→reported→verified→accepted` lifecycle; `DONE` never
  auto-accepts. TIPs now carry `allowed_paths`, `forbidden_paths`,
  `acceptance_commands`, `evidence_required`, `rollback_plan` (PRD §8).
- **Stress matrix v2** (`stress_matrix_v2`, `mql5-stress-matrix`) — eight
  broker-condition scenarios; `UNTESTABLE` (never `PASS`) without a live broker.
- **Evidence attestation** (`evidence_attestation`, `mql5-evidence-attestation`)
  — tamper-evident SHA-256 hash chain; any post-seal change fails verification.
- **Aggregate gate** (`check_all`, `vkmql-check all`) — runs every stage and
  prints one honest verdict; the verdict is idempotent across runs.
- **Agent CLI** (`agent_cli`, `vkmql-agent`) — `export-context`, `next-tip`,
  `ingest-report`, `status`, `repair-loop`.
- **v2.6 risk signals in `scan_ea`** — detects `raw-ordersend`, `ctrade`,
  `event-handler`, `hardcoded-symbol`, `hardcoded-timeframe`, `risk-input`.
- **Tests** — 39 new `unittest` cases (`tests/test_v26_*.py`) covering every
  new module with pass + fail cases, plus golden-fixture classification, and the
  deep-audit hardening adds 5 more suites (evidence attestation, check-evidence
  gate, ready-claim validation, recursive scan, nested stress matrix). The
  commercial-clean bundle includes **74 runnable tests** in total. Run from the
  repo root with `pytest -q` (a `pythonpath = ["scripts"]`
  entry in `pyproject.toml` means `PYTHONPATH=scripts` is no longer required)
  or `python3 -m unittest discover -s tests`.
- **Golden fixtures** (`tests/fixtures/v26/`) — 1 PASS + 4 FAIL project
  fixtures (`simple_valid`, `missing_risk`, `fake_ready_claim`, `stress_fail`,
  `release_eligible`) consumed by `test_v26_fixtures.py`.
- **Docs** — `docs/V26-BIG-HARDENING.md`, `docs/AI-BUILD-CONTRACT.md`,
  `docs/RELEASE-POLICY.md`, refreshed `docs/COMMANDS.md` (128 tools), and the
  `templates/AI-BUILD-CONTRACT.md.tmpl` field-layout reference.

### Changed
- **`release_policy.compute_release_eligible`** — THE canonical predicate now
  also honours `stress_ok` and `hash_chain_ok` gate keys (PRD §9). Both default
  to the neutral `True` so pre-v2.6 callers are unaffected. `check_all` routes
  its final verdict through this single predicate.
- **`vkmql-check all --require-release`** — new CI release mode. Without the
  flag the gate is "ok" when no stage FAILs (UNTESTABLE tolerated for audit);
  with the flag the command exits non-zero unless the build is genuinely
  `release_eligible`, so an UNTESTABLE stage fails CI release pipelines.

### Notes / known limitations
- **Stress matrix is an honest *simulated* gate.** It never fabricates a PASS:
  scenarios that cannot be proven locally are reported `UNTESTABLE`, which
  blocks release-eligibility. Real harsh stress (PASS/FAIL from a live MT5
  Strategy Tester or broker simulation) requires a real MT5 worker; wiring that
  worker is deferred to a later release (`remote_worker_client` stays at the
  protocol level in v2.6 per PRD §10).
- **Version bumped to 2.6.0** across `pyproject.toml`, `_version.py`, both tool
  catalogs and both `agent-contract.json` copies (`version_triple_match`
  selftest invariant passes).

## [2.5.2] - 2026-06-07

### Fixed (commercial bundle audit / trust)
- **Stale repo-root `agent-contract.json`** — the repo-root `agent-contract.json` still declared `kit.version` `2.4.4` while pyproject, both tool catalogs and the package-internal contract had been bumped. A bundle auditor (or enterprise buyer) inspecting the zip would see a version mismatch. The root contract is now synced to the current kit version.

### Changed
- **`version_triple_match` selftest invariant hardened** — it now additionally requires that **every** shipped `agent-contract.json` (`kit.version`) matches pyproject, not just the pyproject/`_version`/catalog triple. Prevents any future agent-contract drift from shipping silently.

## [2.5.1] - 2026-06-07

### Fixed (third-party QA review of v2.5.0)
- **#3 Doc claim verifier over-claiming (most serious)** — `ea_doc_claims.py` now blanks comments + string/char literals and skips `#include` lines before matching (`find_evidence(..., code_only=True)`), and the *weak* capability claims (`news_filter`, `spread_filter`, `ml_filter`) must be evidenced in the EA **entrypoint** (`.mq5`), not merely by a bundled-but-unwired library header. Patterns tightened to real API/usage anchors (`OnnxRun`, `SYMBOL_SPREAD`, `CalendarValueHistory`, …). Eliminates false "supported" from comments and unused includes while preserving genuine wiring detection.
- **#1 Spec parser silently dropping requirements** — `spec_from_prompt`: the daily-loss recogniser now tolerates intervening words (`limit`/`of`/`percent`…); "max N (grid) levels" maps onto `max_open_positions`; multi-symbol prompts keep a primary symbol but **surface** the full requested set as a warning (stderr / `PromptParseResult.warnings`) instead of dropping it.
- **Grid risk false-positive** — `mq5_graphs._LEVEL_CAP` now recognises input-named caps such as `InpMaxGridLevels`, so a real hard cap no longer produces a spurious "Lot scaling without a hard cap" critical.
- **#4 Senior-review noise** — `ea_senior_review.code_quality_issues` suppresses unused-function/input/include findings inside reusable library headers (`.mqh`) and reports a `suppressed_library_findings` count, so toolkit helpers no longer bury real findings.

### Added
- `tests/test_qa_review_fixes.py` — 14 regression tests covering all four fixes (81 tests total, all green).

### Notes
- **#5 (no real compile)** and **#2 (placeholder signal logic in scaffolds)** are by-design and remain honestly labeled: releases stay gate-blocked without MetaEditor/MT5 evidence, and scaffolds ship clearly-marked logic stubs.

## [2.5.0] - 2026-06-07

### Added
- **Hardening v2.5** — a quality pass (no new product features) closing the six gaps from the v2.4.4 review:
  - **#1 Golden happy path e2e** (`tests/test_golden_path_e2e.py`): drives `vkmql new (from-prompt + build) → check (lint) → ship docs → ship release` end-to-end and asserts the pipeline honestly refuses to mark a build release-eligible when no MetaEditor compile / MT5 backtest evidence exists (no faked PASS).
  - **#2 Buggy-EA corpus + reviewer assertions** (`tests/test_bug_corpus.py`, `tests/fixtures/buggy/`): 8 deliberately broken EAs (martingale-no-cap, no-SL, async-without-OnTradeTransaction, wrong pip normalization, netting/hedging basket-close-without-magic, unused risk input, raw `OrderSend`, plus a clean control) with assertions that each defect is caught and that forged evidence / async over-claims are rejected.
  - **#3 Preset integration tests** (`tests/test_preset_integration.py`): clean builds across trend, grid, dca, breakout, scalping, portfolio-basket, ml-onnx, service-llm-bridge, wizard-composable, plus the existing-EA scan path.
  - **#4 Public command surface** (`surface.py`): the end-user surface is now exactly 5 public commands (`vkmql-new`, `vkmql-check`, `vkmql-ship`, `mql5-ea-deep-review`, `mql5-doctor`); everything else is tiered internal/advanced. Manifest tools now carry a `tier` field.
  - **#5 Maturity labels** (`maturity.py`): every catalog tool is labelled `release-grade` / `scaffold` / `placeholder`; manifest tools now carry a `maturity` field, and no public command is a placeholder.
  - **#6 Structured-graph scanner** (`mq5_graphs.py`): regex heuristics upgraded to call-graph, input-usage, order-lifecycle, risk-invariant, and basket-integrity graphs; wired into `scan-ea --graph` and `mql5-ea-deep-review` (additive, advisory).
- Two new selftest checks (`public_surface_stable`, `maturity_labeled`); selftest now 10/10.
- Test suite grew from 38 → 67 unit tests.

## [2.4.4] - 2026-06-07

### Fixed
- Documentation audit hardening after the 2.4.3 Vietnamese consolidation: repaired all dangling intra-doc links. The removed Vietnamese guides (`QUICKSTART.vi.md`, `USAGE-vi.md`, `USER-GUIDE-vi.md`, `ENV-SETUP-vi.md`) and the never-shipped `devin-chat-driven-build.md` were still cross-referenced from `QUICKSTART.md`, `USAGE-en.md`, `USER-GUIDE-en.md`, and `mcp/vibecodekit-bridge/README.md`; these now point at the single master guide `docs/HUONG-DAN-TOAN-TAP-vi.md` (with section anchors) or were de-linked. Broken-link sweep is now 0.
- Removed pre-existing dead links unrelated to the consolidation: `docs/agent-prompts/*.md` (7 links in `COMMANDS.md`), `references/59-trader-checklist.md`, `reference-ea/REPORT.md`, and `PLAN-v5.md` were de-linked to plain references since those targets are not shipped.
- Corrected stale facts in the retained English guides: version `v2.0.0` → `v2.4.3`, command count `69` → `118` (heading + TOC anchor kept in sync), and the obsolete `1494 tests / 4 skipped` baseline → the real shipped `38 unit tests + selftest 8/8`.

### Changed
- `selftest.py` `_USER_DOC_NAMES` now lists the actual shipped user docs (`COMMANDS.md`, `QUICKSTART.md`, `USAGE-en.md`, `USER-GUIDE-en.md`, `HUONG-DAN-TOAN-TAP-vi.md`), so the `no_dev_refs_in_user_docs` invariant actively scans the new master guide instead of skipping deleted filenames.
- No command-surface or runtime-logic change: the registered command set is unchanged (118 tools). Removing the Vietnamese guides does not affect tool structure or function — no runtime code opened any of them; 38/38 unit tests and 8/8 selftest invariants remain green.

## [2.4.3] - 2026-06-07

### Changed
- Documentation consolidation: merged all Vietnamese end-user guides into a single comprehensive document `docs/HUONG-DAN-TOAN-TAP-vi.md` so a user only needs to open one file to learn the entire tool (latest version). Covers install/env, quickstart, the 8-step build philosophy + 3 modes, step-by-step EA build, `ea-spec.yaml` (8 blocks), one-command deep-review (Stage 0→7), the Owner→Contractor→Builder contract workflow, remote worker, EA DOCX docgen, RRI/review lenses, MCP/IDE integration, anti-patterns + Trader-17 + quality matrix, the no-fake-PASS evidence policy, the full command catalog by group, VPS deploy, and troubleshooting.
- Removed the now-redundant Vietnamese guide files (`QUICKSTART.vi.md`, `USER-GUIDE-vi.md`, `USAGE-vi.md`, `HUONG-DAN-BUILD-EA-STEP-BY-STEP-vi.md`, `ENV-SETUP-vi.md`, `CONTRACT-BUILD-PIPELINE-vi.md`, `EA-DOCX-DOCGEN-vi.md`, `REMOTE-WORKER-READY-vi.md`, `VALIDATION-POLICY-vi.md`) and the stale root `LLM-FOCUSED-NOTES-vi.md`, to avoid documentation clutter for end users.
- Rewrote `docs/README.md` (doc map) and the root `README.md` Vietnamese sections to point at the single master guide. English references (`COMMANDS.md`, `QUICKSTART.md`, `USAGE-en.md`, `USER-GUIDE-en.md`, `anti-patterns-AVOID.md`, `MIGRATE-VPS.md`) are retained.
- No command-surface change: the registered command set is unchanged; this is a docs-only consolidation. The doc avoids dev-only reference patterns so the `no_dev_refs_in_user_docs` selftest stays green.

## [2.4.2] - 2026-06-07

### Fixed
- QA sync pass before release. Regenerated `agent-contract.json` whose `kit.version` was stale at 2.3.1 (now tracks the kit version).
- Removed references to commands that are not registered console-scripts in the current surface: corrected the `mql5-overfit_check` typo to `mql5-overfit-check` (USAGE-vi); replaced the bare `mql5-rri-matrix --collect` with the canonical `python -m vibecodekit_mql5.rri.matrix --collect` (USAGE-en, USAGE-vi, and `_agent_io.py` help text/comment); removed the non-existent `mql5-rri-template` alias from USER-GUIDE-vi so the alias list matches the stated count of 8.
- No command-surface change: the 118-command set is unchanged; only docs/metadata were synced.

## [2.4.1] - 2026-06-07

### Fixed
- Code-hygiene audit of the v2.4 modules: removed 5 unused imports (`build_symbol_graph` in `deep_review`, `FunctionInfo`/`strip_comments_and_strings` in `line_review`, `EVENT_HANDLERS` in `structure_audit`, `Iterable` in `mq5_symbols`) plus a dead `_GLOBAL_DECL` regex.
- Removed a dead branch in `deep_review._resolve_files` (`... if False else _read(...)`) that obscured the single-file read path.
- CHANGELOG: added the missing 2.4.0 entry.

### Added
- Wired the `modernize` matrix/vector advisor (`_MATRIX_HINT`): manual element-wise numeric loops now emit an INFO hint suggesting MQL5 matrix/vector types (build 3620+).

## [2.4.0] - 2026-06-07

### Added
- **One-command deep review** `mql5-ea-deep-review` (alias `mql5-ea-audit`) orchestrating Stages 0–7 into one unified Markdown + JSON + DOCX report; prompt-trigger wired in `AGENTS.md`.
- Internal pipeline stages (no new CLI surface): `mq5_symbols` (symbol-graph), `structure_audit` (LOC/complexity/nesting/hot-path/duplicate), `deadcode` (unused func/input/include, unreachable, dead branch), `line_review` (grounded LLM packets + MQL5-2026 rubric), `modernize` advisor, and `code_quality` folding into senior-review.
- Flags `--fast`, `--no-docx`, `--json-only`, `--profile`.

## [2.3.0] - 2026-06-07
## [2.3.1] - 2026-06-07

### Fixed
- **CRITICAL**: UTF-16/UTF-16-LE encoding parser bug in `scan_ea.py` and `ea_doc_analyzer.py` — now use `read_mq5_text` helper for all `.mq5/.mqh` files
- scan-ea no longer misreports UTF-16 EAs as 0 behaviours / trend-follow
- docgen/senior-review/chat-workflow now correctly parse inputs from UTF-16 sources

### Added
- P1.1: Detect dangerous Sleep(>10000ms) in OnTick
- P1.2: Detect expiry/name-lock/account-lock in EA source
- P1.3: Detect basket close/profit operations without magic filter
- P1.4: Detect PositionGetSymbol + Magic() without SelectByIndex (stale object risk)



Hardening release (no new features). Fixes correctness defects raised in
external review and locks them in with a runnable regression suite.

### Fixed

- **Doc-verify generic profile**: a generic EA no longer inherits grid-only
  required claims. `verify_docs` now defaults to the `generic` profile (which
  requires no profile-specific claims), and an unknown profile falls back to
  `generic` instead of silently enforcing `grid-safe`.
- **Senior-review evidence scoring**: missing compile/backtest evidence is now a
  hard release blocker. A bare EA with no `evidence/manifest.json` scores as
  `release-blocked` with separate "No compile evidence" / "No backtest evidence"
  criticals; only positive proof (`compile_ok`/`backtest_ok` true) clears them.
  Absence is never treated as success.
- **auto-llm-review output contract**: stdout is now exactly one JSON document.
  Internal docgen/doc-verify sub-steps no longer leak their own JSON to stdout,
  the human-readable summary moved to stderr, and a `--json-only`/`--quiet`
  flag suppresses it entirely for machine consumers.

### Added

- **Regression suite** under `tests/` (runnable with `python -m unittest`, no
  pytest required) covering the generic/unknown/grid-safe doc-verify profiles,
  the senior-review evidence gate, and the output contract. `testpaths` now
  points at this real directory.

## [2.2.0] - 2026-06-07

Final "ready for all users" release. Hardens packaging, makes the release
predicate single-sourced, adds a glanceable golden-flow status surface, and
introduces a commercial hand-off bundle.

### Added
- **`vkmql-check status`** (`golden_flow`): renders the full
  `BUILD -> COMPILE -> BACKTEST -> GATE -> RELEASE` flow from the canonical
  evidence manifest plus a single `Next action:` line. Reads
  `release_eligible` verbatim; never recomputes eligibility.
- **`vkmql-check status --html report.html`**: self-contained HTML dashboard
  (no external CSS/JS) for sharing or publishing build status.
- **`mql5-dist --flavor {slim,full,commercial}`**: the new `commercial`
  profile ships the slim runtime surface (no tests/CI/maintainer docs) plus a
  generated 3-command `QUICKSTART-COMMERCIAL.md`, hashed in the manifest and
  byte-stable across rebuilds.
- Two new selftest invariants: `docs_assets_resolvable` and
  `no_dev_refs_in_user_docs` (8 invariants total).
- Build accepts `--out-dir` / `--workspace` as aliases for `--out`.
- Persona-tiered quick reference at the top of `docs/COMMANDS.md`.

### Changed
- **Canonical release predicate**: `release_policy.compute_release_eligible`
  is now the single source of truth; both v1 `summarize` and v2 `evaluate`
  route through it (no divergent eligibility logic).
- `ea_docs_assets` is now declared in package-data so the docs renderer works
  from an installed wheel (P0 packaging fix).
- Compile/test/role-guard subprocesses now enforce timeouts and surface
  `timed_out` instead of hanging.
- MQL5 headers hardened: opt-in magic filtering (`CRiskGuard`), atomic magic
  reservation (`CMagicRegistry`), stops-level/lot validation (`CSafeTradeManager`).
- Repair output renamed `compile-repair-report.json` -> `repair-attempt.json`
  (a back-compat copy under the old name is kept for one minor release).
- User docs no longer reference git clone / git tag workflows.

## [2.1.5]
- Previous baseline release.
