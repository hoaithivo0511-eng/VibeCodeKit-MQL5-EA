---
id: v26-big-hardening
title: v2.6 BIG HARDENING
---

# v2.6 BIG HARDENING

v2.6 closes the gap between *"an AI coding tool said it's done"* and *"the kit
can prove it's done."* It adds a deterministic, machine-checkable contract
around every AI-built EA so a build can never silently mark itself ready.

> **Honesty rule (unchanged from earlier versions):** nothing here invents a
> PASS. Anything that cannot be observed locally (a real MetaEditor compile, a
> real Strategy Tester backtest, a real broker stress run) is reported as
> `UNTESTABLE`, never as success. `UNTESTABLE` blocks release-eligibility.

## What's new

### 1. EA-SPEC v2.6 schema (`spec_schema_v26`)
A stricter spec document with required `risk` bounds (incl.
`max_drawdown_pct`), `execution` (account modes, slippage/spread caps, magic
number policy) and `validation` flags. Forbidden "ready" statuses
(`READY`, `LIVE-READY`, `PRODUCTION-READY`) are rejected outright.

### 2. AI-BUILD-CONTRACT (`ai_build_contract`)
Generated from the spec, this is the guard-rail handed to the AI builder:
exactly which paths it may edit (`allowed_paths`), which it must never touch
(`forbidden_paths` — always including `evidence/` and `release/`), which claims
are forbidden, and what evidence a release requires. Available as
human-readable `.md` and machine-readable `.json`.

### 3. Completion Report parser (`completion_report_parser`)
When the AI finishes a TIP it hands back a Completion Report. The kit parses
it **without an LLM** (plain, deterministic scanning) and validates it: a
`DONE` status with no test evidence is rejected, and a TIP-ID mismatch is
rejected.

### 4. TIP state machine (`tip_state`) + richer TIPs (PRD §8)
Each TIP now carries `allowed_paths`, `forbidden_paths`, `acceptance_commands`,
`evidence_required` and a `rollback_plan`. The lifecycle is strict:

```
planned -> assigned -> reported -> verified -> accepted
```

A `DONE` report only moves a TIP to `reported`; acceptance happens **only**
through an explicit passing `verify`. A TIP cannot be assigned while any
dependency is not yet `accepted`.

### 5. Stress matrix v2 (`stress_matrix_v2`)
Eight broker-condition scenarios (spread widening, high slippage, stop/freeze
level constraints, insufficient margin, missing history, market closed, trade
context busy). With no live broker the scenarios report `UNTESTABLE`, never
`PASS`. The matrix loader accepts both a flat `scenarios: [...]` document and a
nested `stress_matrix:\n  scenarios: [...]` document. A malformed schema is
reported as a hard error (FAIL) — it is never silently replaced by the 8
default scenarios; defaults apply only when no matrix file is present.

### 6. Evidence attestation (`evidence_attestation`)
A tamper-evident SHA-256 hash chain over the evidence files. If any evidence
file changes after the chain is sealed, `verify` fails — a forged PASS cannot
survive re-verification. A valid chain alone is **not** enough to be
release-eligible: `attest --release-eligible` only writes
`release/ship-manifest.json` with `release_eligible=true` when **all** core
evidence is present (`compile/compile-log.txt`, `compile/ea.ex5`,
`backtest/report.xml`, `stress/stress-matrix-report.json`,
`review/deep-review.json`, `manifest.json`) **and** `manifest.release_eligible
== true`. If anything is missing it emits `release_eligible=false` and exits
non-zero — it never fabricates eligibility from an empty project.

### 7. One canonical release predicate (`release_policy.compute_release_eligible`)
The single source of truth for release-eligibility now also honours two new
gate keys — `stress_ok` and `hash_chain_ok` — alongside compile / backtest /
contract / evidence. Both default to the neutral value so older callers are
unaffected. `check_all` routes its final verdict through this same predicate,
so a build can never look "eligible" in one command and "blocked" in another.

### 8. Aggregate gate (`check_all`) and agent CLI (`vkmql-agent`)
`vkmql-check all` runs every stage (scan, contract, lint, compile, backtest,
stress, review, evidence, release-policy) and prints one honest verdict. The
scan stage walks `Experts/**/*.mq5` recursively (so a standard
`Experts/MyEA/MyEA.mq5` layout is covered, not just `Experts/*.mq5`) and scans
every `.mq5` file; any HIGH-severity risk flag in any file fails the stage.
`vkmql-agent` exposes the build loop to an AI agent: `export-context`,
`next-tip`, `ingest-report`, `status`, `repair-loop`.

## New commands

| Command | Purpose |
| --- | --- |
| `vkmql-new spec` | Write a v2.6 `EA-SPEC.yaml`. |
| `vkmql-new contract` | Generate AI-BUILD-CONTRACT + risk/broker/evidence contracts. |
| `vkmql-new tip-graph` | Emit `TASK-GRAPH.yaml` + `TIP-STATE.json`. |
| `vkmql-check contract` | Validate the project AI-BUILD-CONTRACT. |
| `vkmql-check stress` | Run the stress matrix. |
| `vkmql-check evidence` | Release-evidence gate: verifies hash chain **and** core-evidence presence + manifest validity + release-eligible consistency. Prints `INCOMPLETE` + exits non-zero on missing evidence (never a bare `OK`). |
| `vkmql-check all` | Run every gate and print one verdict. |
| `vkmql-agent <verb>` | Drive the TIP build loop from an AI agent. |
| `mql5-ai-build-contract` | Generate/validate AI-BUILD-CONTRACT standalone. |
| `mql5-completion-report-parse` | Parse + validate a Completion Report. |
| `mql5-tip-state` | Inspect / initialise the TIP state machine. |
| `mql5-stress-matrix` | Run the stress matrix standalone. |
| `mql5-evidence-attestation` | Build / verify / attest evidence. |

## Workflow at a glance

```
vkmql-new spec MyEA           # 1. write EA-SPEC.yaml (v2.6)
vkmql-new contract MyEA       # 2. generate AI-BUILD-CONTRACT + contracts
vkmql-new tip-graph MyEA      # 3. emit TASK-GRAPH + TIP-STATE
# ... AI builder works TIP by TIP, handing back Completion Reports ...
vkmql-agent ingest-report MyEA --tip TIP-001 --report report.md
vkmql-check all MyEA          # 4. one honest verdict (UNTESTABLE until real evidence)
```
