---
plan_id: import-queue-survives-navigation
title: Warn before leaving /import with an unfinished queue
area: import
effort: small
status: draft
roadmap_ref: ../roadmap.md
---

# Warn before leaving /import with an unfinished queue

## Intent

The import queue (uploaded files, accounts, categories, flags) lives in a `state`
dict inside the page function (`src/kaleta/views/import_view/page.py:119`). Any
full navigation away from `/import` rebuilds the page and the queue is gone
without warning.

On 2026-11-09, with 9 files uploaded and configured, the tab ended up on
`/settings` and coming back showed an empty import page; everything had to be
uploaded again. The trigger was not captured. It was **not** "Manage saved
mappings": that link already opens a new tab (`new_tab=True`,
`settings_section.py:137`; e2e `test_import_link_to_saved_mappings.py`, KAL-CSV-035).
Remaining candidates: a sidebar click (Settings is in the sidebar), browser back,
or an automation tool navigating the tab.

## Scope

In scope:

1. **Find the trigger first** (timebox: 30 min): reproduce with the sidebar
   "Settings" link and with browser back while files are queued; record the
   result in "Implementation notes". It does not change the fix below, but tells
   whether the sidebar guard is needed.
2. **Leave guard.** While `not queue_is_terminal(state["queue"])` (any file not
   `done`/`failed`) or an import is running:
   - register a `beforeunload` handler (browser back, reload, close, and full-page
     navigations from `ui.link` / `ui.navigate.to`);
   - remove the handler when the queue becomes terminal or empty.
   - If step 1 shows sidebar clicks bypass `beforeunload`, add a confirmation
     dialog on sidebar links while the guard is active (i18n keys
     `import.leave_guard_title`, `import.leave_guard_body`, en/pl).
3. **Do not persist the queue** in `app.storage.tab` or elsewhere: with Redis/Valkey
   configured it would hold plain-text statement rows. Memory-only is intended.

Tests:

- `tests/e2e/test_import_leave_guard.py`:
  - `test_leave_guard_active_with_queued_file` — after upload, `window.onbeforeunload`
    (or the registered listener flag) is set;
  - `test_leave_guard_cleared_after_import` — after a completed import it is cleared.
- Unit test for `queue_is_terminal` if it does not exist yet.

Out of scope:

- Server-side persistence of parsed files across sessions.

## Acceptance criteria

- `uv run pytest tests/e2e/test_import_leave_guard.py -q`
- `grep -c "KAL-CSV-042" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` With two files queued, click the sidebar "Settings": a confirmation
  appears; cancelling keeps the queue.

## Touchpoints

- `src/kaleta/views/import_view/page.py` — guard on/off around queue changes
- `src/kaleta/views/import_view/state.py` — `queue_is_terminal` (reuse if present)
- sidebar layout (only if step 1 requires it)
- i18n files (en/pl), `docs/bdd.md` — `KAL-CSV-042`, `tests/e2e/test_import_leave_guard.py`

## Open questions

- Answered by step 1: does a NiceGUI sidebar link fire `beforeunload`? (`ui.link`
  and `ui.navigate.to` do full page loads, so it should.)

## Implementation notes

## Implementation (filled by plan-archiver)
