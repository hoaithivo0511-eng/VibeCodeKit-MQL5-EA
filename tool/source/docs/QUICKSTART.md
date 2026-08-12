---
id: quickstart
title: Quickstart — RC7 honest build and compile
audience: end-user
---

# Quickstart — VibeCodeKit MQL5 v3.3.0rc7

This is the shortest supported path from an unpacked kit to an honestly gated EA project.

> **Important:** a successful native compile proves compile readiness only. Backtest, restart/recovery, broker parity, forward and live stages require their own evidence.

## 1. Install

```bash
cd vibecodekit-mql5-ea
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'
```

Check the kit itself:

```bash
mql5-doctor --soft
mql5-selftest
```

`--soft` allows environment-only MT5/Wine gaps to remain warnings. It does not hide hard package/source failures.

## 2. Create project governance

```bash
vkmql-new spec ./MyEA --name MyEA --symbol EURUSD --tf H1
vkmql-new contract ./MyEA --name MyEA
```

This creates the project-level specification/contract boundary used by the aggregate gate.

If you already have an EA source tree, point the commands at that project instead of generating another scaffold.

## 3. Build or import source

For prompt/EA-IR driven generation, the advanced RC7 pipeline remains available:

```bash
mql5-spec-from-prompt \
  "EA named TrendEA, EURUSD H1, netting, risk 0.5%, trend strategy" \
  --strict --out EA-IR.json

mql5-auto-build --spec EA-IR.json --out-dir ./MyEA
```

For an existing project, skip generation and audit the existing `.mq5/.mqh` source directly.

## 4. Static verification

```bash
vkmql-check lint ./MyEA/Experts/MyEA/MyEA.mq5
mql5-ea-deep-review ./MyEA
```

Advanced static analyzers remain available through the `mql5-*` catalog, but the high-level `vkmql-*` surface should be the default operator path.

## 5. Compile — RC7 backend router

Canonical command:

```bash
vkmql-check compile ./MyEA/Experts/MyEA/MyEA.mq5 \
  --project-root ./MyEA \
  --backend auto
```

`auto` tries:

```text
1. local Windows MetaEditor
2. GitHub Actions Windows backend (when configured)
3. trusted remote Windows worker
4. Wine MetaEditor for development/diagnostic use
5. no available backend -> UNTESTABLE
```

### Explicit GitHub Actions native compile

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

The backend must bind Windows runner, repository, run/job IDs, exact commit/tree and artifact hashes. See `GITHUB-NATIVE-COMPILE-vi.md`.

### Compile truth

A compile PASS requires:

```text
MetaEditor log contains Result:
errors   = 0
warnings = 0
EX5 exists
hash/size evidence is coherent
```

The MetaEditor process exit code alone is not the success authority.

## 6. Full project gate

```bash
vkmql-check all ./MyEA
```

This is an audit-oriented run: a missing runtime environment is reported as `UNTESTABLE`, not fabricated as PASS.

For a release-mode predicate:

```bash
vkmql-check all ./MyEA --require-release
```

This exits non-zero unless every mandatory stage is release-positive.

## 7. Runtime evidence

If the EA changes trading behaviour/risk/execution, collect the required target evidence with a real MT5 environment:

```text
Strategy Tester
quality / robustness metrics
stress cases
restart / recovery
walk-forward / forward evidence
broker/profile evidence
owner/release approval
```

Parsing a sample/imported XML is useful for parser testing but is not release execution provenance.

## 8. Package / ship

`vkmql-ship release` refuses a project whose evidence manifest is not release-eligible.

```bash
vkmql-ship release --out-dir ./MyEA --dry-run
```

If the dry-run says the project is blocked, fix the named missing/failed evidence. Do not bypass the gate by renaming artifacts or marking skipped stages as successful.

## VibecodeV5 lifecycle

Use this mental model throughout the build:

```text
SCAN → RRI → SPECIFY → DECIDE → CONTRACT → PLAN → BUILD → VERIFY → EVIDENCE → RETRO
```

For a small edit, scale the ceremony down. For release/native/risk changes, use the Full path.

## Next documentation

- `HUONG-DAN-TOAN-TAP-vi.md` — Vietnamese master guide.
- `USAGE-en.md` — English operating guide.
- `USER-GUIDE-en.md` — English step-by-step flow.
- `COMMANDS.md` — command surface and advanced tools.
- `DOC-MAP.md` — canonical topic ownership.
- `GITHUB-NATIVE-COMPILE-vi.md` — native Windows GitHub backend.
