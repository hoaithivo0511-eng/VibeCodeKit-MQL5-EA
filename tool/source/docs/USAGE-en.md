---
id: usage-en
title: vibecodekit-mql5-ea v2.4.3 Usage Guide (English)
audience: end_user, dev_team
---

# `vibecodekit-mql5-ea` v2.4.3 Usage Guide

End-to-end walkthrough of all 118 commands, from idea to live shipping.
Suitable for both new users and dev teams.

> 📚 Vietnamese master guide (single source): [HUONG-DAN-TOAN-TAP-vi.md](HUONG-DAN-TOAN-TAP-vi.md)

## Contents

1. [Environment setup](#1-environment-setup)
2. [The 8-step build philosophy](#2-the-8-step-build-philosophy)
3. [Commands by stage](#3-commands-by-stage)
4. [End-to-end example: MACD+SAR EURUSD H1](#4-end-to-end-example)
5. [Integrating the 4 MCP servers](#5-integrating-the-4-mcp-servers)
6. [23 anti-pattern detectors](#6-23-anti-pattern-detectors)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Environment setup

### 1.1. Requirements

| Component | Version |
|-----------|---------|
| Python | ≥ 3.10 |
| Wine | 8.0.2 (Linux/macOS) — MetaEditor is native on Windows |
| MetaEditor | build ≥ 5260 (so method-hiding lint stays at ERROR) |
| ONNX runtime | 1.14 (ONNX e2e for ml-onnx scaffold + `mql5-onnx-export` / `mql5-onnx-embed`) |
| Xvfb | optional — needed only on headless Linux CI |

### 1.2. Linux (Ubuntu 22.04+)

```bash
# Unzip the downloaded release (.zip) to get started
cd vibecodekit-mql5-ea

./scripts/setup-wine-metaeditor.sh # ~3 min
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m vibecodekit_mql5.doctor # every probe must show ok: true
```

### 1.3. macOS

Wine on macOS runs but is not officially supported by MetaQuotes.
Recommend a Devin VM or Linux VM. If you must run locally:

```bash
brew install --cask wine-stable
# Then same as Linux
```

### 1.4. Windows

MetaEditor is native, no Wine needed. PowerShell:

```powershell
# Unzip the downloaded release (.zip) to get started
cd vibecodekit-mql5-ea
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m vibecodekit_mql5.doctor
```

> ⚠️ `setup-wine-metaeditor.sh` is bash-only — on Windows simply set
> `METAEDITOR_PATH` env var to your `metaeditor64.exe` path and skip
> the Wine step.

---

## 2. The 8-step build philosophy

the kit spec splits the entire EA lifecycle into 8 steps. Each step has a
markdown template in `docs/rri-templates/` and a dedicated command:

| Step | Name | Open template | Output |
|------|------|---------------|--------|
| 1 | **SCAN** | `python -m vibecodekit_mql5.scan <dir>` | Project tree |
| 2 | **RRI** (Research / Risk / Robustness) | `python -m vibecodekit_mql5.rri --mode {personal,team,enterprise}` | `docs/rri-report.md` |
| 3 | **VISION** | `python -m vibecodekit_mql5.vision` | `docs/vision.md` |
| 4 | **BLUEPRINT** | `python -m vibecodekit_mql5.blueprint` | `docs/blueprint.md` |
| 5 | **TIP** (8 Technical Implementation Points) | `python -m vibecodekit_mql5.tip` | `docs/tip.md` |
| 6 | **BUILD** | `python -m vibecodekit_mql5.build <archetype>` or `wizard`, `async-build` | `.mq5` from scaffold |
| 7 | **VERIFY** | 10 commands from `compile` → `multibroker` | XML report + 64-cell matrix |
| 8 | **REFINE + SHIP** | `python -m vibecodekit_mql5.refine` + `ship` | Verify + package + signed manifest |

### Mode breakdown

| Mode | RRI questions | Permission layers | Audience |
|------|---------------|-------------------|----------|
| `personal` | 5 q/persona × 6 = 30 | 1, 2, 3, 4, 7 | Solo trader |
| `team` | 12 q/persona × 6 = 72 | 1-5, 7 | 2–5-dev team |
| `enterprise` | 25 q/persona × 6 = 150 | 1-7 (full) | Org / fund |

---

## 3. Commands by stage

### 3.1. Discovery (4)

```bash
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio
python -m vibecodekit_mql5.survey "MA cross strategy H1 trend following"
python -m vibecodekit_mql5.doctor
python -m vibecodekit_mql5.audit
```

### 3.2. Plan — template openers + generators (7)

```bash
# Template renderers (open the markdown skeleton)
python -m vibecodekit_mql5.rri --mode team
python -m vibecodekit_mql5.vision
python -m vibecodekit_mql5.blueprint
python -m vibecodekit_mql5.tip

# deterministic step-output generators (no LLM call)
mql5-vision-gen step-2-rri.md --out step-3-vision.md
mql5-blueprint-gen ea-spec.yaml --vision step-3-vision.md --out step-4-blueprint.md
mql5-tip-gen step-4-blueprint.md --out step-5-tip.md
```

`mql5-vision-gen` parses the Step-2 RRI for `## Constraints` +
`- [x] persona::q-id` lines and fills the Scope / Active personas
sections of `step-3-vision.md`. Timeline + Risk register stay as
`TODO` for the operator (or downstream LLM persona) to refine.

`mql5-blueprint-gen` loads `ea-spec.yaml`, validates via `spec_schema`,
and seeds the Step-4 invariants table from 18 preset-keyed templates
(`PRESET_INVARIANTS` in `step_gen/blueprint_gen.py`). The module
diagram + state machine are derived from the spec's signals / filters
/ stack / preset (sync vs async vs indicator-only branches). Pass
`--vision <step-3-vision.md>` to fuse the prior step's Scope items.

`mql5-tip-gen` parses the Step-4 BLUEPRINT for `## Invariants`
checkboxes and the first fenced block under `## Module diagram`. For
each invariant it emits a row with the most relevant module(s) (naive
keyword heuristic over `CPipNormalizer.mqh` / `CMagicRegistry.mqh` /
`CRiskGuard.mqh` / signal block / filter block) and a pytest-compatible
`test_<snake>` name. Test ownership + interface signatures are left as
`TODO` for the operator to refine.

All three generators support the standard `--json` envelope +
`--gate-report <path>` for downstream agent consumption.

### 3.3. Build (13)

```bash
# Scaffolds + patchers
python -m vibecodekit_mql5.build stdlib --name MyEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.wizard --name MyWizardEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.async_build --name MyHftEA --symbol EURUSD --tf M1
python -m vibecodekit_mql5.pip_normalize MyEA.mq5
python -m vibecodekit_mql5.onnx_export model.pt --output model.onnx --opset 14
python -m vibecodekit_mql5.onnx_embed MyEA.mq5 --model model.onnx
python -m vibecodekit_mql5.llm_context MyEA.mq5 --pattern cloud-api
python -m vibecodekit_mql5.forge_init MyEA

# End-user EA documentation — LLM structure-driven pipeline
# (bundle auto-runs inside mql5-auto-build; assemble runs once guide.md exists)
mql5-docs-bundle ea-spec.yaml MyEA.mq5 --out-dir build/MyEA/docs
mql5-docs-assemble build/MyEA/docs/guide.md --out build/MyEA/docs/MyEA.docs.docx
```

`mql5-docs-bundle` emits `docs-context.json` + `docs-prompt.md` from the
**real parsed `.mq5` inputs** (semantic-library enriched) plus build/lint
metrics. An external LLM agent reads those, authors `guide.md`, and
`mql5-docs-assemble` renders it to `MyEA.docs.docx`. The guide covers:

* **Kiến trúc hệ thống** — derived from the actual source structure.
* **Chu trình chiến lược** — strategy timeline.
* **Tham số EA** — table built from the real `input` declarations.
* **Chi tiết từng tham số** — per-input deep-dive (meaning, formula,
  sensible range, dependencies, gotchas) from the parsed inputs +
  semantic library.
* **Cách EA chạy** — OnInit / OnTick / OnDeinit narrative the LLM builds
  from the source itself (no fixed per-archetype template).
* **Setup khuyến nghị** — tuning guidance per account / broker context.
* **Ghi chú quan trọng** — rule-driven warnings (PipNormalizer,
  permission gate, AP-17 / AP-18 reminders).

> The legacy fixed-template renderer (`mql5-ea-docs` / `mql5-ea-docgen`)
> was removed in v2.6 — it could describe inputs that the shipped EA did
> not actually expose. Ship docs are now LLM structure-driven.

Available archetypes for `build`: `stdlib`, `trend`, `mean-reversion`,
`breakout`, `scalping`, `hedging-multi`, `news-trading`,
`arbitrage-stat`, `library`, `indicator-only`, `grid`, `dca`,
`portfolio-basket`, `wizard-composable`, `hft-async`, `ml-onnx`,
`service-llm-bridge`.

LLM patterns: `cloud-api` | `self-hosted-ollama` | `embedded-onnx-llm`.

#### 3.3a. One-shot auto-build pipeline

The four CLIs below close the gap between "I want an EA that does X"
and a green-CI pull request. Each command is deterministic, regex-only
(no LLM call), and produces a structured JSON or YAML artifact you can
feed into the next stage.

```bash
# Free-text → schema-valid ea-spec.yaml (use --explain to see what
# was inferred vs defaulted; --strict to fail if any required field
# isn't recognisable in the prompt).
mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5% macd or sar" \
    --out ea-spec.yaml --explain

# Single-shot pipeline: scan → build → lint → compile → permission-gate
# → dashboard. Writes auto-build-report.json (idempotent).
mql5-auto-build --spec ea-spec.yaml --out-dir build/MyEA

# Apply the 8-AP transformer loop to an existing .mq5 (AP-1, 3, 5, 15,
# 17, 18, 20, 21). Re-runs the lint after each pass.
mql5-auto-fix MyEA.mq5

# Render + (optionally) publish the 64-cell RRI quality matrix HTML.
# Reads MQL5_DASHBOARD_PUBLISH_CMD or --publish-cmd; falls back to
# file:// if no hook is configured.
mql5-dashboard --metrics metrics.json --out quality-matrix.html
```

Flags worth knowing:

* `mql5-auto-build --no-compile` skips the Wine + MetaEditor stage (useful
  on a Windows-less CI runner or when the focus is lint/gate alone).
* `mql5-auto-build --no-gate` skips the 7-layer permission orchestrator.
* `mql5-auto-build --force` re-renders the scaffold even when the
  `out_dir` is non-empty.
* `mql5-auto-build --publish-cmd <cmd>` overrides the dashboard
  publish hook for that one run.

Schema reference for `ea-spec.yaml` (risk / signals / filters / hooks /
stack overrides) lives at `scripts/vibecodekit_mql5/spec_schema.py`;
recognisers for `mql5-spec-from-prompt` are tabulated in
the chat-driven build parser (see the master guide §4).

### 3.4. Verify (13)

```bash
# Code-quality (run anytime; no XML needed)
python -m vibecodekit_mql5.compile MyEA.mq5
python -m vibecodekit_mql5.lint MyEA.mq5
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260

# .D POC — opt in to the lightweight MQL5 AST scanner for
# AP-1 (no SL) / AP-2 (SL too tight) / AP-7 (hardcoded magic). All
# other AP codes still use the regex pipeline. Findings are
# byte-identical to the regex pipeline on the 20-EA + 23-scaffold
# golden corpus, so this flag is safe to wedge into existing CI:
mql5-lint MyEA.mq5 --use-ast
mql5-lint MyEA.mq5 --use-ast --json --gate-report gate-report-lint.json

# Parse Strategy Tester XML report (run backtest manually first, then parse)
python -m vibecodekit_mql5.backtest MyEA.ex5 inputs.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json

# End-to-end Strategy Tester run (drives terminal64.exe via Wine + parses XML)
# Requires $MQL5_TERMINAL_PATH (exported by scripts/setup-wine-metaeditor.sh).
python -m vibecodekit_mql5.tester_run MyEA.ex5 \
    --symbol EURUSD --period H1 --from 2024-01-01 --to 2024-06-01 \
    --out tester.xml > metrics.json

# End-to-end Strategy Tester optimization (drives terminal64.exe + parses opt
# XML into top-N parameter sets). The .set file must carry optimize=true flags
# with start/step/stop ranges; mql5-optimize-run does not synthesize ranges.
python -m vibecodekit_mql5.optimize_run MyEA.ex5 default.set \
    --symbol EURUSD --period 2024.01.01-2024.12.31 --tf H1 \
    --mode genetic --criterion sharpe-max --top 10 > top-sets.json

# Hermetic / CI: parse an existing opt XML without launching MT5
python -m vibecodekit_mql5.optimize_run MyEA.ex5 default.set \
    --period 2024.01.01-2024.12.31 \
    --from-xml /path/to/opt-results.xml --criterion sharpe-max

# Walk-forward / overfit / monte-carlo take POSITIONAL XML/CSV inputs
python -m vibecodekit_mql5.walkforward is.xml oos.xml > walkforward.json
python -m vibecodekit_mql5.overfit_check is.xml oos.xml > overfit.json
python -m vibecodekit_mql5.monte_carlo returns.csv --reported-dd 5.4 \
                                         --n-sims 1000 --seed 42 > montecarlo.json

# Multi-broker: comma-separated XML report paths
python -m vibecodekit_mql5.multibroker --reports a.xml,b.xml,c.xml

# Custom fitness template (positional; omit to list 5 templates)
python -m vibecodekit_mql5.fitness sharpe > OnTester.mq5

# MFE/MAE: CSV must have columns deal_id,open_time,close_time,magic,
# type,profit,mfe,mae (exact, as emitted by CMfeMaeLogger.SaveToCsv())
python -m vibecodekit_mql5.mfe_mae mfe.csv
```

> **Note:** `backtest`, `walkforward`, `overfit_check`, `multibroker` only
> **parse** XML reports — they do NOT drive the Strategy Tester. Run the
> backtest yourself via MetaTrader 5 (or automate it with
> `terminal64.exe /config:tester.ini`), capture the XML, then feed it in.
> `cloud_optimize` only emits the `tester.ini` you upload to MetaQuotes
> Cloud Network. `tester_run` and `optimize_run` *do* drive
> `terminal64.exe` and parse the result; use them for local sweeps.

### 3.5. RRI methodology (4 — 1 umbrella + 3 aliases)

consolidated the three RRI CLIs (`mql5-rri-bt`, `mql5-rri-rr`,
`mql5-rri-chart`) into a single `mql5-rri` umbrella with subcommands.
The legacy console scripts remain as aliases that forward
1-line to the umbrella subcommand — JSON output is byte-identical
under `data.kind`. **Use the umbrella for new code.**

```bash
# Umbrella (preferred):
mql5-rri # legacy: print Step-2 RRI template
mql5-rri template # explicit template subcommand
mql5-rri bt --metrics metrics.json --mode enterprise --output rri-bt.html
mql5-rri rr --trader-check tc.json --walkforward wf.json \
               --monte-carlo mc.json --overfit of.json \
               --mode enterprise --output rri-rr.html
mql5-rri chart --metrics chart.json --mode personal --output rri-chart.html

# Legacy aliases (kept for back-compat, equivalent to the umbrella subcommands above):
mql5-rri-bt --metrics metrics.json --mode enterprise --output rri-bt.html
mql5-rri-rr --trader-check tc.json --walkforward wf.json \
               --monte-carlo mc.json --overfit of.json \
               --mode enterprise --output rri-rr.html
mql5-rri-chart --metrics chart.json --mode personal --output rri-chart.html

# Module-level (works on both umbrella and legacy aliases):
python -m vibecodekit_mql5.rri bt --metrics metrics.json --mode enterprise --output rri-bt.html
python -m vibecodekit_mql5.rri.rri_bt --metrics metrics.json --mode enterprise --output rri-bt.html
python -m vibecodekit_mql5.rri.rri_rr --trader-check tc.json --walkforward wf.json \
                                         --monte-carlo mc.json --overfit of.json \
                                         --mode enterprise --output rri-rr.html
python -m vibecodekit_mql5.rri.rri_chart --metrics chart.json --mode personal --output rri-chart.html
```

#### Matrix cell-coverage audit 

The 8×8 RRI quality matrix has 64 cells but only **6** of them are
filled discriminatively by a `--gate-report` artefact (one cell
per (dim, axis) pair). The remaining 58 cells either come from an RRI
HTML review that broadcasts the same dim status across all 8 axes
(`rri_broadcast`, 50 cells) or have no automation at all (`manual`,
8 cells — the entire `d_inference` row).

The legacy `passes_personal()` / `passes_enterprise()` thresholds
assume **all** 64 cells are populated and therefore always fail in
practice when the matrix is built solely from W1.4 gate-report
collection. Use the **gate-only** verdicts instead — they recompute
the personal / enterprise verdict against the 6 cells the collector
can actually fill.

```bash
# Standalone audit — no inputs / no reports needed:
python -m vibecodekit_mql5.rri.matrix --audit
# Prints:
# {
# "schema_version": "1",
# "total_cells": 64,
# "counts": {"gate_auto": 6, "rri_broadcast": 50, "manual": 8},
# "cells": { … per-cell map with the gate-report tool per gate_auto cell … }
# }

# Collect → matrix → HTML, gate-only verdicts also in the envelope:
python -m vibecodekit_mql5.rri.matrix --collect ./reports/ --output matrix.html
# Envelope adds :
# counts_by_coverage: per-class status counts
# passes_personal_gate_only: PASS verdict over the 6 gate_auto cells
# passes_enterprise_gate_only: strict PASS (zero WARN) over the same cells
```

The HTML report now visually distinguishes the three coverage classes
(solid blue border = `gate_auto`, dashed purple = `rri_broadcast`,
dim dotted grey = `manual`) so reviewers can tell at a glance which
cells carry real per-(dim, axis) signal and which are fillers.

Four of the six `gate_auto` cells are populated by **more than one**
emitter (e.g. `d_correctness × implement` is targeted by
`mql5-lint`, `mql5-method-hiding-check`, and `mql5-bt-sim`). When
multiple gate reports land on the same cell, `--collect` keeps the
**worst** status (`FAIL > WARN > PASS > N/A`) and concatenates every
contributing tool's summary into the cell note so reviewers can trace
the verdict. A single `FAIL` from any emitter is never silently
hidden by a later-alphabetically-named `PASS` report.

`--audit` ignores `--output` and prints to stdout. If both flags are
supplied, the CLI emits a stderr warning and exits 0.

| Cell | Coverage class | Discriminative tool(s) |
|-------------------------------------|-------------------|------------------------------------------------------------------------|
| `d_correctness × implement` | `gate_auto` | `mql5-lint`, `mql5-method-hiding-check`, `mql5-bt-sim` |
| `d_correctness × integration` | `gate_auto` | `mql5-permission` |
| `d_risk × design` | `gate_auto` | `mql5-trader-check` |
| `d_robustness × backtest` | `gate_auto` | `mql5-backtest`, `mql5-monte-carlo`, `mql5-mfe-mae`, `mql5-forge-loop` |
| `d_robustness × walk_forward` | `gate_auto` | `mql5-walkforward`, `mql5-overfit-check` |
| `d_broker_safety × multi_broker` | `gate_auto` | `mql5-broker-safety`, `mql5-multibroker` |
| `d_inference × *` (whole row) | `manual` | none — fill via `--inputs` JSON |
| _(all other 50 cells)_ | `rri_broadcast` | `mql5-rri bt|rr|chart` (uniform dim status across all 8 axes) |

### 3.6. Review openers (6 — 1 umbrella + 4 aliases + 1 standalone)

consolidated four review-persona CLIs (`mql5-eng-review`,
`mql5-ceo-review`, `mql5-cso`, `mql5-investigate`) into the single
`mql5-review` umbrella via the new `--lens <eng|ceo|cso|investigate>`
flag. Legacy console scripts remain as aliases (1-line forward
to `mql5-review --lens <name>`); JSON output is byte-identical with
`data.lens` and `data.steps` populated. **Use the umbrella for new
code.** `mql5-second-opinion` is a separate standalone fast-pass and
is NOT a lens (not consolidated).

```bash
# Umbrella (preferred):
mql5-review # legacy: open base review template
mql5-review --lens eng --mode personal --output eng-review.md
mql5-review --lens ceo --mode personal --output ceo-review.md
mql5-review --lens cso --mode personal --output cso-review.md
mql5-review --lens investigate --mode personal --output investigate.md
mql5-review --persona trader --step verify --mode personal --output review.md # legacy single-persona path (unchanged)

# Legacy aliases (kept for back-compat):
mql5-eng-review --mode personal --output eng-review.md
mql5-ceo-review --mode personal --output ceo-review.md
mql5-cso --mode personal --output cso-review.md
mql5-investigate --mode personal --output investigate.md

# Standalone (NOT a lens — lint + Trader-17 fast pass on a .mq5):
mql5-second-opinion EA.mq5

# Module-level:
python -m vibecodekit_mql5.review --lens eng --mode personal --output eng-review.md
python -m vibecodekit_mql5.review.eng_review
python -m vibecodekit_mql5.review.ceo_review
python -m vibecodekit_mql5.review.cso
python -m vibecodekit_mql5.review.investigate
```

### 3.7. Deploy (3)

```bash
python -m vibecodekit_mql5.deploy_vps MyEA --out MIGRATE-VPS.md --mode personal
python -m vibecodekit_mql5.cloud_optimize MyEA --symbol EURUSD --period H1 \
                                           --passes 1000 --budget-usd 50 --mode enterprise
python -m vibecodekit_mql5.canary MyEA.ex5 --duration 30m # or --journal mt5.log
```

### 3.8. Ship (4)

```bash
python -m vibecodekit_mql5.forge_pr feature-branch --target main

# Package an mql5-auto-build output as a manifest + ship-zip
python -m vibecodekit_mql5.package --out-dir ./dist --spec ea-spec.yaml
# Or fold the packager into the build pipeline (only runs on a green build):
python -m vibecodekit_mql5.auto_build --spec ea-spec.yaml --out-dir ./dist --package

python -m vibecodekit_mql5.ship --tag v1.0.1 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.1
python -m vibecodekit_mql5.refine --diff change.patch
```

**Ship .zip contents.** `mql5-package` (and `mql5-auto-build --package`)
walks the `--out-dir`, classifies each file via
`scripts/vibecodekit_mql5/package.py::classify_artifact`, writes a
`manifest.json` with SHA-256 + group index, and bundles everything into
`<out-dir>/<name>-ship.zip`. The bundle's groups:

| Group | Files | Why it ships |
|-----------|------------------------------------------------------------------|----------------------------------------------------------------|
| `runtime` | `*.ex5`, `Sets/*.set` | Drop into MT5 to run the EA / Strategy Tester preset |
| `source` | `*.mq5`, `*.mqh`, scaffold `README.md` | Recompile, audit source, review the scaffold |
| `review` | `auto-build-report.json`, `quality-matrix.html`, `*.docs.*`, `*.log` | Build / lint / compile / gate verdict + EA documentation |
| `repro` | `*spec*.yaml/yml/json`, `*.onnx`, `*.csv` | Re-derive the build from the spec + ML / dataset side-inputs |
| _(root)_ | `manifest.json` | SHA-256 inventory + group index for the rest of the zip |

Files outside the classifier (random `.txt`, IDE droppings, the zip
itself, an older `manifest.json`) are skipped. The `auto-build-report.json`
copy inside the zip is the build-side snapshot (build / lint / compile /
gate / docs / dashboard); the on-disk copy is rewritten after packaging
so `report.package.ok` and `report.package.groups` are also queryable
post-run.

### 3.9. Other (5)

```bash
python -m vibecodekit_mql5.broker_safety MyEA.mq5
python -m vibecodekit_mql5.trader_check MyEA.mq5
python -m vibecodekit_mql5.install ~/existing-mt5-project
python -m vibecodekit_mql5.second_opinion MyEA.mq5

# 7-layer permission gate orchestrator (positional source, NOT --source).
# Modes: personal (layers 1,2,3,4,7) | team (1-5,7) | enterprise (1-7).
mql5-permission --mode personal MyEA.mq5
mql5-permission --mode team MyEA.mq5 --multibroker reports/
mql5-permission --mode enterprise MyEA.mq5 \
    --compile-log build.log --trader-check-report trader.json \
    --matrix quality-matrix.html --journal rri-bt.json
```

`mql5-permission` exits 1 if any layer fails. Layer 2 (compile)
requires Wine + MetaEditor on Linux — use `mql5-doctor --soft` to
verify; on a docs-only CI runner that lacks Wine, omit `--mode
enterprise` so layer 2 doesn't block.

The state dir (`--state-dir`, default `.rri-state`) caches per-layer
payloads so subsequent CLI runs can re-use them without re-executing
each tool.

**sentinel-content validator on layer 5.** The methodology
layer (Layer 5) previously trusted ``.rri-state/<step>.done`` sentinels
without inspecting the step output's content, so an operator (or LLM
agent) could ``touch`` the sentinel without filling in any ``##
Activities`` checkbox in ``step-N-<name>.md``. Enable the audit with
``--enforce-activities``:

```bash
python -m vibecodekit_mql5.permission.layer5_methodology \
    --state-dir .rri-state --mode team --enforce-activities
```

The validator reads each step's companion ``step-N-<name>.md`` (next to
the sentinel) and computes the ratio of ``- [x]`` to ``- [ ]`` items
under ``## Activities``. The gate fails when the ratio is below the
per-mode default threshold (`personal ≥ 50%`, `team ≥ 80%`,
`enterprise = 100%`); override with ``--activity-threshold 0.7``.
Companion files with zero activities (or missing) pass trivially — the
validator is *additive*, not a replacement for the legacy sentinel-
existence check.

### 3.10. Forge closed loop (1, )

`mql5-forge-loop` runs a hermetic backtest iteration loop on Linux
without Wine. Each iteration chains `mql5-fixture --type backtest`
(deterministic by `--base-seed + i`) into the `mql5-backtest` XML
parser and aggregates the per-iter metrics into a single report.
Used to pin lint / parser contract regression and to drive forge-style
robustness sweeps in CI.

```bash
# Minimal — 3 iterations of the trend strategy, deterministic from seed 100:
mql5-forge-loop --iterations 3 --strategy trend --base-seed 100 \
                --out ./forge-loop/

# With hard gate floors — fail any iteration that breaches a threshold:
mql5-forge-loop --iterations 5 --strategy mean-rev --base-seed 200 \
                --pf-floor 1.10 --sharpe-floor 0.80 --max-dd-ceiling 35.0 \
                --out ./forge-loop/ \
                --gate-report forge-loop-report.json --json

# Module-level:
python -m vibecodekit_mql5.forge_loop \
    --iterations 3 --strategy random --base-seed 42 --out ./forge-loop/
```

`mql5-forge-loop` ships the `--json` envelope
(`schema_version=1`) and `--gate-report` flag, so the matrix collector
(`python -m vibecodekit_mql5.rri.matrix --collect`) consumes it unchanged. No Wine, no
MetaTester — the fixture generator emits the XML/CSV/journal artefacts
the backtest parser ingests.

### 3.11. Backtest engine — in-process tick-bar simulator (1, .E)

`mql5-bt-sim` generates **synthetic OHLC bars** under a seed-controlled
random walk, runs a built-in long-only strategy on those bars, and
emits an XML report in the same schema as MetaTrader 5's Strategy
Tester output. The existing `mql5-backtest` parser accepts the file
unchanged → chain `mql5-bt-sim → mql5-backtest` to replace
`mql5-fixture --type backtest` whenever the agent wants *real*
strategy entry / exit logic in the loop instead of raw return synthesis.

Four built-in strategies:

| `--strategy` | Logic |
|---------------|------------------------------------------------------------------------------------------|
| `sma-cross` | Fast/slow SMA crossover, long-only. Trending drift baked into bar synth → PF > 1. |
| `mean-rev` | Bollinger-style: enter long < SMA−k·σ, exit at SMA. AR(1) coefficient -0.5 in bar synth. |
| `breakout` | Donchian-channel: enter on N-bar high breakout, exit on N-bar low. Edge under trend. |
| `random` | Dumb baseline (enter on i%3==1 bars, exit on i%3==0). Useful as a zero-edge fixture. |

```bash
# Minimal — sma-cross on 500 synthetic bars, deterministic from seed 42:
mql5-bt-sim --strategy sma-cross --bars 500 --seed 42 --out tester.xml

# Chain into the existing XML parser unchanged:
mql5-backtest --report tester.xml --json

# JSON envelope + gate-report for the matrix collector:
mql5-bt-sim --strategy mean-rev --bars 500 --seed 99 \
            --out tester.xml --returns-csv returns.csv \
            --json --gate-report gate-report-btsim.json

# Tune the moving-average periods / mean-rev band width:
mql5-bt-sim --strategy sma-cross --fast 5 --slow 20 --bars 800 --seed 7 \
            --out tester.xml
mql5-bt-sim --strategy mean-rev --slow 30 --k 2.5 --bars 800 --seed 7 \
            --out tester.xml

# Module-level:
python -m vibecodekit_mql5.bt_engine \
    --strategy breakout --bars 600 --seed 123 --out tester.xml
```

Same `(strategy, seed, bars)` triple → byte-identical XML on re-run.
Pure-Python, dependency-free, no Wine, no MetaTester. The `--returns-csv`
output also drops into `mql5-monte-carlo` / `mql5-overfit-check`
unchanged for downstream robustness analysis.

---

### 3.12. Agent prompts — six paste-and-run persona roles 

The kit deliberately does **not** call an LLM internally. When you do
want an external LLM chat (Claude, ChatGPT, Cursor, Devin) to act as
a *single* role on a *single* step, use the matching role guidance from
`skill/vibecode-mql5/`; the old `docs/agent-prompts/` tree is not included
in the v3 package:

| File | Persona | Lens | Owns steps |
|---|---|---|---|
| `strategy-architect.md` | Quant / strategy author | `ceo`, `investigate` | SCAN, RRI, VISION, REFINE |
| `broker-engineer.md` | Senior MQL5 implementer (the code owner) | `eng` | BLUEPRINT, TIP, BUILD, VERIFY |
| `risk-auditor.md` | Compliance / risk officer | `cso` | RRI, BLUEPRINT, VERIFY |
| `devops.md` | Deploy / VPS / observability | `eng` | BUILD, VERIFY, REFINE |
| `perf-analyst.md` | Backtest + tester analyst | `investigate` | VERIFY, REFINE |
| `trader.md` | End-user (the "owner") | `ceo` | SCAN, VISION, VERIFY |

Each prompt has YAML frontmatter (`persona:`, `role:`,
`review_lens:`, `owns_steps:`, `contributes_steps:`, `peers:`,
`inputs:`, `outputs:`, `forbidden:`) plus a fixed set of operator
sections (`## Operating principles`, `## Step-by-step
responsibilities`, `## Handoff contracts`, `## What you must refuse
to do`, `## How to use this prompt`). The schema is pinned by the bundled agent-prompt schema tests, so every prompt
stays uniform and machine-readable.

These prompts pair cleanly with the generators
(`mql5-vision-gen` / `mql5-blueprint-gen` / `mql5-tip-gen`) — the
generator emits a deterministic skeleton, the LLM running under the
matching persona then refines it. They also pair with the content validator: the persona is not "done" with a step until the
matching `step-N-<name>.md` has enough ticked `## Activities`
checkboxes to pass the per-mode threshold (`personal ≥ 50%`, `team
≥ 80%`, `enterprise = 100%`).

See `docs/V3-GOVERNANCE.md` and `docs/RETRO-GUARDS.md` for the current
operator playbook. Historical prompt names below are migration notes only.

---

### 3.13. Triangle of Power — three actor roles + contract + verify-report 

introduces a governance layer on top of the six personas. The current kit
expresses the three actor roles in the skill router; it does not ship the old
`docs/agent-prompts//actors/` prompt tree, plus two new emitter CLIs and an
extension to the layer-5 permission gate that audits the manual
sign-off ritual between actors.

#### 3.13.1. Three actors

| File | Actor (English) | Sub-personas | Owns | Sign-off |
|---|---|---|---|---|
| `chu-nha.md` | Homeowner — the human operator | `trader` | SCAN, VISION (decide), REFINE (decide) | `APPROVED by <name>` on blueprint, `CONFIRM by <name>` on contract |
| `chu-thau.md` | Contractor — the design seat (Claude Chat / GPT-4 / Cursor Ask) | `strategy-architect`, `risk-auditor` | VISION (design), BLUEPRINT, CONTRACT, TASK-GRAPH, VERIFY-REPORT | Emits `CHECKPOINT` + `CONFIRM` blocks; never runs build/compile |
| `tho-thi-cong.md` | Builder — the implementation seat (Claude Code / Devin / Cursor Edit) | `broker-engineer`, `devops`, `perf-analyst` | SCAN (execute), TIP execution, BUILD, VERIFY runs | Emits Completion Reports + per-step `gate-report-*.json` |

Each actor file declares a `sub_personas:` mapping (binding it to the
six personas), an `escalates_to:` / `delegates_to:` graph
edge, and a `forbidden_tools:` allow-list. The six personas
got a matching `super_actor:` field; both schemas are pinned by the bundled prompt-schema tests.

#### 3.13.2. `mql5-contract-gen` — Step 4.5 contract emitter

The Contractor emits a homeowner-facing contract from an APPROVED
Step-4 blueprint plus the canonical `ea-spec.yaml`:

```bash
mql5-contract-gen step-4-blueprint.md \
    --ea-spec ea-spec.yaml \
    --out contract.md
```

The output has six fixed sections (`## DELIVERABLES`, `## EXCLUSIONS`,
`## TECH STACK`, `## INVARIANTS`, `## TASK GRAPH SUMMARY`,
`## ACCEPTANCE OVERVIEW`) followed by a manual `## CONFIRM` block the
Homeowner must complete (`CONFIRM by <name> at <YYYY-MM-DD>`).
Deliverable and exclusion bullets are preset-keyed (`trend`,
`mean-rev`, `breakout`, `grid`, `martingale`, `scalping`, `swing`,
`news`, …) so the same `(preset, stack)` always produces the same
contract body. The CLI supports the standard `--json` envelope and
`--gate-report <path>`.

If the blueprint is missing its `APPROVED by …` line, the contract
header includes a `> WARNING` callout so the operator notices before
forwarding.

#### 3.13.3. `mql5-verify-report` — Step 7 aggregator

Once the Builder has run every gate and dropped
`gate-report-*.json` envelopes into a directory, the Contractor
aggregates them into a single Markdown verify report:

```bash
mql5-verify-report \
    --gate-reports reports/ \
    --blueprint step-4-blueprint.md \
    --tip-dir tasks/ \
    --completion-dir completions/ \
    --out verify-report.md
```

The report derives `OVERALL STATUS = READY | NEEDS_FIXES |
MAJOR_ISSUES`, splits gates into Tech Health / Scenario Results /
Other, surfaces every FAIL with file pointer, and (when blueprint +
TIP dir are supplied) emits an `INVARIANT ↔ TIP` coverage table by
greedy keyword match. It also rolls up any `completion-*.md` STATUS
lines and ends with the four-choice REFINE menu (`Ship as-is`,
`Tighten`, `Add tests`, `Reopen VISION`) so the Contractor can hand
the Homeowner a decision draft.

#### 3.13.4. `mql5-permission-layer5 --enforce-sign-off` — manual seal audit

The layer-5 gate now optionally enforces the manual sign-off ritual:

```bash
mql5-permission-layer5 \
    --state-dir .rri-state/ \
    --mode team \
    --enforce-activities \
    --enforce-sign-off \
    --blueprint step-4-blueprint.md \
    --contract contract.md
```

The audit looks for `APPROVED by <name> at <date>` on the blueprint
and `CONFIRM by <name> at <date>` on the contract, captures the
signer + date, and computes a canonical sha256 over the body
**minus** the sign-off line. Any mutation to the body after the line
is added will silently change the hash so reviewers can detect a
re-edit. In `personal` mode the contract sign-off is optional; in
`team` and `enterprise` modes both are required. The flag composes
with `--enforce-activities` — both can run in a single
invocation.

---

### 3.14. Task Graph + Completion Report 

expands the homeowner-facing contract into a per-TIP
dependency DAG and gives the Builder a deterministic shape for the
Completion Report they hand back.

#### 3.14.1. `mql5-task-graph-gen` — expand contract.md into per-TIP files

The Contractor calls this CLI immediately after the Homeowner signs
the contract:

```bash
mql5-task-graph-gen contract.md --out-dir .
```

Outputs (deterministic given a fixed contract):

* `tasks/TIP-001.md` … `tasks/TIP-NNN.md` — one file per `TIP-NNN —
  <desc>` bullet in `## TASK GRAPH SUMMARY`, with YAML frontmatter
  (`tip_id`, `title`, `status: PENDING`, `actor: tho-thi-cong`,
  `depends_on: [...]`, `invariant_refs: [...]`,
  `contract_sha256_prefix:`) plus four Markdown sections (`## Goal`,
  `## Acceptance criteria`, `## Dependencies`, `## Completion`).
* `task-graph.md` — Mermaid `graph TD` diagram of the dependency
  edges plus an index table cross-linking every TIP with its actor
  and invariant count.

Dependencies are resolved structurally from a keyword classifier on
each TIP description:

| Class | Keyword(s) | Depends on |
|---|---|---|
| `scaffold` | `scaffold` | _none — root_ |
| `risk` | `risk guard`, `risk per` | every scaffold TIP |
| `signal` | `signal` | every risk TIP (fallback: scaffold) |
| `filter` | `filter` | every signal TIP (fallback chain) |
| `backtest` | `backtest`, `walk-forward` | every filter + signal TIP |
| `permission` | `permission`, `gate` | every backtest TIP |
| `other` | (anything else) | the immediate predecessor |

Invariants from the contract's `## INVARIANTS` block are
cross-linked into each TIP's frontmatter by greedy ≥ 6-char
alphabetic token match, so the Builder can trace which BLUEPRINT
invariant a TIP is implementing. The classifier and matcher are
deterministic — two invocations on the same contract produce
byte-identical files. Standard `--json` envelope and `--gate-report
<path>` are supported.

Add `--force` to overwrite an existing `tasks/TIP-*.md` or
`task-graph.md` (otherwise the CLI refuses with exit code 2).

#### 3.14.2. `mql5-completion-report` — per-TIP STATUS / Files / Tests / Issues

After the Builder finishes a TIP, they emit a per-TIP Completion
Report from the TIP file plus a directory of gate-report
envelopes:

```bash
mql5-completion-report \
    --tip tasks/TIP-001.md \
    --gate-reports reports/TIP-001/ \
    --file Include/CRiskGuard.mqh \
    --file TrendEA.mq5 \
    --test tests/test_risk_guard.py \
    --out completions/completion-001.md
```

Output (`completion-001.md`):

* `# Completion Report — TIP-001`
* `**TITLE:**`, `**STATUS:**` (READY / IN_PROGRESS / BLOCKED),
  `**ACTOR:** tho-thi-cong`, TIP source path + sha256 prefix
* `## Files Changed` — one bullet per `--file` flag
* `## Tests Added` — one bullet per `--test` flag
* `## Issues Encountered` — one bullet per `--issue` flag
* `## Gate Reports Referenced` — auto-generated table (Tool /
  Status / Summary / Path) for every envelope under
  `--gate-reports`
* `## Invariants Referenced` — verbatim from the TIP frontmatter

Status is derived deterministically:

| Condition | STATUS |
|---|---|
| Any envelope `FAIL` or any `--issue` supplied | `BLOCKED` |
| All envelopes `PASS` or `WARN`, no FAIL, no issues | `IN_PROGRESS` (if any WARN) or `READY` (if all PASS) |
| No envelopes loaded | `IN_PROGRESS` |

The CLI emits the standard `--json` envelope and `--gate-report
<path>`. When STATUS is BLOCKED the exit code is 1 so CI / shell
chains can short-circuit; otherwise the exit code is 0. The CLI
deliberately does **not** edit the TIP's `status:` frontmatter
field — that flip is the Builder's manual decision after reading
the report. The Contractor's `mql5-verify-report` picks
up the resulting `completion-*.md` files via `--completion-dir`.

#### 3.14.3. End-to-end flow

```
HOMEOWNER signs blueprint (APPROVED by <name>)
        │
        ▼
CONTRACTOR runs mql5-contract-gen
        │
        ▼
HOMEOWNER signs contract (CONFIRM by <name>)
        │
        ▼
CONTRACTOR runs mql5-task-graph-gen → tasks/TIP-001..N.md + task-graph.md
        │
        ▼
BUILDER picks the next root TIP → implements → emits gate-report-*.json
        │
        ▼
BUILDER runs mql5-completion-report → completions/completion-NNN.md
        │
        ▼
CONTRACTOR runs mql5-verify-report → verify-report.md
        │
        ▼
HOMEOWNER chooses REFINE option (Ship / Tighten / Add tests / Reopen VISION)
```

### 3.15. Escalation audit log 

When one Triangle-of-Power actor cannot proceed without input from
another, they raise an **escalation** instead of guessing. The kit
stores an append-only JSONL log under `.mql5-audit/escalations.jsonl`
so the audit trail composes with normal git workflows.

Three levels are recognised:

| Level | Meaning | Blocks `mql5-permission-layer5` (with `--enforce-no-open-escalation`)? |
|------:|---------|------------------------------------------------------------------------|
| 1 | Note / observation | No |
| 2 | Warning / question | No (informational; appears in Verify Report) |
| 3 | Hard block | **Yes** — TEAM / ENTERPRISE gate fails while any L3 stays OPEN |

#### 3.15.1. `mql5-escalation` — raise / list / resolve

```bash
# Raise (Builder asks Contractor for missing CPipNormalizer):
mql5-escalation \
    --from tho-thi-cong \
    --to chu-thau \
    --level 3 \
    --reason "missing CPipNormalizer for XAUUSD; pip math wrong" \
    --artefact tasks/TIP-002.md

# List (default filters to OPEN; --status RESOLVED|ALL also valid):
mql5-escalation --list
mql5-escalation --list --status ALL --level 3

# Resolve (Contractor acknowledges + records resolution):
mql5-escalation \
    --resolve ESC-20260525-001 \
    --resolved-by chu-thau \
    --note "patched in include/CPipNormalizer.mqh"
```

Behaviour:

- Each record gets a deterministic `ESC-YYYYMMDD-NNN` id allocated
  from a single scan of the existing log so two calls on the same day
  never collide.
- `--from` and `--to` must differ and must be one of
  `chu-nha` / `chu-thau` / `tho-thi-cong`.
- `--reason` is required and must be non-empty after stripping.
- Custom log path: `--audit-log <path>` (default
  `.mql5-audit/escalations.jsonl`).
- Standard envelope flags: `--json` for stdout, `--gate-report
  <path>` to persist.
- Idempotency: re-resolving a `RESOLVED` record raises an error
  rather than silently overwriting the previous note.

#### 3.15.2. Layer-5 hook — `--enforce-no-open-escalation`

```bash
# TEAM gate fails while any L3 escalation is still OPEN:
mql5-permission-layer5 \
    --mode team \
    --enforce-no-open-escalation

# Personal mode reports the count but does not fail (backward compat):
mql5-permission-layer5 \
    --mode personal \
    --enforce-no-open-escalation

# Custom log path (composes with --enforce-activities + --enforce-sign-off):
mql5-permission-layer5 \
    --mode enterprise \
    --enforce-no-open-escalation \
    --escalation-log .mql5-audit/escalations.jsonl \
    --enforce-sign-off \
    --enforce-activities
```

The envelope adds three new fields under `data`:

```json
{
  "escalation_log": ".mql5-audit/escalations.jsonl",
  "escalation_open_level3_count": 1,
  "escalation_open_level3": [
    {"id": "ESC-20260525-001", "from": "tho-thi-cong",
     "to": "chu-thau", "level": 3, ...}
  ],
  "escalation_enforced": true
}
```

`escalation_enforced` is `true` only when `mode != "personal"` so an
operator looking at a personal-mode report can immediately see the
count is informational.

#### 3.15.3. When to use which level

- **Level 1 (note):** Builder noticed a pre-existing magic number
  collision while implementing a TIP. Doesn't block this TIP, but the
  Contractor should know.
- **Level 2 (warning):** Builder discovered the TIP's acceptance
  criteria contradicts an invariant. Needs Contractor decision before
  the next TIP, but current TIP can ship.
- **Level 3 (hard block):** Builder cannot finish TIP-002 because the
  contract assumed `CPipNormalizer` exists but it doesn't.
  TEAM / ENTERPRISE gate refuses to ship until the Contractor either
  edits the contract or supplies the missing include.

---

## 4. End-to-end example

The full worked example lives at
`examples//ea-wizard-macd-sar-eurusd-h1-portfolio/`. It demonstrates a
**4-hour enterprise turnaround** on a Devin VM.

### Step 1 — SCAN (5 min)
```bash
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio
```

### Step 2 — RRI (90 min, enterprise mode)
```bash
python -m vibecodekit_mql5.rri.step_workflow --mode enterprise
# 6 personas × 25 questions = 150 questions
# → docs/rri-report.md
```

### Step 3 — VISION (15 min)
Fill `docs/rri-templates/step-3-vision.md.tmpl`:
- Hypothesis: MACD signal cross gated by Parabolic-SAR flip
- Scope: EURUSD H1 netting account
- Out of scope: hedging, multi-symbol, news filter

### Step 4 — BLUEPRINT (30 min)
Pick:
- Archetype: `wizard-composable/netting`
- Includes: `CPipNormalizer`, `CRiskGuard`, `CMagicRegistry`, `CMfeMaeLogger`
- Magic: 5001

### Step 5 — TIP (8 TIPs, ~30 min)
8 Technical Implementation Points covering SL/TP, risk per trade,
filters, trailing, kill switch, slippage limit, news blackout, weekly
DD cap.

### Step 6 — BUILD (10 min)
```bash
python -m vibecodekit_mql5.wizard \
    --name EAMacdSarPortfolio \
    --symbol EURUSD --tf H1 \
    --output ~/projects/eurusd-portfolio
```

### Step 7 — VERIFY (multi-stage, ~60 min)
```bash
# Code-quality first (no XML required)
python -m vibecodekit_mql5.compile EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.lint EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.method_hiding_check EAMacdSarPortfolio.mq5

# Run Strategy Tester manually via MT5 GUI, capture XML reports, then:
python -m vibecodekit_mql5.backtest EAMacdSarPortfolio.ex5 default.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json
python -m vibecodekit_mql5.walkforward is.xml oos.xml > walkforward.json
python -m vibecodekit_mql5.monte_carlo returns.csv --reported-dd 5.4 \
                                         --n-sims 1000 > montecarlo.json
python -m vibecodekit_mql5.overfit_check is.xml oos.xml > overfit.json
python -m vibecodekit_mql5.multibroker --reports a.xml,b.xml,c.xml
python -m vibecodekit_mql5.trader_check EAMacdSarPortfolio.mq5 > trader-check.json

python -m vibecodekit_mql5.rri.rri_bt --metrics metrics.json \
                                         --mode enterprise --output rri-bt.html
python -m vibecodekit_mql5.rri.rri_rr --trader-check trader-check.json \
    --walkforward walkforward.json --monte-carlo montecarlo.json \
    --overfit overfit.json --mode enterprise --output rri-rr.html
```

### Step 8 — REFINE + SHIP (~10 min)
```bash
python -m vibecodekit_mql5.refine --diff change.patch
python -m vibecodekit_mql5.ship --tag v1.0.0 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.0
```

Resulting artefacts in `results/`:
`EAMacdSarPortfolio.ex5`, `.set` file, 64-cell matrix HTML, backtest
XML, MFE/MAE report, canary log.

---

## 5. Integrating the 4 MCP servers

All four speak JSON-RPC 2.0 over stdio per the MCP spec. Usable from
any MCP client (Claude Desktop, Claude Code, Cursor, Codex, Devin, ...).

### 5.1. metaeditor-bridge

3 tools: `metaeditor.compile`, `metaeditor.parse_log`,
`metaeditor.includes_resolve`.

```bash
python mcp/metaeditor-bridge/server.py
```

### 5.2. mt5-bridge (READ-ONLY)

10 **read-only** tools (NO `order_send`, `order_close`, or
`position_modify` — enforced by `test_mt5_bridge_readonly_no_trade`):

- `mt5.symbols.list`, `mt5.symbol.info`
- `mt5.rates.copy`, `mt5.tick.last`
- `mt5.account.info`, `mt5.terminal.info`
- `mt5.positions.list`, `mt5.positions.history`
- `mt5.history.deals`, `mt5.market.book`

```bash
python mcp/mt5-bridge/server.py
```

> ⚠️ **Platform note:** the `MetaTrader5` Python package only installs
> on **Windows** (or a Wine-hosted MT5 desktop via `winetricks`). On a
> plain Linux VM the import fails and every tool returns a
> deterministic **stub payload** (empty symbol list, zero bars,
> hardcoded `digits=5, point=0.00001` for `mt5.symbol.info`). The
> stubs keep the MCP contract testable hermetically but they are
> **not live data**. Run this server on Windows or under Wine MT5
> when you need real account / market data.

### 5.3. algo-forge-bridge

6 tools: `forge.init`, `forge.clone`, `forge.commit`, `forge.pr.create`,
`forge.pr.list`, `forge.repo.list`. Requires `ALGO_FORGE_API_KEY`.

```bash
ALGO_FORGE_API_KEY=xxx python mcp/algo-forge-bridge/server.py
```

### 5.4. vibecodekit-bridge

29 tools across six PRs. Lets an AI coding agent (Codex CLI / Claude
Code / Cursor / Devin / Claude Desktop) drive the full `prompt → spec
→ build → verify → review → ship` loop via JSON-RPC. The wire format
is stable across PRs — future ones extend `DISPATCH` without breaking
clients.

**PR-1 (prompt → spec → build → permission-gate):**
`spec.from_prompt`, `spec.validate`, `build.auto`, `verify.permission`.

**PR-2 (static-analysis verify suite):** `verify.lint` (8 critical AP),
`verify.lint_best_practice` (17 WARN AP), `verify.method_hiding`,
`verify.trader17`, `verify.compile`, `verify.broker_safety`,
`verify.audit`.

**PR-3 (runtime / statistical verify suite):** `verify.backtest`
(MT5 tester XML report parser), `verify.walkforward` (OOS/IS Sharpe
correlation + verdict), `verify.montecarlo` (bootstrap DD stress
test), `verify.multibroker` (N-broker stability — PF CV / Sharpe
stdev / DD diff), `verify.fitness` (lookup tester `OnTester()`
template), `verify.mfe_mae` (excursion CSV stats), `verify.overfit`
(IS/OOS Sharpe ratio verdict — no XML required).

**PR-4 (review / RRI suite):** `review.eng` (broker-engineer + devops),
`review.cso` (risk-auditor), `review.ceo` (trader + strategy-architect),
`review.investigate` (perf-analyst + strategy-architect), plus the
generic `rri.persona` for ad-hoc 1-persona x 1-step x 1-mode drills.
Each tool returns markdown ready to drop into a PR description or a
`review.md` artefact.

**PR-5 (ship-stage tools):** `dashboard.publish` renders the 64-cell
quality-matrix HTML from a pipeline digest and publishes it via a
configurable command (falls back to `file://` URI when no command is
set). `forge.pr.create` opens a PR on MQL5 Algo Forge — real HTTP call
when `MQL5_FORGE_TOKEN` is available, structured dry-run payload
otherwise. Chain them to embed the public dashboard URL directly into
the Forge PR body.

**Spec schema additions (PR-2 + PR-8):** eight optional, back-compat
blocks on `ea-spec.yaml`. PR-2 added `prop_firm` (FTMO/MFF DD limits
+ news block + weekend-flat), `time_exit` (Friday close, max trade
duration, session windows), `stealth` (slippage / comment / lot-jitter
randomisation, split orders). PR-8 adds `trailing` (fixed/ATR/parabolic
trailing-stop), `partial_close` (scale-out levels + move-SL-to-breakeven
trigger), `correlation` (max correlated positions, Pearson threshold,
symbol group, block-on-correlated-loss), `swap_filter` (per-side daily
swap pip caps, skip Wednesday triple-swap), and `logs` (level, file
pattern, terminal output, account-number redaction). Specs that don't
supply them validate unchanged.

**PR-7 (discovery / fix-loop helpers):** `discover.doctor` runs the
kit's environment doctor (Python / Wine / MetaEditor / required
modules + scaffolds), `discover.scan` inventories a workspace tree
and classifies files by extension (`.mq5` → ea-source, `.mqh` →
include, `.set` → tester-set, `.ex5` → compiled, `.onnx` →
onnx-model), `discover.llm_context` wires one of the 3 LLM-bridge
scaffold patterns (`cloud-api` / `self-hosted-ollama` /
`embedded-onnx-llm`) into an existing EA `.mq5`, and
`verify.auto_fix` runs the AP auto-fixer over a file (in-place) or
an in-memory source string. Pair `verify.lint` ↔ `verify.auto_fix`
to close the agent's fix loop without leaving the bridge.

```bash
python mcp/vibecodekit-bridge/server.py
```

### 5.5. MCP client configuration

See [docs/HUONG-DAN-TOAN-TAP-vi.md](HUONG-DAN-TOAN-TAP-vi.md) (§12 MCP/IDE) for ready-to-paste configs
for Claude Desktop, Cursor, Codex, and Devin.

---

## 6. 26 anti-pattern detectors

Lint is split across two tiers:

### 6.1. Critical APs — ERROR, block ship (8)

| ID | Description | Detector |
|----|-------------|----------|
| AP-1 | `OrderSend` without SL | `lint.py` |
| AP-3 | Fixed lot size, not risk-based | `lint.py` |
| AP-5 | EA overfit (in-sample only) | `lint.py` |
| AP-15 | Raw `OrderSend` (no `CTrade`) | `lint.py` |
| AP-17 | `WebRequest` inside `OnTick` | `lint.py` |
| AP-18 | `OrderSendAsync` without `OnTradeTransaction` | `lint.py` |
| AP-20 | Hard-coded pip (`* 0.0001`, `* _Point`) | `lint.py` |
| AP-21 | JPY/XAU digits broken | `lint.py` |

### 6.2. Best-practice APs — WARN (17)

| ID | Description | Detector |
|----|-------------|----------|
| AP-2 | SL too tight | `lint_best_practice.py` |
| AP-4 | Martingale without cap | `lint_best_practice.py` |
| AP-6 | Curve-fitted optimisation | `lint_best_practice.py` |
| AP-7 | Hard-coded magic number | `lint_best_practice.py` |
| AP-8 | No spread guard | `lint_best_practice.py` |
| AP-9 | Multi-entry on same bar | `lint_best_practice.py` |
| AP-10 | `OrderSend` return not checked | `lint_best_practice.py` |
| AP-11 | EA mode-blind | `lint_best_practice.py` |
| AP-12 | Indicator handle leak | `lint_best_practice.py` |
| AP-13 | Broker-coupled EA | `lint_best_practice.py` |
| AP-14 | No MFE/MAE logging | `lint_best_practice.py` |
| AP-16 | Reinvent stdlib | `lint_best_practice.py` |
| AP-19 | ONNX without Strategy-Tester validation | `lint_best_practice.py` |
| AP-22 | `OnTick` reaches no order-placing call (placeholder signal) | `lint_best_practice.py` |
| AP-23 | `CTrade.Buy/Sell` return/retcode not checked | `lint_best_practice.py` |
| AP-24 | History/indicator access without sync guard | `lint_best_practice.py` |
| AP-25 | Raw `delete` without pointer guard | `lint_best_practice.py` |

### 6.3. Method-hiding (1, build-aware)

MetaEditor build ≥ 5260 reports ERROR when a `CExpert` subclass has a
method with the same name as a base method without a
`using BaseClass::method;` directive. Build < 5260 only WARNs.

```bash
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260
```

---

## 7. Troubleshooting

### "wine: command not found"
- Linux: `./scripts/setup-wine-metaeditor.sh` failed silently.
- macOS: `brew install --cask wine-stable`.
- Windows: set `METAEDITOR_PATH=C:\Path\To\metaeditor64.exe`.

### `doctor` reports "metaeditor-bin: not found"
```bash
export METAEDITOR_PATH=~/.wine/drive_c/Program\ Files/MetaTrader\ 5/metaeditor64.exe
```

### `doctor --soft` for docs-only / lint-only CI
Wine / MetaEditor / terminal probes degrade to warnings instead of failures, so
CI jobs that don't ship Wine still exit 0. Hard checks (Python ≥ 3.10, kit
package imports, `docs/references//`, scaffold archetypes) still flip the gate.
```bash
python -m vibecodekit_mql5.doctor --soft
# JSON output adds "soft": true and "strict_ok": <unfiltered ok>
# rc == 0 when only optional wine/MT5 probes fail; rc == 1 if any hard
# check fails.
```

### ONNX e2e test fails — torch not installed
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install onnx onnxscript
```

### Build reports a missing scaffold file
- Check `git status` for untracked scaffold files.
- Verify `.gitignore` isn't excluding artefacts:
  ```bash
  git check-ignore -v examples//**/results/canary.log
  ```

### mt5-bridge "MetaTrader5 not installed"
```bash
pip install MetaTrader5 # Windows or Wine MT5 desktop only
```

### `forge_init` returns 401 Unauthorized
```bash
export ALGO_FORGE_API_KEY=your_key_here
```

---

## Further resources

- [`docs/COMMANDS.md`](COMMANDS.md) — 43-command reference card
- [`docs/references//`](references/) — 28 technical cheatsheets (50-survey → 79-pip-norm)
- [`docs/anti-patterns-AVOID.md`](anti-patterns-AVOID.md) — VCK-HU anti-patterns to avoid
- [`docs/rri-personas/`](rri-personas/) — 6 YAML × 25 q each
- [`docs/rri-templates/`](rri-templates/) — 8 step-by-step markdown templates
- [`examples//ea-wizard-macd-sar-eurusd-h1-portfolio/`](../examples//ea-wizard-macd-sar-eurusd-h1-portfolio/) — 4-hour worked example

Questions / bugs → contact the official release support channel.


## Quality gates — added in v2.6.1

Three new commands add quantitative quality checks. Building an EA does **not** auto-run them — `mql5-build` / `mql5-project-gen` only scaffold code. Quality checking is a **separate, explicit** step via the `vkmql-check` gate.

| Command | Auto-runs inside `vkmql-check all`? | Notes |
| --- | --- | --- |
| `mql5-backtest-quality` | Yes — stage `quality` | Grades a tester XML on PF/RF/Sharpe/R²/MaxDD → PASS/WARN/FAIL/INSUFFICIENT. Advisory; blocks release only with `--require-release`. |
| stage `forward` (uses `mql5-walkforward`) | Yes — stage `forward` | Needs `evidence/walkforward/{is,oos}_report.xml`; absent → UNTESTABLE (not FAIL). |
| `mql5-trade-hygiene` | No — run separately (`vkmql-check hygiene`) | Static trade-call hygiene scan; advisory only, never blocks the gate. |
| `mql5-mt5-python` | No — standalone | MetaTrader5 worker (needs a live terminal); offline → UNTESTABLE (exit 3). |

```bash
# Full gate: quality + forward auto-run here (advisory)
vkmql-check all <project-dir>
vkmql-check all <project-dir> --require-release   # stricter: quality/forward block release

# Run SEPARATELY (not part of build or the default gate)
vkmql-check quality tester.xml        # = mql5-backtest-quality
vkmql-check hygiene Experts/MyEA.mq5  # = mql5-trade-hygiene
mql5-mt5-python probe --json          # needs a live MT5
```
