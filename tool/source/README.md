# VibeCodeKit MQL5 EA — v3.3.0rc7

Canonical executable/package source for the current integrated RC7 line.

## Supported operator surface

```text
vkmql-new
vkmql-check
vkmql-ship
mql5-ea-deep-review
mql5-doctor
```

The package also exposes 139 total console entrypoints for advanced/internal/compatibility use. `tool-catalog.json` and `[project.scripts]` in `pyproject.toml` are the machine-readable source of truth.

## Install from this source tree

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'

mql5-doctor --soft
mql5-selftest
```

## VibecodeV5 workflow

```text
SCAN → RRI → SPECIFY → DECIDE → CONTRACT → PLAN → BUILD → VERIFY → EVIDENCE → RETRO
```

Scale the workflow to the task. Full release/native/risk changes require stronger evidence than a small static fix.

## Compile

Canonical frontend:

```bash
vkmql-check compile <target.mq5> --backend auto
```

Auto backend preference:

```text
local Windows MetaEditor
→ GitHub Actions Windows
→ remote Windows worker
→ Wine MetaEditor (development/diagnostic)
→ UNTESTABLE
```

Compile policy:

- MetaEditor log must contain `Result:`;
- default requires `0 errors, 0 warnings`;
- `.ex5` must exist;
- stale log/EX5 is removed before compile;
- process exit code alone is not compile success authority;
- backend-specific provenance/hashes are validated.

GitHub native details: `docs/GITHUB-NATIVE-COMPILE-vi.md`.

`mql5-compile-runner` remains a compatibility/evidence wrapper; local/Wine compile truth is delegated to the canonical compile implementation.

## Full gate

```bash
vkmql-check all <project-dir>
vkmql-check all <project-dir> --require-release
```

Every stage is one of:

```text
PASS | FAIL | UNTESTABLE | SKIPPED
```

`UNTESTABLE` never becomes release-positive merely because source/static checks pass.

## Release semantics

Native compile does not imply:

```text
Strategy Tester
restart/recovery
broker parity
walk-forward / forward
live readiness
```

`vkmql-ship release` validates the release manifest and canonical provenance before package/sign hand-off. It does not turn missing evidence into a release.

## Package verification

The RC7 package gate verifies:

- full source regression/selftest;
- deterministic wheel rebuild;
- clean installed-wheel execution outside checkout;
- synchronized distribution snapshot;
- fail-closed pre-candidate artefact handling.

The installed-wheel verification snapshot lives at:

```text
scripts/vibecodekit_mql5/resources/distribution/
```

That directory intentionally mirrors selected source tests/contracts and should not be deduplicated as build trash.

## Documentation

Start with:

- `docs/QUICKSTART.md`;
- `docs/HUONG-DAN-TOAN-TAP-vi.md`;
- `docs/USAGE-en.md`;
- `docs/USER-GUIDE-en.md`;
- `docs/COMMANDS.md`;
- `docs/DOC-MAP.md`;
- `docs/GITHUB-NATIVE-COMPILE-vi.md`.

Historical HTML reports in `docs/` retain their original point-in-time versions/test counts and are not the current RC7 verdict.

## Current source vs published release

This source tree is `3.3.0rc7`. The latest published repository tester pre-release may still be `v3.3.0rc6`; source integration and release promotion are separate states.

See repository-level `docs/release/v3.3.0rc7/` for the current RC7 audit/status ledger.
