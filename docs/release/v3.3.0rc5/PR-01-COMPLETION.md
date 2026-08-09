# PR-01 Completion Report — worker artifact security

Plan ID: `VCK-RC5-HARDENING-V1`

Task: `01 — Worker artifact security`

Date: `2026-08-09`

Status: `DONE — WAVE 0 CONTINUES`

Release eligible: `false`

## Outcome

Worker artifact metadata can no longer select a path outside the caller's
destination, traverse through a symlink, or expose partially verified files.
Every declared artifact is downloaded into an isolated transaction directory
and verified by SHA-256 and byte size before any destination file changes.

## Security invariants delivered

- Reject empty, absolute, POSIX traversal, Windows drive, UNC, alternate-stream
  and ambiguous path-segment spellings.
- Normalize path separators before duplicate detection.
- Validate artifact metadata before invoking the transport.
- Reject symlinks in mock source paths and destination paths.
- Require every declared artifact to match, including artifacts marked
  optional when the worker nevertheless declares them in its result.
- Stage all downloads before commit.
- Replace each file atomically and restore all original destination files if a
  later commit operation fails.
- URL-encode validated path segments without changing their logical identity.

## Verification

| Gate | Result |
|---|---|
| Targeted worker security tests | 18/18 PASS |
| `worker_protocol.py` coverage | 98% |
| `remote_worker_client.py` coverage | 93% |
| Combined focused coverage | 94.87% — target 90% PASS |
| Full RC5 source regression | 144/144 PASS; 0 skipped |
| RC5 selftest | 13/13 PASS |
| Ruff on touched code/tests | PASS |

The tests exercise successful nested downloads, POSIX and cross-platform
Windows traversal spellings, source/destination symlinks, duplicate normalized
paths, optional-artifact corruption, hash/size mismatch, URL encoding and a
simulated failure during the fourth commit operation to prove rollback.

## Deferred scope

No intake, audit or generated MQL5 runtime behavior changed in this task.
Native MetaEditor and MT5 evidence remain Release Task 10 gates.

## Gate

Wave 0 authorization remains active for Task 02 only. Complete the canonical
EA-IR quickstart, then stop for owner review before Wave 1.
