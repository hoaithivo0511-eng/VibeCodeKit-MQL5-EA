---
id: usage-en
title: VibeCodeKit MQL5 EA v3.3.0rc7 Operating Guide (English)
audience: end_user, dev_team
---

# VibeCodeKit MQL5 EA v3.3.0rc7 — Operating Guide

This guide describes the **current integrated RC7 tool line**. The latest published tester pre-release may still be RC6; a repository source version and a promoted release are separate facts.

For the full Vietnamese reference, use `HUONG-DAN-TOAN-TAP-vi.md`. For every console entrypoint, use the machine-readable `tool-catalog.json` plus `COMMANDS.md`.

## 1. Operating principles

1. Use the small public surface first: `vkmql-new`, `vkmql-check`, `vkmql-ship`, `mql5-ea-deep-review`, `mql5-doctor`.
2. Treat `mql5-*` commands as advanced/internal/compatibility primitives unless a guide explicitly asks for one.
3. Missing execution environments are `UNTESTABLE`, never PASS.
4. Compile evidence does not substitute for Strategy Tester, restart/recovery or live evidence.
5. Evidence must bind execution provenance and hashes; realistic filenames are not proof.
6. Demo strategies are fixtures, not hidden defaults for generated EAs.

## 2. VibecodeV5 lifecycle

RC7 uses the 10-step lifecycle:

```text
SCAN
→ RRI
→ SPECIFY
→ DECIDE
→ CONTRACT
→ PLAN
→ BUILD
→ VERIFY
→ EVIDENCE
→ RETRO
```

### SCAN

Inventory the repository/project and identify the actual EA source, dependencies, existing evidence, broker/runtime assumptions and risk boundaries.

### RRI

Ask only the questions that can materially change implementation or acceptance. For a release/native/risk change, use Full depth; for a small fix, use Lite/Standard depth.

### SPECIFY

Turn requirements into explicit machine/human-readable constraints. Existing projects can be audited in place; a new project can start with:

```bash
vkmql-new spec ./MyEA --name MyEA --symbol EURUSD --tf H1
```

### DECIDE

Resolve architecture, account mode, execution model, risk invariants, evidence target and known exclusions. Do not bury unresolved decisions in generated code.

### CONTRACT

```bash
vkmql-new contract ./MyEA --name MyEA
```

The contract is the hand-off boundary between design, implementation and verification.

### PLAN

Create the task graph/TIP state appropriate to the change size. Large release work should make dependencies and acceptance criteria explicit.

### BUILD

Use deterministic project/source generators where they fit, or modify existing source directly. Advanced generation examples:

```bash
mql5-spec-from-prompt \
  "EA named TrendEA, EURUSD H1, netting, risk 0.5%, trend strategy" \
  --strict --out EA-IR.json

mql5-auto-build --spec EA-IR.json --out-dir ./MyEA
```

### VERIFY

Static verification and native compile are independent from runtime Strategy Tester verification.

```bash
vkmql-check lint ./MyEA/Experts/MyEA/MyEA.mq5
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 \
  --project-root ./MyEA --backend auto
vkmql-check all ./MyEA
```

### EVIDENCE

Release-positive evidence requires the corresponding trusted execution source plus integrity/provenance checks. Imported/sample reports remain useful for parser regression but are not native execution proof.

### RETRO

Record what escaped earlier gates and convert recurring failures into tests/policies. RC7 examples include duplicate-content classification, toolchain-preparation ownership and native evidence source binding.

## 3. Environment setup

Python 3.10+ is required by the current package metadata.

```bash
cd vibecodekit-mql5-ea
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'

mql5-doctor --soft
mql5-selftest
```

Wine is optional for development compile on Linux. It is **not** required if you use a configured GitHub Actions Windows backend or remote Windows worker.

A local Windows MetaEditor remains the highest-priority `auto` compile backend when present.

## 4. RC7 compile architecture

Canonical frontend:

```bash
vkmql-check compile <target.mq5> --backend auto
```

Backend order:

