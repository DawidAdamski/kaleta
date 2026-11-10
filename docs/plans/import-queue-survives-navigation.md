---
plan_id: import-queue-survives-navigation
title: Warn before leaving /import with an unfinished queue
area: import
effort: small
status: in-progress
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

- **Step 1 — trigger (reproduced with Playwright on a demo instance, 2 files
  queued).** Browser back (`history.back()`) went to `/dashboard` with no
  warning and the queue was gone; a sidebar click does the same. NiceGUI here
  (3.18, no `ui.sub_pages`) makes `ui.navigate.to` a full page load, so a
  sidebar entry fires `beforeunload`: with a listener registered, clicking the
  sidebar "Settings" raised the browser's prompt and dismissing it kept
  `/import` with both files. **No sidebar dialog was added** and the i18n keys
  `import.leave_guard_title` / `_body` were not needed (the prompt is the
  browser's own, with its own text).
- **A listener, not `window.onbeforeunload`.** NiceGUI already owns
  `window.onbeforeunload` (it sets `sessionStorage.__nicegui_tab_closed`);
  overwriting it would break that. The guard is a named listener,
  `window.__kaletaImportLeaveGuard`, added/removed with
  `addEventListener`/`removeEventListener`; the e2e reads that name.
- **When it is on:** `state.leave_guard_active(queue, importing=...)` — a run
  is going, or the queue holds a file not `done`/`failed` (reuses
  `queue_is_terminal`). Synced in `_render_queue` (every queue change renders
  the queue) and after a run ends; `state["leave_guard"]` mirrors what was
  last sent, so the script runs only on changes.
- **The page's client is captured at build time.** The first version called
  `ui.run_javascript` from `do_import_all`'s `finally`; that handler is fired
  by the footer's import button, which `wizard_footer.refresh()` deletes, so
  NiceGUI could not resolve the client ("The parent element this slot belongs
  to has been deleted") and the run never reached its summary. The existing
  `test_csv_import` e2e caught it. `page_client.run_javascript` avoids the
  slot lookup.
- **Not persisted** (scope item 3): the queue stays memory-only.
- **Manual criterion checked with Playwright** (two files, sidebar
  "Settings" → `beforeunload` prompt; cancel → still `/import`, 2 queue rows).
  The e2e uses the pinned "Dashboard" entry instead of "Settings": it is
  always visible, and expanding the "Setup" group would persist a nav
  collapse change for the shared e2e user. Both are the same `ui.navigate.to`.

## Implementation (filled by plan-archiver)
