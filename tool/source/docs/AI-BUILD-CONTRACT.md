---
id: ai-build-contract
title: AI-BUILD-CONTRACT (v3; v2.6-compatible)
---

# AI-BUILD-CONTRACT v3 (v2.6-compatible)

The AI-BUILD-CONTRACT is the guard-rail an AI coding tool (Claude Code, Codex,
Cursor, …) must obey while implementing an EA from its `EA-SPEC.yaml`. It is
generated per project and exists in two forms:

- `AI-BUILD-CONTRACT.md` — human-readable contract.
- `AI-BUILD-CONTRACT.json` — machine-readable contract for `vkmql-check contract`.

Generate / validate it with:

```bash
mql5-ai-build-contract <project_dir>          # generate .md + .json
vkmql-check contract <project_dir>            # validate the project against it
```

## What the contract pins

### Allowed paths (editable by the AI)

```text
Experts/
Include/
Presets/
Tester/
```

### Forbidden paths (never hand-edited)

```text
evidence/
release/
evidence/manifest.json
evidence/attestation/*
release/ship-manifest.json
```

`evidence/` and `release/` are **always** forbidden. Evidence is produced only
by the toolkit, never written by the AI — otherwise the hash chain is
meaningless.

### Forbidden claims

The AI may never write any of these into docs/code/reports unless the project
is genuinely `RELEASE-ELIGIBLE` with a valid evidence hash chain:

```text
READY
LIVE-READY
PRODUCTION-READY
```

### Forbidden behaviours

```text
- Adding a feature that is not in EA-SPEC.
- Silently changing a risk rule.
- Removing a stop loss.
- Adding martingale / grid / DCA when the spec forbids it.
- Claiming PASS/READY/LIVE before evidence exists.
```

## Validation rules (`validate_ai_build_contract`)

| Check | Result on failure |
| --- | --- |
| EA-SPEC present + valid (`spec_schema_v26`) | invalid |
| `risk` section present (incl. `max_drawdown_pct`) | invalid |
| `evidence/` or `release/` listed as editable | invalid |
| Forbidden ready-claims missing from contract | invalid |
| Modified file outside allowed paths (report-time) | warning |

The contract checker reuses `spec_schema_v26` for spec validation — it does not
re-implement its own schema (anti-bloat rule #4).
