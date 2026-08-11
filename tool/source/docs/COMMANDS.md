---
id: commands
title: Command catalog (139 commands)
---

# Command catalog

All commands callable directly via `python -m vibecodekit_mql5.<name>`.
No master `/mql5` router — every command stands alone.

## EA-IR compiler commands (introduced in v3.1 RC2; current in RC6)

| Command | Purpose |
| --- | --- |
| `mql5-ea-intake-ir` | Compile prompt or text requirements into canonical EA-IR 3.1. |
| `mql5-doc-intake-ir` | Extract PDF/DOCX/text and compile it to page-referenced EA-IR. |
| `mql5-ir-build` | Capability-plan and generate a composable MQL5 project from EA-IR. |
| `mql5-ir-verify` | Verify IR/source/manifest binding and optional native compile/tester evidence. |

## v3 governance commands

| Command | Purpose |
| --- | --- |
| `vkmql-new spec` | Write a v3-compatible `EA-SPEC.yaml` with mode, release and semantic-policy defaults. |
| `vkmql-new contract` | Generate AI-BUILD-CONTRACT, Decision Ledger and risk/broker/evidence contracts. |
| `vkmql-check decisions` | Validate `DECISIONS.yaml`. |
| `mql5-retro-init` / `vkmql-check retro-init` | Create a conservative `UNTESTABLE` Retro evidence skeleton. |
| `vkmql-check retro` | Verify machine-readable Retro Guard evidence and hashed guard artefacts. |
| `mql5-release-approve` | Bind forward/live approval to exact build and evidence hashes. |

## v2.6 compatibility commands

See `docs/V26-BIG-HARDENING.md` for the full guide.

| Command | Purpose |
| --- | --- |
| `vkmql-new spec` | Write an additive v3 `EA-SPEC.yaml` (v2.6 documents remain readable). |
| `vkmql-new contract` | Generate AI-BUILD-CONTRACT + risk/broker/evidence contracts. |
| `vkmql-new tip-graph` | Emit `TASK-GRAPH.yaml` + `TIP-STATE.json`. |
| `vkmql-check contract` | Validate the project AI-BUILD-CONTRACT. |
| `vkmql-check stress` | Run the broker stress matrix. |
| `vkmql-check evidence` | Release-evidence gate: verifies the hash chain **and** core-evidence presence, manifest validity, and release-eligible consistency. Prints `INCOMPLETE` + lists missing evidence + exits non-zero when core evidence is absent — never a bare `OK`. |
| `vkmql-check all` | Run every gate and print one honest verdict (exit 0 unless a stage FAILs). |
| `vkmql-check all --require-release` | CI release mode: exit non-zero unless the build is release-eligible (UNTESTABLE blocks). |
| `vkmql-agent <verb>` | Drive the TIP build loop (export-context / next-tip / ingest-report / status / repair-loop). |
| `mql5-ai-build-contract` | Generate/validate AI-BUILD-CONTRACT standalone. |
| `mql5-completion-report-parse` | Parse + validate a Completion Report (no LLM). |
| `mql5-tip-state` | Inspect / initialise the TIP state machine. |
| `mql5-stress-matrix` | Run the stress matrix standalone. |
| `mql5-evidence-attestation` | Build / verify / attest evidence (hash chain). |
| `mql5-check-all` | Aggregate gate (alias of `vkmql-check all`). |

## By persona (start here)

Most users only need the five commands in their lane. The full catalog below
is the reference; this table is the fast path.

| Persona | You want to… | Core commands |
| --- | --- | --- |
| **EA buyer / operator** | Unzip and get a verified build, no MQL5 knowledge | `selftest` → `build` → `golden_flow` → `vkmql-ship release` |
| **EA builder / quant** | Author, compile, backtest and gate a strategy | `vkmql-new build`, `vkmql-check compile`, `vkmql-check test`, `vkmql-check audit`, `vkmql-check status` |
| **Reviewer / lead** | Judge a build without re-running it | `vkmql-check status [--html report.html]`, `mql5-review --lens {eng,ceo,cso}`, `mql5-rri --collect`, `mql5-audit` |
| **Maintainer / release** | Ship a signed, reproducible bundle | `mql5-dist --flavor {slim,full,commercial}`, `vkmql-ship release`, `mql5-agent-contract --emit` |

