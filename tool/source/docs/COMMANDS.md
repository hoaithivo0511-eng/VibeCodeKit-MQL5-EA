---
id: commands
title: VibeCodeKit MQL5 v3.3.0rc7 command surface (139 entrypoints)
---

# Command surface — v3.3.0rc7

The package currently exposes **139 console entrypoints** for compatibility, advanced analysis and automation. Normal users should start with the **five public commands** instead of treating all 139 as equal UX surface.

Machine-readable source of truth:

```text
tool-catalog.json
pyproject.toml [project.scripts]
```

Validate/discover the installed catalog with the bundled manifest/selftest tools rather than relying on a historical prose count.

## 1. Public commands

| Command | Purpose |
| --- | --- |
| `vkmql-new` | Create project specs/contracts/planning/build artefacts through the high-level router. |
| `vkmql-check` | Static checks, compile, evidence, stress, status and aggregate release gates. |
| `vkmql-ship` | Verify release eligibility, package and sign the hand-off; no release bypass. |
| `mql5-ea-deep-review` | Deep EA/project review. |
| `mql5-doctor` | Environment/package capability diagnostics. |

Use:

```bash
vkmql-new --help
vkmql-check --help
vkmql-ship --help
mql5-ea-deep-review --help
mql5-doctor --help
```

## 2. Canonical new-project flow

```bash
vkmql-new spec ./MyEA --name MyEA --symbol EURUSD --tf H1
vkmql-new contract ./MyEA --name MyEA
```

Advanced prompt/EA-IR generation remains available:

```bash
mql5-spec-from-prompt \
  "EA named TrendEA, EURUSD H1, netting, risk 0.5%, trend strategy" \
  --strict --out EA-IR.json

mql5-auto-build --spec EA-IR.json --out-dir ./MyEA
```

## 3. Verification commands

High-level examples:

```bash
vkmql-check lint ./MyEA/Experts/MyEA/MyEA.mq5
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 \
  --project-root ./MyEA --backend auto
vkmql-check all ./MyEA
vkmql-check all ./MyEA --require-release
vkmql-check status ./MyEA
```

`vkmql-check compile` is the canonical RC7 compile frontend.

### Compile backends

```text
auto
local-metaeditor
github-actions
remote-worker
wine-metaeditor
```

`auto` prefers native Windows local MetaEditor, then configured GitHub Actions Windows, then remote Windows worker, then Wine development/diagnostic compile. No usable backend produces `UNTESTABLE` rather than a fake PASS.

### GitHub native example

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

See `GITHUB-NATIVE-COMPILE-vi.md` for repository secrets, provenance and reusable-action details.

## 4. Advanced source/build primitives

Common advanced commands include:

| Command | Purpose |
| --- | --- |
| `mql5-ea-intake-ir` | Compile prompt/text requirements into canonical EA-IR. |
| `mql5-doc-intake-ir` | Extract a document into page/source-referenced EA-IR. |
| `mql5-ir-build` | Capability-plan and generate a composable MQL5 project from EA-IR. |
| `mql5-ir-verify` | Verify IR/source/manifest binding and optional native evidence. |
| `mql5-spec-from-prompt` | Deterministic prompt-to-spec/IR intake. |
| `mql5-auto-build` | Build/lint/compile/permission/dashboard pipeline. |
| `mql5-lint` | MQL5 anti-pattern/static analysis. |
| `mql5-method-hiding-check` | Build-aware inherited-method collision check. |
| `mql5-trade-hygiene` | Trade-call hygiene analysis. |
| `mql5-broker-safety` | Broker-related static safety checks. |

These primitives are useful for automation and debugging, but they do not replace high-level release policy.

## 5. Runtime/statistical analysis primitives

Examples:

```text
mql5-backtest
mql5-backtest-quality
mql5-walkforward
mql5-monte-carlo
mql5-overfit-check
mql5-multibroker
mql5-mfe-mae
mql5-stress-matrix
mql5-mt5-python
```

Important distinction:

- parser/simulation tools can test calculations and schemas;
- only trusted actual/remote MT5 Strategy Tester sources satisfy release execution provenance where the policy requires it.

## 6. Review and RRI

Preferred umbrellas:

```bash
mql5-review --lens eng
mql5-review --lens ceo
mql5-review --lens cso
mql5-review --lens investigate

mql5-rri template
mql5-rri bt ...
mql5-rri rr ...
mql5-rri chart ...
```

Legacy lens/matrix aliases remain for compatibility and forward to the shared implementation.

## 7. Evidence and release primitives

```text
mql5-evidence-attestation
mql5-agent-contract
mql5-manifest
mql5-release-approve
mql5-completion-report
mql5-verify-report
mql5-escalation
```

The canonical release predicate is intentionally fail-closed. A valid hash chain, imported tester XML or compile source label alone is not enough to claim release eligibility.

## 8. `vkmql-ship`

Dry-run the release predicate:

```bash
vkmql-ship release --out-dir ./MyEA --dry-run
```

A real release operation proceeds only when the evidence manifest is release-eligible and the canonical provenance validator agrees.

The current ship command packages/signs an auditable hand-off; end-user ship logic does not perform maintainer repository tag/push operations.

## 9. Internal / compatibility commands

The package keeps internal shims such as catalog/selftest and deprecated umbrella aliases so older automation does not break abruptly. They are not recommended as the starting point for new user flows.

`mql5-compile-runner` is a compatibility/evidence wrapper. It delegates local/Wine compile truth to the canonical compiler and retains the remote-worker evidence path; it is **not** a second independent compile-policy implementation.

## 10. JSON/gate reports

Many verification tools support machine-readable output through `--json`, and gate-capable tools may support `--gate-report <path>`. Use those outputs for orchestration rather than scraping human text.

The exact flag set is defined by each command's `--help` and its machine-readable catalog entry.

## 11. Discover the full 139-entry catalog

The prose guide intentionally does not duplicate 139 detailed command specifications. To inspect the installed truth:

```bash
mql5-manifest --validate tool-catalog.json
mql5-selftest
```

For source checkout development, `pyproject.toml [project.scripts]` and `tool-catalog.json` must agree; selftest enforces that invariant.

## 12. VibecodeV5 lifecycle mapping

```text
SCAN      → discovery / deep review
RRI       → RRI/review/risk tools
SPECIFY   → spec/IR intake
DECIDE    → decision ledger / architecture choice
CONTRACT  → vkmql-new contract
PLAN      → TIP/task graph
BUILD     → build/IR-build/auto-build
VERIFY    → lint/compile/test/review
EVIDENCE  → manifest/attestation/provenance
RETRO     → retro guards / post-milestone learning
```

See `DOC-MAP.md` for the canonical owner of each documentation topic.
