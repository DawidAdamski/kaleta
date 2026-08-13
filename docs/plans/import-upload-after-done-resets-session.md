---
plan_id: import-upload-after-done-resets-session
title: Import — dropping a file after a completed run starts a fresh session
area: import
effort: small
status: draft
roadmap_ref: ../roadmap.md#import
---

# Import — upload after a completed run starts a fresh session

## Intent

Dogfooding follow-up to `import-flow-polish` (archived). After an import
completes, the summary shows "Start new import". If the user instead
drops a new file directly: the summary (and its button) disappears, but
the finished `done` file **stays in the queue** next to the new one.
The state is safe — `do_import_all()` only imports `status == "ready"`
files (`page.py:471`) — but it *looks* like both files might import,
which erodes trust in exactly the place a finance app can't afford it.

## Root cause

- `handle_upload` hides the summary on any new upload
  (`page.py:324` `summary_section.hide()`) but never clears terminal
  files from `state["queue"]`.
- `_start_new_import()` (`page.py:208`) already does the right cleanup
  (snapshot last settings → clear queue → hide summary → reset upload
  widget) — it just isn't invoked on the upload path.

## Scope

- **Auto-reset on upload after a terminal run**: in `handle_upload`,
  when the queue is non-empty and **every** file is terminal
  (`done`/`failed`), run the `_start_new_import()` cleanup before
  enqueuing the new file. Settings inheritance is preserved — the
  cleanup already snapshots `last_settings`, and the new file inherits
  from it.
- **Mixed states stay untouched**: if any file is still
  `pending`/`ready`/`importing`, adding a file keeps today's behaviour
  (that's the legitimate "add more files to this batch" flow).
- **Failed files**: a `failed` file counts as terminal for the reset —
  but notify (`ui.notify`, info) that the previous failed file was
  cleared, so the user doesn't think it silently succeeded. The
  completed run remains visible in the "Recent imports" history
  (`ImportRun`, shipped in `import-history-account-coverage`) — nothing
  is lost, it just stops masquerading as pending work.
- **Extract the terminal-state check** as a pure helper
  (`queue_is_terminal(queue) -> bool`) so it is unit-testable.
- **BDD**: extend Feature: mBank CSV Import with the next free KAL-CSV
  ID (`grep -o "KAL-CSV-[0-9]*" docs/bdd.md | sort -u` — expected
  KAL-CSV-013): dropping a file after a completed run starts a clean
  queue containing only the new file. Tag `@automated` — the e2e ships
  in this PR.

Out of scope: multi-batch queue history inside the page (the Recent
imports section already covers it), changes to `do_import_all`
eligibility (already correct).

## Tests (same PR as the implementation)

Unit (`tests/unit/`):

1. `queue_is_terminal`: empty queue → False; all done → True; done +
   failed → True; done + ready → False; importing present → False.

E2E (`tests/e2e/test_csv_import.py`, docstring `Covers:` the new ID):

2. Import file A to completion; without clicking "Start new import",
   upload file B: the queue shows **only** file B, the import button
   reads "Import 1 file", and importing yields exactly file B's rows
   (file A's transactions not duplicated — assert ledger count).
3. Regression: upload two files back-to-back *before* importing —
   both stay in the queue (mixed-state flow unchanged, existing
   multi-file e2e stays green).

## Acceptance criteria

- `uv run pytest tests/unit -q`
- `uv run pytest tests/e2e/test_csv_import.py -q`
- `grep -q "KAL-CSV-013" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Flow from the bug report: import → drop new file without
  clicking the button → no stale done-file in the queue, no ambiguity
  about what the import button will do.

## Touchpoints

- `src/kaleta/views/import_view/page.py` (`handle_upload`,
  `_start_new_import` reuse), `state.py` (helper)
- `src/kaleta/i18n/locales/en.json` + `pl.json` (cleared-failed notify)
- `docs/bdd.md` (KAL-CSV-013)
- `tests/unit/`, `tests/e2e/test_csv_import.py`

## Open questions

1. Should the auto-reset also fire when the user drops a file while
   the summary is visible but the queue was already emptied by "Start
   new import"? No-op by definition (empty queue) — no special case.

## Implementation notes

_Filled in as work progresses._
