# Repository structure — v3.3.0rc6 hardening line

This map describes the **role** of each repository area rather than embedding file/byte counts that become stale after maintenance commits.

```text
/
├── .github/workflows/          deterministic CI release gates
├── demo/                       golden + generic acceptance fixtures
├── docs/
│   ├── maintenance/            repository bootstrap/maintenance history
│   └── release/                 immutable RC4/RC5 history + active RC6 plan
├── native/                     MetaEditor/MT5 native-validation handoff
├── reports/                    historical RC4 audit/test evidence
├── scripts/maintenance/        safe repository-maintenance helpers
├── tool/
│   ├── source/                 active RC6 hardening source
│   ├── *-source-full.zip       versioned frozen/candidate source archives
│   ├── *.whl                   versioned frozen/candidate wheels
│   └── *.manifest.json         distribution manifest
├── BUNDLE-MANIFEST.json        immutable RC4 bundle manifest
├── SHA256SUMS.txt              immutable RC4 bundle checksum set
├── REPO-MANIFEST.sha256        repository-level integrity inventory
├── README.md                   hardening/release overview
└── LICENSE                     MIT license, identical to packaged source
```

## Integrity boundaries

### Canonical RC4 artifact boundary

The following remain frozen historical RC4 artifacts throughout RC6 hardening:

- `VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip`
- `tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip`
- `tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl`
- original bundle evidence in `BUNDLE-MANIFEST.json` and `SHA256SUMS.txt`

They must never be overwritten by RC6 outputs. RC5 candidate/SHIP files are
also retained as historical inputs. The active `tool/source/` tree is allowed
to change on the RC6 branch; RC6 artifacts receive new filenames, hashes,
manifests and a full regression cycle.

### Repository-maintenance boundary

The following may change during reviewed RC6 development, provided repository
integrity metadata is regenerated afterward:

- root README/structure/license/ignore policy;
- `.github/workflows/`;
- `docs/maintenance/`;
- `docs/release/`;
- `scripts/maintenance/`;
- release-prep reports and repository-level manifest.
- `tool/source/`, until the RC6 Task 17 candidate is frozen.

## Generated/native outputs

Python caches, local virtual environments, coverage output, editor/OS noise, temporary patch files, `.ex5` binaries and local logs are excluded by `.gitignore`. Native deliverables should be attached to a release/evidence set only after provenance and native validation are available.

## Release status

RC6 may pass deterministic source/static/package gates while still being **not
production-release eligible**. Task 18 native MetaEditor compilation, MT5
Strategy Tester and restart/recovery evidence remain independent gates; do not
infer them from static or Python regression success.
