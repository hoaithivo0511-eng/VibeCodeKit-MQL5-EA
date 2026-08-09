# VibeCodeKit-MQL5-EA

Release-candidate repository for **VibeCodeKit MQL5 EA v3.3.0rc4** (`runtime-safety-fix`). It contains the canonical packaged source, installable wheel, source archive, deterministic test evidence, demo/golden fixtures, and the native-validation handoff needed before production release.

> Release status: **pre-release candidate only**. Deterministic Python/static gates have passed in the audited build, but native MetaEditor compile and MT5 Strategy Tester evidence are still pending. The current release metadata therefore remains `release_eligible=false`.

## Repository layout

| Path | Purpose |
|---|---|
| `tool/source/` | Canonical expanded v3.3.0rc4 source tree. It is intentionally kept byte-identical to `tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip`. |
| `tool/*.whl` | Installable Python package for VibeCodeKit MQL5 EA. |
| `tool/*-source-full.zip` | Canonical source archive used for distribution/parity checks. |
| `demo/` | CCBSN golden fixture and generic cross-project acceptance fixtures. CCBSN is test evidence, not a default template. |
| `reports/` | Static analysis, coverage, deep-review, regression and acceptance evidence from the RC4 build. |
| `native/` | Native MetaEditor / MT5 validation handoff and Windows worker material. |
| `docs/release/` | Release-preparation plan and final release-prep report. |
| `docs/maintenance/` | Historical/maintenance repository procedures, separated from user-facing release documentation. |
| `scripts/maintenance/` | Repository-maintenance helpers. They do not commit or push automatically. |
| `.github/workflows/` | Deterministic CI release gates for source regression, artifact parity and repository hygiene. |

See `STRUCTURE.md` for the release-oriented tree policy. File counts are deliberately not hard-coded in this README; `REPO-MANIFEST.sha256` is the authoritative repository integrity inventory after release-prep is finalized.

## RC4 deterministic status

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

These hashes are frozen for the RC4 artifact set. Repository-only cleanup must not silently change them:

```text
33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip
a8e091caf35b59fbf436d10c5c8e1dc0414d3e355d029162295192c02029566f  tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip
5945a91c9f2b74ee3bbe3a7977991445d3e95885e396c3f95a14262ac8eb127a  tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl
```

The expanded `tool/source/` tree must also remain byte-identical to every non-directory member of the source ZIP.

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
  33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6 \
  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip | sha256sum -c -
```

GitHub Actions runs the corresponding source-regression, source/archive parity, wheel selftest and repository-hygiene gates.

## Safety and release semantics

`tool/source/DRAFT-NOT-VALIDATED.txt` is retained intentionally because it is part of the canonical source archive and warns that **draft artifacts produced by the tool are not automatically compiled/gated/validated**. It does not mean the RC4 source itself has never been tested.

Do not treat a generated EA as production-ready without real MetaEditor compilation, broker/environment checks and MT5 Strategy Tester evidence. No `.ex5` is tracked by default; native outputs belong in signed/attested release evidence or GitHub Release assets.

## License

MIT. The root `LICENSE` is identical to `tool/source/LICENSE`.