> The golden flow is always `BUILD → COMPILE → BACKTEST → GATE → RELEASE`.
> Run `vkmql-check status` at any point to see where a build stands and the
> single next command to run.

The remaining sections document every command in full for reference.

**(v1.1) consolidated 10 commands into 2 umbrellas**:

* The five review CLIs (`mql5-review`, `mql5-eng-review`, `mql5-ceo-review`,
  `mql5-cso`, `mql5-investigate`) now share `mql5-review`'s umbrella — pick
  a preset via `--lens {eng,ceo,cso,investigate}`. The four lens-named
  console scripts remain as 1-line aliases so existing operator habits
  keep working.
* The four RRI CLIs (`mql5-rri`, `mql5-rri-bt`, `mql5-rri-rr`,
  `mql5-rri-chart`) now share `mql5-rri`'s umbrella — pick a matrix
  flavour via subcommand `mql5-rri {template,bt,rr,chart}`. The three
  matrix-named console scripts remain as 1-line aliases.

The canonical command catalog is generated from `pyproject.toml` by
`mql5-manifest --emit`. The v3.3.0rc6 baseline contains 139 public entry
points, including compatibility aliases. The high-level supported
surface remains the `vkmql-new`, `vkmql-check`, and `vkmql-ship` umbrellas;
the catalog count is not a recommendation to memorise every command. Every
alias must resolve to its declared entry point. `.A/B/C` consolidated
the *implementation* of `mql5-review` / `mql5-rri`, not the surface.
.D adds an opt-in `mql5-lint --use-ast` flag (no new CLI) that
routes AP-1 / AP-2 / AP-7 through a lightweight MQL5 AST scanner under
`scripts/vibecodekit_mql5/ast_parser/` — byte-identical to the regex
pipeline on the 20-EA + 23-scaffold golden corpus, regex remains the
default. .E adds the new `mql5-bt-sim` in-process tick-bar
simulator.

## Agent contracts 

Twelve gates accept a standardised `--json` flag that emits a stable
envelope (`schema_version=1`) on stdout instead of pretty text — see
`scripts/vibecodekit_mql5/_agent_io.py`. The same gates also accept
`--gate-report <path>` to additionally write the envelope to disk; the
matrix collector picks them up:

```bash
mql5-lint EA.mq5 --json
mql5-lint EA.mq5 --format sarif # SARIF 2.1.0
mql5-walkforward is.xml oos.xml --gate-report gate-report-wf.json
python -m vibecodekit_mql5.rri.matrix --collect ./reports/ --output matrix.html
python -m vibecodekit_mql5.rri.matrix --audit # cell-coverage audit
```

