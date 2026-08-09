# Documentation map — which file should I read?

This kit ships four large, overlapping guides that grew independently. Roughly
149 KB of their content is duplicated. Rather than mechanically merge them —
which would break every existing deep link and risk dropping content that only
exists in one copy — this release declares a **canonical source per topic** and
keeps the others as recognised aliases, scheduled for consolidation in a
docs-only release.

Being explicit about the duplication is the honest interim step; pretending it
is already fixed would not be.

## Start here

| You want to… | Read | Size |
| --- | --- | --- |
| Get running in 10 minutes | `QUICKSTART.md` | 6.7 KB |
| Look up a specific command | `COMMANDS.md` | 27 KB |
| Understand the whole workflow (English) | `USAGE-en.md` | 55 KB |
| Understand the whole workflow (Tiếng Việt) | `HUONG-DAN-TOAN-TAP-vi.md` | 33 KB |

## Canonical source per topic

| Topic | Canonical | Also appears in (duplicate) |
| --- | --- | --- |
| Command reference | `COMMANDS.md` | `USAGE-en.md`, `USER-GUIDE-en.md` |
| Install & first build | `QUICKSTART.md` | `USAGE-en.md`, `HUONG-DAN-TOAN-TAP-vi.md` |
| Governance & Triangle of Power | `V3-GOVERNANCE.md` | `USAGE-en.md` |
| Release policy & gates | `RELEASE-POLICY.md` | `USAGE-en.md`, `USER-GUIDE-en.md` |
| Runner key & trust root | `RELEASE-TRUST.md` | — (new, no duplicate) |
| Retro guards A1–A14 | `RETRO-GUARDS.md` | `USAGE-en.md` |
| UI / panel governance | `UI-PANEL-GOVERNANCE.md` | `USAGE-en.md` |
| Anti-patterns | `anti-patterns-AVOID.md` | `USAGE-en.md` |

When two documents disagree, **the canonical file wins**. If you find a
contradiction, that is a defect — the canonical file should be corrected and the
duplicate updated or removed.

## Known duplication debt

| File | Size | Status |
| --- | --- | --- |
| `USAGE-en.md` | 55.7 KB | Superset; slated to become a topic index |
| `HUONG-DAN-TOAN-TAP-vi.md` | 33.2 KB | Vietnamese full guide; keep, deduplicate against canon |
| `USER-GUIDE-en.md` | 33.0 KB | Largely subsumed by `USAGE-en.md`; merge candidate |
| `COMMANDS.md` | 27.7 KB | Canonical command reference; keep |

Deferred deliberately: consolidating these is a content edit, not a code fix,
and doing it in the same release as a security change would make both harder to
review.
