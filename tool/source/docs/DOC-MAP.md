# Documentation map — v3.3.0rc7

This map defines the **current documentation authority** for the integrated RC7 source line. Historical versioned reports remain point-in-time evidence and do not override current docs.

## Start here

| Goal | Read | Role |
| --- | --- | --- |
| Get from install to first honest compile/gate | `QUICKSTART.md` | Canonical quickstart |
| Understand the full workflow in Vietnamese | `HUONG-DAN-TOAN-TAP-vi.md` | Vietnamese master guide |
| Understand the RC7 operating model in English | `USAGE-en.md` | English operating guide |
| Follow an EA build step by step in English | `USER-GUIDE-en.md` | English step-by-step guide |
| Find supported/advanced CLI surfaces | `COMMANDS.md` | Command surface guide |
| Configure Windows native compile through GitHub Actions | `GITHUB-NATIVE-COMPILE-vi.md` | Native backend guide |

## Current source vs published release

```text
current integrated source/tool : 3.3.0rc7
latest published tester release : v3.3.0rc6
production/live release claim   : not implied by either label
```

Current RC7 audit/release truth is maintained under the repository root:

```text
docs/release/v3.3.0rc7/
```

The root `README.md` is the entry-point status summary. The versioned RC7 status ledger contains exact evidence/run identifiers.

## Canonical source per topic

| Topic | Canonical file | Notes |
| --- | --- | --- |
| VibecodeV5 lifecycle | `HUONG-DAN-TOAN-TAP-vi.md` | 10 steps: SCAN → RRI → SPECIFY → DECIDE → CONTRACT → PLAN → BUILD → VERIFY → EVIDENCE → RETRO |
| Short onboarding | `QUICKSTART.md` | Leads with high-level commands and honest environment gaps |
| English operating model | `USAGE-en.md` | Thin RC7 operator guide; does not duplicate the whole command catalog |
| English walkthrough | `USER-GUIDE-en.md` | Concrete project flow and evidence checkpoints |
| CLI surface | `COMMANDS.md` | Public umbrellas first; `tool-catalog.json` is machine-readable source of truth for all 139 entrypoints |
| GitHub native compile | `GITHUB-NATIVE-COMPILE-vi.md` | Backend routing, provenance, ProbeEA, staging and release semantics |
| Release policy | `RELEASE-POLICY.md` | Generic release gates and fail-closed semantics |
| Runner trust root | `RELEASE-TRUST.md` | External/native runner key trust |
| Retro guards | `RETRO-GUARDS.md` | Runtime engineering guardrails |
| UI/panel governance | `UI-PANEL-GOVERNANCE.md` | UI-specific rules |
| Anti-patterns | `anti-patterns-AVOID.md` | Static/design anti-pattern guidance |

When two active documents disagree, the canonical file for that topic wins. Treat the contradiction as a documentation defect rather than choosing whichever claim is more convenient.

## Machine-readable truth

Do not infer command availability from prose alone.

```text
tool/source/pyproject.toml
tool/source/tool-catalog.json
tool/source/agent-contract.json
```

Current RC7 catalog has 139 console entrypoints. The normal user surface is intentionally much smaller.

## Historical snapshots

The following are retained as immutable point-in-time reports:

- `E2E-AUDIT-REPORT.html`;
- `UI-E2E-REPORT.html`;
- `OPUS-AUDIT-CROSSCHECK-R2.html`;
- versioned changelogs/delivery/fix reports from older releases.

Their embedded versions and test counts describe the historical run that generated them. They are **not** the current RC7 release verdict.

## Historical release ledgers

`docs/release/v3.3.0rc4/`, `v3.3.0rc5/` and `v3.3.0rc6/` remain historical release evidence. Do not rewrite them to make prior releases appear to have used RC7 logic.

## Documentation duplication policy

Earlier releases allowed several large guides to independently repeat the same install/workflow/command text. That made version and lifecycle drift likely.

RC7 direction:

- keep one master guide per language/purpose;
- keep `COMMANDS.md` focused on command discovery and support tiers;
- keep `QUICKSTART.md` short;
- keep historical reports immutable;
- link to canonical topic owners instead of copying whole sections;
- validate active docs for current version/workflow/backend semantics in regression tests.

## Runtime truth boundary

No documentation may turn:

```text
native compile PASS
```

into:

```text
Strategy Tester PASS
restart/recovery PASS
broker parity PASS
forward/live PASS
```

without the corresponding trusted evidence. Missing environment/evidence is `UNTESTABLE`/`INCOMPLETE`, not a successful release gate.
