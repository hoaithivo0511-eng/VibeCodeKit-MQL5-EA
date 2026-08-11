# VibeCodeKit-MQL5-EA

Hardening repository for **VibeCodeKit MQL5 EA v3.3.0rc6**. Task 17 has frozen
a deterministic fail-closed candidate from the active `tool/source/` tree. It
is not a production release until trusted native evidence is bound and the
Task 19 promotion predicate passes.

> Release status: **candidate-integrated / `release_eligible=false`**. RC4 and
> RC5 artifacts remain historical inputs. RC6 package parity is complete;
> production eligibility is blocked on trusted MetaEditor, MT5 Strategy Tester
> and restart/recovery evidence.

## Repository layout

| Path | Purpose |
|---|---|
| `tool/source/` | Active v3.3.0rc6 hardening source; candidate artifacts are generated only after implementation gates pass. |
| `tool/*.whl` | Historical RC4/RC5 wheels and the separately named RC6 candidate wheel after Task 17. |
| `tool/*-source-full.zip` | Historical RC4/RC5 archives and the separately named RC6 source candidate after Task 17. |
| `demo/` | CCBSN golden fixture and generic cross-project acceptance fixtures. CCBSN is test evidence, not a default template. |
| `reports/` | Historical evidence; RC6 evidence must be regenerated and must not reuse these verdicts. |
| `native/` | Native MetaEditor / MT5 validation handoff and Windows worker material. |
| `docs/release/` | Immutable RC4/RC5 history plus the active RC6 plan, ledgers and native runbook. |
| `docs/maintenance/` | Historical/maintenance repository procedures, separated from user-facing release documentation. |
| `scripts/maintenance/` | Repository-maintenance helpers. They do not commit or push automatically. |
| `.github/workflows/` | Deterministic CI release gates for source regression, artifact parity and repository hygiene. |

See `STRUCTURE.md` for the release-oriented tree policy. File counts are deliberately not hard-coded in this README; `REPO-MANIFEST.sha256` is the authoritative repository integrity inventory after release-prep is finalized.

## Frozen RC4 deterministic status

The audited RC4 package reports:

| Gate | Status |
|---|---|
| Source regression | 126/126 PASS |
| Source selftest | 13/13 PASS |
| Wheel regression | 126/126 PASS |
| Wheel selftest | 13/13 PASS |
| Source archive regression | 126/126 PASS |
| Generic cross-project acceptance | 4/4 PASS |
| MetaEditor native compile | PENDING / not proven in this repository environment |
| MT5 Strategy Tester | PENDING / not proven in this repository environment |
| Production release eligibility | **false until native evidence exists** |

Historical coverage evidence records package-wide statement coverage at 18.23%; high-value modules are substantially higher. Coverage is a maintainability metric, not proof of trading correctness.

## Fixed RC4 artifact identities

These hashes are frozen for the RC4 artifact set. RC6 work must not silently
change or overwrite them:

```text
33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip
a8e091caf35b59fbf436d10c5c8e1dc0414d3e355d029162295192c02029566f  tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip
5945a91c9f2b74ee3bbe3a7977991445d3e95885e396c3f95a14262ac8eb127a  tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl
```

The RC4 and RC5 artifacts remain immutable. The active RC6 `tool/source/` tree
is frozen for Task 17 at source tree
`53b8c6aad2fde6a0b0b8d6f61e2da4f6d7df20f6`; the RC6 source ZIP and wheel
passed identical 252-test suites and 13/13 selftests in all three channels.

## RC6 fail-closed candidate identities

```text
3bc4ce857613c7f82f2aecb0648b84e1971939f282a1fd056d93440d21305059  tool/vibecodekit-mql5-v3.3.0rc6-source-full.zip
a2ba69f0b568d7362017d3e81f28feea80ddb71f33494989089c4669136578d6  tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
f13cc038ce6187543e6e556b257ec109990a3646c3c16eea8ca67489c1ac9396  VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip
```

These hashes identify a package-integrated candidate, not a production
release. `release_eligible` remains `false` until Task 18 and Task 19 pass.

## Local deterministic verification

```bash
# Source tests
cd tool/source
python -m pip install -e '.[dev]'
python -m pytest -q
mql5-selftest
cd ../..

# Fixed artifact hashes
printf '%s  %s\n' \
  33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c \
  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip | sha256sum -c -
```

GitHub Actions runs RC6 source regression independently from frozen RC4
artifact integrity. The RC6 package-integration workflow verifies canonical
snapshot, reproducible wheel, source/archive/wheel parity and fail-closed
candidate metadata.

## Safety and release semantics

`tool/source/DRAFT-NOT-VALIDATED.txt` is retained intentionally and warns that
**draft artifacts produced by the tool are not automatically
compiled/gated/validated**.

Do not treat a generated EA as production-ready without real MetaEditor compilation, broker/environment checks and MT5 Strategy Tester evidence. No `.ex5` is tracked by default; native outputs belong in signed/attested release evidence or GitHub Release assets.

## License

MIT. The root `LICENSE` is identical to `tool/source/LICENSE`.
