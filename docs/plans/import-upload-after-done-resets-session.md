---
plan_id: import-upload-after-done-resets-session
title: Import — dropping a file after a completed run starts a fresh session
area: import
effort: small
status: in-progress
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

- **BDD id is KAL-CSV-020, not KAL-CSV-013.** The plan predicted 013 as the
  next free id, but the spec has since grown to KAL-CSV-019 (Wise CSV). The
  acceptance criterion `grep -q "KAL-CSV-013"` still holds — that scenario
  exists and is the multi-file queue regression this change must not break.
- **The reset runs before the first `await` in `handle_upload` — defensively,
  not because a test demands it.** A multi-file drop arrives as one HTTP
  request, but `handle_event` schedules each async upload handler as its own
  background task (`background_tasks.create_or_defer`), so the handlers do
  interleave. Checking synchronously at the top means only the first handler can
  find a terminal queue; the rest see an empty one, and `queue_is_terminal([])`
  is `False` by design, so they append instead of wiping each other's files.
  Mutation-checked: moving the block *after* `await e.file.read()` still passes
  the whole e2e suite, because a file only becomes terminal once imported —
  long after it was appended — so the queue is empty at the second handler's
  check either way. The order is kept as the one that stays correct if a file
  can ever be terminal earlier, and the comment says so rather than claiming
  test coverage it does not have.
- **KAL-CSV-020 also drops two files at once onto a finished queue** and asserts
  both survive with the finished file gone. That is a real regression test for
  the multi-drop outcome; it is not evidence for the ordering above.
- **Open question 1 resolved as the plan's default.** An already-empty queue is
  not terminal, so dropping a file after "Start new import" is a no-op — no
  special case.
- **`queue_is_terminal` lives in `state.py`** next to `TERMINAL_STATUSES`, not
  in `constants.py`: the helper is queue logic over `QueuedFile`, and
  `constants.py` documents itself as profile/colour lookups only.
- **Test-infrastructure fix outside the plan's touchpoints:
  `tests/e2e/test_rules.py::_select_option`.** The new e2e seeds one more
  account, which pushed `test_rules_apply_during_csv_import`'s target-account
  option out of Quasar's virtualised `.q-menu` slice — the option was not in
  the DOM at all, so the click timed out. Verified as a latent order dependency,
  not a regression from this change: the full suite is green on `main`, green on
  this branch with the new test deselected, and failed only with it selected.
  The helper now scrolls the menu until the option renders. No assertion was
  loosened. Every other `.q-menu` helper in `tests/e2e/` has the same latent
  fragility; left alone here to keep this diff single-purpose, and worth a
  Chore-inbox line. Shipped as its own commit (Working Agreement rule 9).
- **The failed-file branch got its own scenario, KAL-CSV-021.** The plan's test
  list did not cover it, and review flagged it as the one shipped behaviour
  without direct verification. Reaching a `failed` file turned out not to be a
  parse-path question — `_parse_file` degrades to `needs_mapping` (not terminal)
  for every malformed input tried, including empty and non-CSV content. The
  reachable route is `_import_one`: importing a Ready file with no target
  account fails the readiness check. The e2e drives exactly that, then asserts
  the toast and the cleared queue. It seeds nothing, so it does not grow the
  account list the virtualised selects depend on.
- **`count_transactions(account_id)` added to `tests/e2e/seed_helpers.py`** so
  the e2e can assert the ledger count directly (3 rows from file A, then 5 after
  file B) rather than inferring "not duplicated" from the UI.
