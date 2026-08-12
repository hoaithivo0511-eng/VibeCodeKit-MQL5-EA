---
id: user-guide-en
title: Step-by-step EA build with VibeCodeKit MQL5 v3.3.0rc7
audience: end_user, dev_team, ai_agent_operator
---

# Step-by-step guide — VibeCodeKit MQL5 v3.3.0rc7

This guide follows one project from requirements to an evidence-backed release decision. It does **not** promise a compiled `.ex5` or live-ready EA when the required execution backend is unavailable.

Current catalog: **139 console entrypoints**. Normal operators should prefer the five public commands and only drop to advanced primitives when needed.

## 0. What success means

There are several different success levels:

```text
source/static health
native compile
Strategy Tester/runtime evidence
forward/broker evidence
live eligibility
```

Passing one level does not automatically pass the next.

## 1. Install and self-check

```bash
cd vibecodekit-mql5-ea
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'

mql5-doctor --soft
mql5-selftest
```

If Wine/MetaEditor/MT5 are absent, environment probes can remain unavailable while source/package self-checks still run. That gap must remain visible.

## 2. SCAN — understand the project

For an existing EA, identify:

- entry `.mq5` and all `.mqh` dependencies;
- account mode and symbol/timeframe assumptions;
- trade/risk state and persistence model;
- existing tester/compile evidence;
- broker/timezone/session assumptions;
- manual edits or legacy compatibility constraints.

For a new project, start by creating governance artefacts rather than hardcoding assumptions into source.

## 3. RRI — resolve high-leverage questions

Examples:

- netting or hedging?
- fixed lot, risk-percent or another sizing rule?
- maximum simultaneous exposure?
- retry/idempotency behaviour after broker/terminal timeouts?
- restart/recovery expectations?
- target release level: static only, backtest, forward or live?

Do not ask 100 questions when five decisions determine the architecture. Use Full depth when release/risk/native evidence makes the cost justified.

## 4. SPECIFY

```bash
vkmql-new spec ./MyEA --name MyEA --symbol EURUSD --tf H1
```

Or generate canonical EA-IR from text with the advanced compiler:

```bash
mql5-spec-from-prompt \
  "EA named TrendEA, EURUSD H1, netting, trend strategy, risk 0.5%" \
  --strict --out EA-IR.json
```

Unresolved planning fields should remain explicit instead of being silently guessed.

## 5. DECIDE

Record architecture decisions that materially affect source or acceptance:

```text
account mode
execution model
risk invariants
symbol/pip normalization
session/day rollover model
state persistence/reconciliation
compile backend policy
runtime evidence target
```

For demo fixtures, keep project-specific logic in the fixture. Do not turn it into a kit-wide default.

## 6. CONTRACT

```bash
vkmql-new contract ./MyEA --name MyEA
```

The contract should make deliverables, exclusions, invariants and acceptance evidence explicit.

## 7. PLAN

Break the implementation into TIP/task graph units when the work is large enough to benefit from it. Release hardening should have explicit dependency and verification ownership; a tiny static fix can use a smaller plan.

## 8. BUILD

One advanced build path:

```bash
mql5-auto-build --spec EA-IR.json --out-dir ./MyEA
```

You can also work on an existing MQL5 project directly. The kit is not restricted to one generated scaffold family.

## 9. VERIFY — static

```bash
vkmql-check lint ./MyEA/Experts/MyEA/MyEA.mq5
mql5-ea-deep-review ./MyEA
```

Use advanced analyzers where relevant, for example method-hiding, broker safety, trade hygiene, risk review and RRI lenses.

## 10. VERIFY — compile

Canonical RC7 frontend:

```bash
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 \
  --project-root ./MyEA \
  --backend auto
```

`auto` preference:

```text
local Windows MetaEditor
→ GitHub Actions Windows
→ remote Windows worker
→ Wine MetaEditor (development/diagnostic)
→ UNTESTABLE
```

### GitHub Windows example

```bash
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 \
  --project-root ./MyEA \
  --backend github-actions \
  --github-repo OWNER/REPO \
  --github-ref main \
  --github-commit <40-char-commit-sha> \
  --out ./MyEA/evidence/compile \
  --json
```

A trusted GitHub record is validated beyond its source label: Windows runner, exact commit/tree, correlated run/job, repository, ProbeEA and artifact hashes/sizes are checked.

Compile PASS requires a MetaEditor `Result:` line, zero errors, zero warnings by default and a physical `.ex5`.

## 11. VERIFY — Strategy Tester/runtime

A native compile is not a Strategy Tester run.

For release targets that need runtime proof, generate or import evidence from a real MT5 Strategy Tester execution backend and retain provenance. Typical follow-up analyses include:

```text
backtest quality
walk-forward
Monte Carlo / stress
multi-broker stability
MFE/MAE
restart/recovery
```

A sample/imported report can validate parsers and calculations but is not automatically release-trusted execution evidence.

## 12. Aggregate gate

```bash
vkmql-check all ./MyEA
```

Expected statuses:

```text
PASS | FAIL | UNTESTABLE | SKIPPED
```

For release-mode CI:

```bash
vkmql-check all ./MyEA --require-release
```

Any mandatory `UNTESTABLE`, `FAIL` or disallowed skip blocks release eligibility.

## 13. EVIDENCE

The kit validates release evidence through a single conservative trust path. Core expectations include:

- trusted compile and backtest execution source;
- producer provenance;
- artifact SHA-256/size;
- evidence manifest consistency;
- stress/review semantics;
- runner attestation/trust root where required;
- no unsafe or skipped release stages.

GitHub-native compile records must pass the GitHub-specific record validator before the source is treated as release-trusted.

## 14. RETRO

After a milestone or escaped defect, turn the lesson into a guardrail. Examples from RC7 hardening:

- installer process exit code is not compile truth;
- standard-library warmup must verify the required header;
- temporary smoke workflows must not land in production main;
- distribution snapshot duplicates are intentional and classified;
- release provenance paths must agree about GitHub-native evidence;
- active docs need automated current-version/workflow checks.

## 15. Ship

Dry-run the ship predicate first:

```bash
vkmql-ship release --out-dir ./MyEA --dry-run
```

`vkmql-ship` does not create a legitimate release from an ineligible evidence manifest. Resolve the missing/failed evidence instead of bypassing the policy.

## 16. Recommended release ladder

```text
DRAFT
  static/source checks

BACKTEST_ELIGIBLE
  native compile + trusted Strategy Tester evidence as required

FORWARD_ELIGIBLE
  robustness/walk-forward/restart/broker evidence as required

LIVE_ELIGIBLE
  final policy + approval + operational evidence
```

The exact gates depend on the selected target, but later levels must never be inferred from an earlier one.

## 17. Where to read next

- `QUICKSTART.md` — shortest path.
- `USAGE-en.md` — RC7 operating model.
- `COMMANDS.md` — command support tiers and advanced primitives.
- `HUONG-DAN-TOAN-TAP-vi.md` — Vietnamese master guide.
- `GITHUB-NATIVE-COMPILE-vi.md` — native GitHub backend.
- `RELEASE-POLICY.md` / `RELEASE-TRUST.md` — release trust details.
- `DOC-MAP.md` — canonical source per documentation topic.