The matrix collector recognises **6 discriminative cells** (one per
(dim, axis) pair) — see [USAGE-en §3.5 → Matrix cell-coverage audit
](USAGE-en.md#matrix-cell-coverage-audit-) for the
full coverage table and the new `passes_personal_gate_only` /
`passes_enterprise_gate_only` envelope fields.

Tools with `--json`: `mql5-lint`, `mql5-trader-check`, `mql5-broker-safety`,
`mql5-permission`, `mql5-backtest`, `mql5-walkforward`, `mql5-monte-carlo`,
`mql5-multibroker`, `mql5-overfit-check`, `mql5-mfe-mae`, `mql5-doctor`,
`mql5-audit`, `mql5-fixture`, `mql5-init`, `mql5-forge-loop`, `mql5-bt-sim`,
`mql5-vision-gen`, `mql5-blueprint-gen`, `mql5-tip-gen` (generators
emit the envelope but intentionally OMIT `matrix_dim/axis` — they are
emitters, not gate-report tools),
`mql5-contract-gen`, `mql5-verify-report` (same envelope-only
rationale; the contract / verify-report are emitters consumed by the
layer-5 sign-off sentinel rather than direct matrix inputs),
`mql5-task-graph-gen`, `mql5-completion-report` (task-graph
expands a signed contract into a per-TIP DAG; completion-report
emits a per-TIP STATUS / Files / Tests / Issues / Gate Reports
rollup. Both are emitters; both deliberately OMIT `matrix_dim/axis`),
`mql5-escalation` (actor-to-actor escalation audit log
emitter; raise / list / resolve records under `.mql5-audit/escalations.jsonl`;
intentionally OMITs `matrix_dim/axis` because the layer-5 hook is the
gate-side consumer).

Tools with `--format sarif`: `mql5-lint`, `mql5-method-hiding-check`.

`mql5-manifest` is the discovery tool itself — it has its own
`--emit` / `--validate` surface and does NOT participate in the
`--json` envelope contract. `mql5-compile` carries a *legacy*
`--json` flag (emits `CompileResult` directly, not the envelope) and is therefore also kept out of the table above.

Run `mql5-manifest --emit > manifest.json` for a machine-readable
catalogue of every command (capability flags + module path).

## Draft mode 

Four gates accept the new `--draft` flag, which downgrades errors to
non-blocking warnings and forces exit 0 — useful inside the
chat-driven build loop where the EA is still half-written:

```bash
mql5-lint EA.mq5 --draft
mql5-trader-check EA.mq5 --draft
mql5-permission --mode personal EA.mq5 --draft
mql5-auto-build --spec ea-spec.yaml --draft # implies --no-compile --no-gate --no-docs
```

The JSON envelope still records the original verdict under
`data.original_ok` so downstream tooling can see what would have
blocked in non-draft mode. Draft is distinct from `--soft` (used by
`mql5-doctor` to relax *environment* probes); both flags can coexist.

## Discovery (5)
- `/mql5-scan` — survey project tree, classify artefacts
- `/mql5-survey` — match free-text strategy → scaffold archetype
- `/mql5-doctor` — installation + environment health check (use `--soft` for docs/lint-only CI without Wine: Wine/MetaEditor/terminal probes become warnings, exit 0)
- `/mql5-audit` — run 70-test conformance battery
- `/mql5-init` — interactive 5-question bootstrap wizard → `ea-spec.yaml` . Use `--non-interactive` / `--from-answers <yaml>` in CI.

## Plan (10)
- `/mql5-rri` — open Step 2 RRI template
- `/mql5-vision` — open Step 3 VISION template
- `/mql5-blueprint` — open Step 4 BLUEPRINT template
- `/mql5-tip` — open Step 5 TIP template
- `/mql5-vision-gen <step-2-rri.md>` — ****: auto-emit `step-3-vision.md` from a filled RRI artefact. Parses `## Constraints` + `- [x] persona::q-id` lines, fills Scope / Active personas, leaves Timeline + Risk register as `TODO`. Supports `--json` + `--gate-report`.
- `/mql5-blueprint-gen <ea-spec.yaml>` — ****: auto-emit `step-4-blueprint.md` from `ea-spec.yaml` (preset-keyed invariants + module diagram + state machine). Optional `--vision <step-3-vision.md>` fuses scope.
- `/mql5-tip-gen <step-4-blueprint.md>` — ****: auto-emit `step-5-tip.md` (module table + invariant → module × test coverage). Test names are pytest-compatible snake_case identifiers.
- `/mql5-contract-gen <step-4-blueprint.md> --ea-spec ea-spec.yaml --out contract.md`
  — ****: emit a homeowner-facing contract from an APPROVED blueprint + EA spec. Output has 6 sections (DELIVERABLES, EXCLUSIONS, TECH STACK, INVARIANTS, TASK GRAPH SUMMARY, ACCEPTANCE OVERVIEW) + a `## CONFIRM` block the Homeowner must complete with `CONFIRM by <name> at <YYYY-MM-DD>`. Deterministic per preset/stack; supports `--json` + `--gate-report`.
- `/mql5-verify-report --gate-reports <dir> [--blueprint step-4-blueprint.md] [--tip-dir tasks/] [--completion-dir completions/] --out verify-report.md`
  — ****: aggregate gate-report envelopes into a single Markdown report. Derives `OVERALL STATUS = READY | NEEDS_FIXES | MAJOR_ISSUES`, splits gates into Tech Health / Scenario Results / Other, surfaces every FAIL, and (when blueprint+TIP dir supplied) emits an invariant↔TIP coverage table. Renders the four-choice REFINE menu so the Contractor LLM can copy-paste decisions to the Homeowner.
- `/mql5-permission-layer5 --enforce-sign-off [--blueprint step-4-blueprint.md] [--contract contract.md]`
  — ****: standalone audit of the homeowner sign-off lines (`APPROVED by …` on blueprint, `CONFIRM by …` on contract). Personal mode requires only the blueprint line; team/enterprise require both. Composes with `--enforce-activities` so a single command can verify activities + sign-off in one shot.
- `/mql5-task-graph-gen <contract.md> [--out-dir <dir>] [--force]`
  — ****: expand a signed contract into a per-TIP dependency DAG. Emits `tasks/TIP-001..N.md` (YAML frontmatter + `## Goal` / `## Acceptance criteria` / `## Dependencies` / `## Completion` sections) plus `task-graph.md` (Mermaid `graph TD` + index table). Dependencies are resolved structurally via a keyword classifier; cross-links contract invariants into each TIP. Deterministic. Standard `--json` + `--gate-report`.
- `/mql5-completion-report --tip tasks/TIP-NNN.md [--gate-reports <dir>] [--file <p>]... [--test <p>]... [--issue <text>]... [--out completion-NNN.md]`
  — ****: per-TIP Completion Report for the Builder. Aggregates gate-report envelopes into a Markdown table, accepts repeated `--file` / `--test` / `--issue` flags, derives `STATUS = READY | IN_PROGRESS | BLOCKED` (BLOCKED on any FAIL or any `--issue`; READY when every envelope is PASS; otherwise IN_PROGRESS), and exits 1 only when BLOCKED. The Contractor's `mql5-verify-report --completion-dir` picks the resulting files up.
- `/mql5-escalation --from {chu-nha,chu-thau,tho-thi-cong} --to {chu-nha,chu-thau,tho-thi-cong} --level {1,2,3} --reason <text> [--artefact <path>]`
  — ****: actor-to-actor escalation audit log. Appends a record to `.mql5-audit/escalations.jsonl` (override with `--audit-log <path>`) with a deterministic `ESC-YYYYMMDD-NNN` id. Level 1 = note, Level 2 = warning, Level 3 = hard block. `--list [--status {OPEN,RESOLVED,ALL}] [--level <N>]` queries the log; `--resolve <id> --resolved-by <actor> [--note <text>]` closes one. `mql5-permission-layer5 --enforce-no-open-escalation` fails TEAM / ENTERPRISE gates while any level-3 record stays OPEN; personal mode reports the count without failing.

## Build (15)
- `/mql5-build` — render a scaffold
- `/mql5-auto-build` — single-shot spec → scan → build → lint → compile → gate → dashboard → docs
- `/mql5-auto-fix` — close 8 critical anti-patterns automatically
- `/mql5-spec-from-prompt` — free-text description → canonical `EA-IR.json`; use `--legacy` only for the non-release single-preset YAML compatibility view
- `/mql5-dashboard` — render + publish the quality-matrix HTML
- `/mql5-docs-bundle` — emit `docs-context.json` + `docs-prompt.md` so an external LLM agent can author the EA user-guide markdown (Pattern A — kit-light `.docx` ship). Bundles spec + parsed inputs (semantic-library enriched) + scaffold FLOW + build/lint metrics. Auto-runs inside `mql5-auto-build`.
- `/mql5-docs-assemble` — convert the LLM-authored `guide.md` → Word `<EA>.docs.docx` (embedded images from `images/`, F9-refreshable ToC, Vietnamese diacritics). Auto-runs inside `mql5-auto-build` when `guide.md` is present in the build dir.
- `/mql5-wizard` — render the wizard-composable scaffold
- `/mql5-pip-normalize` — patch a .mq5 to use `CPipNormalizer`
- `/mql5-async-build` — render the hft-async scaffold
- `/mql5-onnx-export` — PyTorch/TF → ONNX (opset ≥ 14)
- `/mql5-onnx-embed` — embed an `.onnx` into an `.mq5` via `#resource`
- `/mql5-llm-context` — wire an LLM bridge into an existing EA
- `/mql5-forge-init` — initialise an Algo Forge repo

## Verify (16)
- `/mql5-compile` — MetaEditor build (Wine on Linux)
- `/mql5-lint` — 8 critical anti-pattern detectors. Add **`--use-ast`** (.D POC) to route AP-1 / AP-2 / AP-7 through the lightweight MQL5 AST scanner instead of the regex detector. Byte-identical findings vs the regex pipeline on the 20-EA + 23-scaffold golden corpus. Regex remains the default.
- `/mql5-method-hiding-check` — build-aware method-hiding detector (ERROR on build ≥ 5260, WARN below)
- `/mql5-backtest` — parse Strategy Tester XML → 14 metrics JSON (you run the tester)
- `/mql5-tester-run` — drive `terminal64.exe` (Wine or native) with a rendered `tester.ini` and parse the XML end-to-end
- `/mql5-optimize-run` — drive `terminal64.exe` in optimization mode (slow/genetic), parse the SpreadsheetML report into top-N parameter sets (`--from-xml` for hermetic CI)
- `/mql5-walkforward` — IS/OOS Sharpe correlation (takes 2 positional XML reports)
- `/mql5-monte-carlo` — bootstrap DD from returns CSV (positional `returns_csv --reported-dd ...`)
- `/mql5-overfit-check` — OOS/IS Sharpe sanity (takes 2 positional XML reports)
- `/mql5-multibroker` — N-broker stability orchestrator (`--reports a.xml,b.xml,c.xml`)
- `/mql5-fitness` — OnTester custom fitness template (positional name; omit to list)
- `/mql5-mfe-mae` — per-trade MFE/MAE CSV analyser (8-col schema; see USAGE)
- `/mql5-bt-sim` — **.E**: deterministic Python tick-bar simulator. Generates synthetic OHLC bars under a seed, runs a built-in strategy (`--strategy sma-cross|mean-rev|breakout|random`), emits XML in the MT5 Strategy Tester schema. The `mql5-backtest` parser ingests the file unchanged → chain `mql5-bt-sim --out tester.xml && mql5-backtest --report tester.xml --json` for hermetic CI without Wine.
- `/mql5-backtest-quality` — grade a Strategy Tester XML against PF/RF/Sharpe/R²/MaxDD thresholds → PASS/WARN/FAIL/INSUFFICIENT verdict (worst-tier metric; `<min_trades` → INSUFFICIENT). Advisory inside `vkmql-check all`; blocks release only under `--require-release`. Supports `--json` + `--gate-report`.
- `/mql5-trade-hygiene` — static trade-call hygiene scan (OrderCheck / volume-price normalize / freeze-&-stops level / retcode handling / OrderCalcMargin / margin-mode / async hooks / basket magic). Advisory (warn/info only) — never blocks the scan gate. Supports `--json` + `--gate-report`.
- `/mql5-mt5-python` — import-guarded MetaTrader5 Python worker for live-env evidence capture (`probe` / `capture` / `order-check-normalize`). Offline → UNTESTABLE (exit 3); cannot run the Strategy Tester programmatically. Supports `--json`.

## RRI methodology (4 — 1 umbrella + 3 aliases)
- `/mql5-rri` — umbrella CLI. Subcommands (alias to the entry points below):
  - `/mql5-rri` *(no subcommand)* / `/mql5-rri template` — print the Step-2 RRI markdown template (legacy default).
  - `/mql5-rri bt --metrics bt.json [--mode personal] [--output rri-bt.html]` — Backtest review (5 personas × 7 dim × 8 axis).
  - `/mql5-rri rr --trader-check tc.json --walkforward wf.json --monte-carlo mc.json --overfit of.json [--output rri-rr.html]` — Risk & Robustness review.
  - `/mql5-rri chart --metrics chart.json [--output rri-chart.html]` — Optional indicator-dev RRI.
- `/mql5-rri-bt`, `/mql5-rri-rr`, `/mql5-rri-chart` — kept as **aliases** for back-compat; each is a 1-line forward to the umbrella subcommand above. Use the umbrella for new code.

## Review (6 — 1 umbrella + 4 aliases + 1 standalone)
- `/mql5-review` — umbrella CLI. Either `--lens <eng|ceo|cso|investigate>` (multi-persona preset) **or** the legacy `--persona <id> --step <id>` single-persona path:
  - `mql5-review --lens eng [--mode personal] [--output eng-review.md]` → broker-engineer + devops, steps BUILD + VERIFY.
  - `mql5-review --lens ceo [--mode personal] [--output ceo-review.md]` → trader + strategy-architect, steps VISION + REFINE.
  - `mql5-review --lens cso [--mode personal] [--output cso-review.md]` → risk-auditor, steps RRI + VERIFY.
  - `mql5-review --lens investigate [--mode personal] [--output investigate.md]` → perf-analyst + strategy-architect + Hypotheses worksheet.
  - `mql5-review --persona trader --step verify --mode personal --output review.md` → legacy single-persona dispatch (unchanged).
- `/mql5-eng-review`, `/mql5-ceo-review`, `/mql5-cso`, `/mql5-investigate` — kept as **aliases** for back-compat; each forwards to the matching `--lens` on the umbrella. Use the umbrella for new code.
- `/mql5-second-opinion` — standalone lint + Trader-17 fast pass on a `.mq5`; NOT a lens (not consolidated).

## Deploy (3)
- `/mql5-deploy-vps` — emit a MIGRATE-VPS.md checklist
- `/mql5-cloud-optimize` — emit a tester.ini for Cloud Network
- `/mql5-canary` — 30-min post-deploy live monitor

## Ship (4)
- `/mql5-forge-pr` — push a PR to Algo Forge
- `/mql5-package` — produce `manifest.json` (SHA-256 inventory) + `<name>-ship.zip` from an `mql5-auto-build` output dir; same step runs inline when `mql5-auto-build --package` is set
- `/mql5-ship` — verify evidence + package + signed manifest
- `/mql5-refine` — classify a diff as tweak/patch/rework

## Other (4)
- `/mql5-broker-safety` — verify pip-norm + multi-broker
- `/mql5-trader-check` — Trader-17 checklist (positional `.mq5` path; outputs JSON verdict 6+/17 PASS threshold)
- `/mql5-permission` — 7-layer permission gate orchestrator (positional `.mq5` source; `--mode {personal,team,enterprise}` selects gate set: PERSONAL=1/2/3/4/7, TEAM=1-5/7, ENTERPRISE=1-7)
- `/mql5-install` — reconcile-install kit overlay

## Agent contracts (3)
- `/mql5-manifest` — emit (or validate) a machine-readable catalogue of every CLI: `--emit [--output manifest.json]`, `--validate manifest.json`
- `/mql5-fixture` — generate hermetic MT5 Strategy Tester fixtures so the BT/WF/MC/MB pipeline runs on Linux without Wine: `--type {backtest,walkforward,monte-carlo,multibroker} --strategy {random,trend,mean-rev} --seed N --out <dir>`
- `/mql5-forge-loop` — ****: closed forge iteration loop. Chains `mql5-fixture --type backtest` into `mql5-backtest` parsing for `N` deterministic iterations (`--iterations 3 --strategy trend --base-seed 100 [--pf-floor F] [--sharpe-floor F] [--max-dd-ceiling F]`). No Wine, no MetaTester. Emits a per-iter `forge-loop-report.json` + `--json` envelope so the matrix collector consumes it unchanged.

## Agent prompts (paste-and-run persona roles, no CLI)

Six markdown persona prompts (described below)
turn an external LLM chat into a focused single-role assistant aligned
with the 8-step RRI methodology. They are documentation artefacts, not
CLIs — every prompt declares a YAML frontmatter (`persona`, `role`,
`review_lens`, `owns_steps`, `contributes_steps`, `peers`, `inputs`,
`outputs`, `forbidden`) pinned by the bundled agent-prompt schema tests.

| File | Persona | Lens | Owns steps |
|---|---|---|---|
| `strategy-architect` | Quant / strategy author | `ceo`, `investigate` | SCAN, RRI, VISION, REFINE |
| `broker-engineer` | Senior MQL5 implementer | `eng` | BLUEPRINT, TIP, BUILD, VERIFY |
| `risk-auditor` | Compliance / risk officer | `cso` | RRI, BLUEPRINT, VERIFY |
| `devops` | Deploy / VPS / observability | `eng` | BUILD, VERIFY, REFINE |
| `perf-analyst` | Backtest + tester analyst | `investigate` | VERIFY, REFINE |
| `trader` | End-user ("owner") | `ceo` | SCAN, VISION, VERIFY |

These prompts pair with the generators (`mql5-vision-gen` /
`mql5-blueprint-gen` / `mql5-tip-gen`) and the sentinel-content validator (`mql5-permission --layer5-enforce-activities`).

### Triangle of Power — three actor prompts 

In addition to the six personas, ships three
governance-layer **actor prompts** from the legacy v2.6 distribution. The
current package routes these responsibilities through `skill/vibecode-mql5/`
and the `[CONTRACTOR]` / `[BUILDER]` / `[VERIFIER]` hat-switch protocol:

- `chu-nha.md` — Homeowner (the human operator). Owns SCAN, VISION,
  APPROVED on blueprint, CONFIRM on contract, REFINE decision.
- `chu-thau.md` — Contractor (Claude Chat / GPT-4 / Cursor Ask seat).
  Owns VISION design, BLUEPRINT, CONTRACT, TASK-GRAPH, VERIFY-REPORT,
  REFINE proposals. Forbidden from running build / compile / tester
  tools.
- `tho-thi-cong.md` — Builder (Claude Code / Devin / Cursor Edit seat).
  Owns SCAN execution, TIP implementation, BUILD, VERIFY runs.
  Forbidden from running design CLIs (vision-gen / blueprint-gen /
  contract-gen / verify-report).

Each actor file declares `sub_personas:` mapping to the personas it wraps, plus an `escalates_to:` / `delegates_to:` graph and a
`forbidden_tools:` allow-list. The persona frontmatter gained
a `super_actor:` field binding it to its parent actor; the schema tests bundled with the kit pin the mapping.
These persona/actor prompts are bundled with the kit's RRI methodology
resources; see the master guide for the operator playbook.

## Full command reference — remaining commands (coverage completion)

The persona + governance tables above are the fast path. The generated
catalog is the authoritative list of all 133 console scripts. Entries whose
maturity is `deprecated`/`compat` are kept only as thin aliases for older
operator habits — prefer the canonical command in their description.

| Command | Maturity | Purpose |
| --- | --- | --- |
| `mql5-ap-policy` | release-grade | Profile-aware anti-pattern policy. |
| `mql5-architecture-check` | release-grade | Architecture compliance checker for profile-driven EA generation. |
| `mql5-blueprint-tip` | release-grade | Blueprint risk/tip reviewer. |
| `mql5-compile-repair` | release-grade | Compile repair loop. |
| `mql5-compile-runner` | release-grade | Real compile runner wrapper. |
| `mql5-contract-blueprint` | release-grade | Contract blueprint generator/validator. |
| `mql5-contract-build` | release-grade | Contract build orchestrator. |
| `mql5-contract-check` | release-grade | vkmql-check contract — project contract checker (v3 governance). |
| `mql5-ea-audit` | release-grade | Single-command deep-review orchestrator (``mql5-ea-deep-review``). |
| `mql5-ea-auto-llm-review` | placeholder | Automatic EA review workflow: intake + static review + LLM pack + optional LLM run. |
| `mql5-ea-chat-review-pack` | release-grade | Chat-LLM review bridge pack. |
| `mql5-ea-chat-review-workflow` | release-grade | One-shot workflow for generic chat LLM environments. |
| `mql5-ea-compose` | release-grade | EA composer for profile-required modules/hooks. |
| `mql5-ea-deep-review` | release-grade | Single-command deep-review orchestrator (``mql5-ea-deep-review``). |
| `mql5-ea-doc-verify` | release-grade | Verify EA documentation claims against source evidence. |
| `mql5-ea-intake` | release-grade | Existing EA intake. |
| `mql5-ea-intake-review` | release-grade | One-shot existing EA intake + review. |
| `mql5-ea-llm-review-pack` | release-grade | LLM review pack generator for MQL5 EA projects. |
| `mql5-ea-llm-review-run` | placeholder | LLM review runner adapters. |
| `mql5-ea-patterns` | release-grade | mql5-ea-patterns -- safety-first EA strategy pattern bank. |
| `mql5-ea-review-report` | release-grade | Generate senior-style EA review report DOCX. |
| `mql5-ea-senior-review` | release-grade | Senior-style static EA review. |
| `mql5-evidence-matrix` | release-grade | Evidence Matrix v2: distinguish measured, heuristic, imported, and unknown cells. |
| `mql5-flow` | release-grade | mql5-flow -- methodology driver (status / next). |
| `mql5-gate-escalate` | release-grade | mql5-gate-escalate -- auto-raise an escalation when a gate FAILS. |
| `mql5-ml-validate` | placeholder | ML/ONNX validation evidence checker. |
| `mql5-multibroker-runner` | release-grade | Remote multi-broker Strategy Tester runner. |
| `mql5-new` | release-grade | vkmql-* — high-level workflow verbs over the mql5-* primitives. |
| `mql5-owner-approve` | release-grade | Owner approval artifact. |
| `mql5-owner-interview` | release-grade | Owner interview contract artifact. |
| `mql5-project-gen` | scaffold | Modular EA project generator for complex EA architectures. |
| `mql5-refine-tip` | release-grade | mql5-refine-tip -- auto-generate a TIP from a failing VERIFY. |
| `mql5-role-guard` | release-grade | mql5-role-guard -- enforce role ownership + blueprint sign-off. |
| `mql5-role-state` | release-grade | mql5-role-state -- unified role & sign-off state (single source of truth). |
| `mql5-rri-run` | release-grade | mql5-rri-run -- make the RRI step executable. |
| `mql5-scan-ea` | release-grade | mql5-scan-ea -- SCAN REPORT for an existing EA source. |
| `mql5-selftest` | release-grade | mql5-selftest / ``vkmql-check selftest`` — ship-in-slim smoke test. |
| `mql5-ship-flow` | release-grade | vkmql-* — high-level workflow verbs over the mql5-* primitives. |
| `mql5-spec-v26` | release-grade | Per-project governance scaffolding for the v3 flow (v2.6-compatible). |
| `mql5-test-runner` | release-grade | Real MT5 Strategy Tester runner wrapper. |
| `mql5-tester-ini` | release-grade | MT5 Strategy Tester INI generator. |
| `mql5-verify-evidence` | release-grade | mql5-verify-report -- render a VERIFY report with embedded evidence. |
| `mql5-version` | release-grade | mql5-version — print the single-source kit version. |
| `mql5-walkforward-runner` | release-grade | Remote walk-forward runner. |
