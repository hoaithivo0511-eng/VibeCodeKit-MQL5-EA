# VibeCodeKit-MQL5-EA

Hardening repository for **VibeCodeKit MQL5 EA v3.3.0rc6**. The active
`tool/source/` tree supersedes the retained RC5 candidate and is not a release
artifact until the RC6 candidate is rebuilt, regression-tested and bound to
fresh evidence.

> Release status: **hardening / `release_eligible=false`**. RC4 and RC5
> artifacts remain historical inputs. RC6 production eligibility is blocked
> until candidate parity and trusted MetaEditor, MT5 Strategy Tester and
> restart/recovery evidence all pass.

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
is intentionally allowed to diverge; Task 17 establishes new source ZIP and
wheel parity under RC6-specific filenames.

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
