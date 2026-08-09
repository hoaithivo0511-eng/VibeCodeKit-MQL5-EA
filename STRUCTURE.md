# Repository structure — v3.3.0rc4 release candidate

This map describes the **role** of each repository area rather than embedding file/byte counts that become stale after maintenance commits.

```text
/
├── .github/workflows/          deterministic CI release gates
├── demo/                       golden + generic acceptance fixtures
├── docs/
│   ├── maintenance/            repository bootstrap/maintenance history
│   └── release/v3.3.0rc4/      phased release-prep plan and final report
├── native/                     MetaEditor/MT5 native-validation handoff
├── reports/                    existing RC4 audit/test evidence
├── scripts/maintenance/        safe repository-maintenance helpers
├── tool/
│   ├── source/                 expanded canonical source (605 files)
│   ├── *-source-full.zip       canonical source archive
│   ├── *.whl                   installable package
│   └── *.manifest.json         distribution manifest
├── BUNDLE-MANIFEST.json        immutable original bundle manifest
├── SHA256SUMS.txt              immutable original bundle checksum set
├── REPO-MANIFEST.sha256        repository-level integrity inventory
├── README.md                   release-candidate overview
└── LICENSE                     MIT license, identical to packaged source
```

## Integrity boundaries

### Canonical RC4 artifact boundary

The following are treated as frozen release-candidate artifacts during repository-only cleanup:

- `VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip`
- `tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip`
- `tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl`
- `tool/source/` expanded contents
- original bundle evidence in `BUNDLE-MANIFEST.json` and `SHA256SUMS.txt`

Changing any of these requires a deliberate package rebuild, new hashes and a full regression cycle. Release-prep documentation cleanup alone must not mutate them.

### Repository-maintenance boundary

The following may change without rebuilding the canonical package, provided repository integrity metadata is regenerated afterward:

- root README/structure/license/ignore policy;
- `.github/workflows/`;
- `docs/maintenance/`;
- `docs/release/`;
- `scripts/maintenance/`;
- release-prep reports and repository-level manifest.

## Generated/native outputs

Python caches, local virtual environments, coverage output, editor/OS noise, temporary patch files, `.ex5` binaries and local logs are excluded by `.gitignore`. Native deliverables should be attached to a release/evidence set only after provenance and native validation are available.

## Release status

The RC4 repository may pass deterministic source/static/package gates while still being **not production-release eligible**. Native MetaEditor compilation and MT5 Strategy Tester evidence remain independent gates; do not infer them from static or Python regression success.
