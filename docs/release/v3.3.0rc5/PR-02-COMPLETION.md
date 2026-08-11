# PR-02 Completion Report — canonical EA-IR quickstart

Plan ID: `VCK-RC5-HARDENING-V1`

Task: `02 — Canonical EA-IR quickstart`

Date: `2026-08-09`

Status: `DONE — OWNER REVIEW REQUIRED`

Release eligible: `false`

## Outcome

`mql5-spec-from-prompt` now emits a complete canonical EA-IR 3.1 document by
default. The resulting JSON is accepted directly by `mql5-auto-build` and
preserves identity, runtime, strategy, risk, controls, requirement evidence,
ambiguities, conflicts and the canonical IR hash.

The older single-preset YAML is available only through `--legacy`. It carries
an explicit non-release compatibility marker which the build pipeline records
as `--legacy-scaffold` and which the release predicate treats as a blocker.

## Invariants delivered

- Default output is canonical EA-IR; `--ir` remains a compatibility alias.
- Legacy output requires `--legacy` and is never selected implicitly.
- Legacy YAML has no fake EA-IR `schema_version` and declares:

  ```yaml
  compatibility:
    mode: legacy_scaffold
    release_eligible: false
  ```

- The legacy schema validator rejects any attempt to set that marker true.
- The EA-IR loader rejects legacy top-level fields even if
  `schema_version: "3.1"` is added manually.
- `mql5-auto-build` propagates the legacy marker into unsafe/release-blocking
  flags.
- Tool catalogs and user quickstarts describe the JSON-default behavior.

## Verification

| Gate | Result |
|---|---|
| Focused prompt/auto-build tests | 20/20 PASS |
| `spec_from_prompt.py` coverage | 94% — target 80% PASS |
| `auto_build.py` coverage | 84% — target 75% PASS |
| Focused combined coverage | 88.09% |
| Installed CLI `prompt → EA-IR → auto-build` | PASS; `source_complete=true` |
| Full Wave 0 source regression | 159/159 PASS; 0 skipped |
| RC5 selftest | 13/13 PASS |
| Ruff on touched modules and mirrored tests | PASS |

The installed CLI smoke generated `CliTrend` from a strict prompt and emitted
the MT5-native `Experts/CliTrend/CliTrend.mq5` tree. Native compile and gate
steps were intentionally skipped, and `release_eligible` remained false.

## Deferred scope

Task 02 does not change input/sinput parsing, audit stages or generated MQL5
runtime behavior. Those remain Wave 1 and Wave 2 tasks.

## Owner gate

Wave 0 is complete. Stop here until the owner explicitly approves Wave 1 or
names the next task.
