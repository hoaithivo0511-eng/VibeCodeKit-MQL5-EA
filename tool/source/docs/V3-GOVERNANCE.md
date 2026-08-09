# VibeCodeKit MQL5 v3 Governance

## Contents

- [Purpose](#purpose)
- [Modes](#modes)
- [Approval and semantic changes](#approval-and-semantic-changes)
- [Release authority](#release-authority)
- [Evidence and telemetry](#evidence-and-telemetry)
- [Compatibility](#compatibility)

## Purpose

v3 composes the v5.1 cognitive workflow with the v2.6 MQL5 runtime. The skill
router proposes and scopes work; the runtime gates verify code and evidence.
Neither layer may invent a release result.

## Modes

| Mode | Allowed scope | Backtest |
| --- | --- | --- |
| Lite | docs, comments, display-only UI, proven behavior-preserving refactor | not required unless behavior cannot be proven unchanged |
| Standard | bounded module, indicator or strategy change | required when behavior/risk changes |
| Full | new EA, risk/execution, architecture, porting, forward/live | required, plus stress/forward gates as applicable |

Lite automatically promotes when entry/exit, risk, units, order lifecycle,
retry, persistence, broker behavior or generated signals may change.

## Approval and semantic changes

`EA-SPEC.yaml` is the semantic source of truth after approval. An agent may
update only formatting, timestamps, generated IDs, hashes, paths and explicitly
derived fields. A semantic change creates a change request in the Decision
Ledger and waits for owner approval.

The following records are intentionally separate:

- `DECISIONS.yaml`: intent and owner decisions;
- `EVIDENCE_MANIFEST.json`: commands, environment and artefact hashes;
- `OWNER_APPROVAL.json`: human approval bound to exact build/evidence hashes.

## Release authority

- Windows-native MetaEditor/MT5 is release-authoritative for the initial product.
- Wine is development/CI evidence unless a parity policy says otherwise.
- `LIVE_ELIGIBLE` requires real-environment gates and owner approval; it is not
  a profitability or safety guarantee.
- ONNX is an optional plugin. Stub models and inconsistent action labels are
  not valid inference evidence.
- MCP is internal/experimental until its schemas and command catalog stabilize.

## Evidence and telemetry

Evidence is local by default. Remote storage is optional and must redact or
encrypt source, strategy parameters, account/broker identifiers, trade history,
logs, paths, signatures and secrets.

Telemetry is off by default. Anonymous opt-in may send only version, broad OS,
canonical command, duration, mode and sanitized status/error code.

### Canonical provenance gate

`evidence/manifest.json` is release-valid only when schema `2.0` contains
trusted execution provenance for both compile and backtest (`source`, command,
tool version, host and UTC timestamp), hashes for every core artifact, a
non-empty MT5 report with metrics, and an independently verified hash chain.
File presence, imported logs, fixture reports, fake EX5 bytes, or Wine-only
compile evidence remain non-release evidence. `check_all` and the attestation
CLI call the same validator so a side command cannot produce a stronger result
than the aggregate gate.

## Compatibility

Existing v2.6 specs remain valid. v3 fields are additive under `governance`
and `release`; old high-level `vkmql-*` commands continue to work. The command
catalog is generated from `pyproject.toml` rather than maintained by hand.
