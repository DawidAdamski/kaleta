---
plan_id: import-multi-file-queue
title: Import — multi-file queue
area: import
effort: medium
status: archived
archived_at: 2026-04-23
roadmap_ref: ../roadmap.md#import
---

# Import — multi-file queue

## Intent

Power users typically have multiple statements (several banks, a
credit card, Revolut) at month end. Today they must import one at a
time. Let them drop N files at once and work through a queue.

## Scope

- Drop zone accepts multiple files.
- Queue panel on the right: pending / in-progress / done / failed.
- Active file drives the main mapping / preview panel. Clicking
  another file in the queue swaps focus (with "save draft mapping"
  for the previous file so the user doesn't lose work).
- Same-institution files auto-inherit the mapping from the first one.
- On finish of the last file: summary screen (N imported, M
  duplicates skipped, K errors).

Out of scope:
- Parallel import workers — sequential is fine for v1.
- ZIP expansion — user uploads individual files.

## Acceptance criteria

- Drop 3 CSVs from 3 different banks → all 3 appear in the queue.
- Finishing file 1 advances focus to file 2 automatically.
- Switching back to file 1 mid-flow restores its draft mapping.
- Summary screen shows per-file counts that sum to the totals.

## Touchpoints

- `src/kaleta/views/import_view.py` — queue panel, focus switching,
  summary.
- `src/kaleta/services/import_service.py` — per-session draft
  mappings, institution fingerprint keyed to reuse mapping.
- `src/kaleta/schemas/import_.py` — queue item schema.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Persist the queue across a page refresh? v1: session-only. If the
  tab is lost so is the queue.
- Max files per batch — soft-cap 20 to protect the UI.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `2c25f1f` | Dawid | 2026-04-23 | feat(import): multi-file queue with per-file mapping and Import all |

**Files changed:**
- src/kaleta/views/import_view.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json

**What shipped:**
- Multi-file drop (`multiple=True, max_files=20`) with per-file `QueuedFile` dataclass holding profile, parsed rows, metadata, settings, status, and result counts.
- Queue panel with per-file status chips (pending / ready / importing / done / failed), theme-aware left-border highlight on the active file, and a remove button.
- All existing sections (profile / settings / preview / transfer detect) now bind to the active file; switching focus repaints from stored state — "draft mapping" is preserved implicitly.
- Settings inheritance: same-mBank-account-digits → full inherit; same-profile → categories + skip-dupes inherit.
- Import All runs the queue sequentially, stamps status per file, and renders a summary card with per-file rows and totals (imported / skipped / failed).
- mBank auto-match on upload still works per file; currency-mismatch blocking still enforced.

**Partial coverage / deferred:**
- Queue is in-memory only — tab reload loses it (matches plan's v1 open-question answer).
- Parallel import workers deferred; sequential import suffices for v1.
- ZIP expansion not added.
- No automated E2E scenario yet (manual browser verification only).
- Per-file transfer-detect button is shown but runs the global detector — a tighter per-file scope would need service changes.