```text
local-metaeditor
→ github-actions
→ remote-worker
→ wine-metaeditor
→ UNTESTABLE
```

### Local Windows

Point the tool at the local native MetaEditor when automatic discovery is not enough.

### GitHub Actions Windows

Explicit example:

```bash
vkmql-check compile Experts/MyEA/MyEA.mq5 \
  --project-root . \
  --backend github-actions \
  --github-repo OWNER/REPO \
  --github-ref main \
  --github-commit <40-char-commit-sha> \
  --out evidence/compile \
  --json
```

The GitHub backend correlates the dispatch request, exact commit, workflow run, job, repository and downloaded artifacts before installing evidence locally.

The repository-native workflow uses `MT5_INSTALLER_URL`; release environments should also pin the expected installer with `MT5_INSTALLER_SHA256`.

### Remote Windows worker

Use only a worker that satisfies the kit's protocol, artifact hashes and release trust policy.

### Wine

Wine MetaEditor is development/diagnostic evidence. It does not become Windows-native release authority by changing a source label.

## 5. Compile house policy

A compile PASS requires:

- a MetaEditor log containing `Result:`;
- zero compile errors;
- zero warnings by default;
- a physical `.ex5` artifact;
- no stale log/EX5 reuse;
- coherent source/log/EX5 hashes;
- backend-specific provenance.

MetaEditor process exit code alone is not the final authority because the observed process code can differ from the compiler result recorded in the log.

## 6. Full gate and release semantics

Audit mode:

```bash
vkmql-check all ./MyEA
```

Release predicate:

```bash
vkmql-check all ./MyEA --require-release
```

The aggregate stage order includes source/contract/static checks plus compile, backtest, quality, forward, stress, review, retro, approval, evidence and release policy. Each stage reports one of:

```text
PASS | FAIL | UNTESTABLE | SKIPPED
```

`UNTESTABLE` is intentionally not a release PASS.

`vkmql-ship release` validates the release manifest and canonical provenance before packaging/signing. It is not a bypass around missing evidence.

## 7. Evidence trust model

Trusted release evidence is not established by file presence alone.

Examples of required distinctions:

```text
Wine compile                != native Windows compile
imported compile log        != execution provenance
sample tester XML           != real Strategy Tester run
hash chain only             != trusted producer evidence
GitHub source label only    != verified GitHub run provenance
```

The GitHub native path additionally validates Windows runner identity, full commit/tree SHA, run/job identifiers, repository binding, ProbeEA, artifact descriptors and downloaded artifact SHA/size.

## 8. Strategy Tester and runtime verification

For an EA whose behaviour/risk/execution changes, the release target may require:

```text
real Strategy Tester
quality/stress metrics
restart/recovery
walk-forward
multi-broker or broker/profile evidence
forward test
owner/release approval
```

The kit may parse imported reports for analysis, but imported/sample evidence remains non-release-trusted unless the execution provenance policy says otherwise.

## 9. Public vs advanced commands

Public:

```text
vkmql-new
vkmql-check
vkmql-ship
mql5-ea-deep-review
mql5-doctor
```

Advanced examples:

```text
mql5-spec-from-prompt
mql5-auto-build
mql5-lint
mql5-backtest
mql5-walkforward
mql5-monte-carlo
mql5-multibroker
mql5-rri
mql5-review
mql5-evidence-attestation
```

Compatibility/internal entrypoints are kept where needed so existing automation does not break, but new operator flows should prefer the public umbrellas.

## 10. Documentation

- `QUICKSTART.md` — shortest supported path.
- `USER-GUIDE-en.md` — concrete step-by-step project flow.
- `COMMANDS.md` — command surface guide.
- `HUONG-DAN-TOAN-TAP-vi.md` — full Vietnamese master guide.
- `GITHUB-NATIVE-COMPILE-vi.md` — GitHub native backend details.
- `DOC-MAP.md` — canonical topic ownership and historical-report policy.

Historical HTML audit reports keep their original test counts and versions. Do not use them as the current RC7 verdict.
