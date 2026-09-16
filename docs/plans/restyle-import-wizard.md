---
plan_id: restyle-import-wizard
title: Restyle — Import becomes the wizard its progress line already describes (artboard 2d)
area: import
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#import
---

# Restyle — Import becomes a wizard

## Intent

Artboard `2d` is one screen: an eyebrow naming the file, a light `Import`
title, the progress line, **one** card holding the CSV sample beside the
field pickers, and a `Back / Continue to settings` footer. `/import`
renders all of that — plus five more cards above and below it, in one
scroll: Select file format, Upload file, Account coverage, File history,
Files to import, Column mapping, Preview, Transfers, Summary.

`restyle-import-mapping` (plan 5) built the artboard's *contents*: the
progress line, the side-by-side mapping, the `auto` badges, the parse
strip. What it deliberately left alone — "the queue, preview and summary
steps" — is the page those contents sit in, and that page is why the
screen still does not read like `2d`. The line says "step 3 of 6" over a
scroll where all six are on screen at once, and `current_step` already
computes the answer nobody acts on.

This plan makes the page agree with its own progress line: one step on
screen, `Back` and `Continue`, and the sand language on the sections
that never got it.

Depends on `restyle-theme-tokens` (1) and `restyle-import-mapping` (5).
Fifteenth in the stack; opened against `plan/restyle-dashboard-rethink`.

## Scope

- **One step on screen.** `page.py` renders the section (or sections)
  belonging to `current_step(active)` and nothing else. The function
  exists, is unit-tested and already reads the same conditions
  `_repaint_active` uses to show and hide — this plan promotes its answer
  from "what the line says" to "what the page shows". `_repaint_active`
  keeps deciding *whether* a step applies; the shell decides which one is
  in front of you.
- **A footer that moves.** `Back` and `Continue to <next step>` under the
  card, in the artboard's words. `Continue` is disabled — not hidden —
  while the step it would leave is unfinished, with the reason beside it
  (the messages `settings_are_complete` and the mapping errors already
  produce). Nothing new decides readiness: the button asks the same
  functions the line does.
- **The page header.** Eyebrow (`<filename> · <n> rows`, `k-eyebrow`,
  mono count) over `PAGE_TITLE` — the light 32px heading every other
  restyled page uses. `page.py:584`'s `text-2xl font-bold` goes.
- **The sections that never got the sand pass**: `profile_section`
  (format picker — no-caps, chips rather than a Quasar tab strip),
  `upload_section`, `queue_section`, `preview_section`,
  `summary_section`. Tokens only: `SECTION_CARD`, `SECTION_TITLE`,
  `CARD_TITLE`, `k-mono` figures, no-caps buttons, `HAIRLINE_ROW` lists.
- **The queue belongs to Upload.** A multi-file import is a queue of
  files each standing on its own step, so the file list lives on step 2,
  and steps 3–5 act on the active file with the eyebrow naming it. Moving
  between files is one control in the header of steps 3–5
  (`< file 2 of 4 >`), not a card under them.
- **Account coverage and File history are not steps.** They are reference
  panels; they move behind one disclosure on step 1, which is the step
  with nothing else to do.
- i18n: `import.back`, `import.continue_to`, `import.file_n_of_m`,
  `import.reference_panels`, and the eyebrow's row count via
  `plural_key("import.rows_count", n)` (the keys exist).
- BDD: `KAL-CSV-028` "the import page shows one step at a time", and
  `KAL-CSV-029` "Continue refuses a step that is not finished, and says
  why" (@automated via `tests/e2e/test_csv_import.py`).
- The existing 21 e2e tests in `test_csv_import.py` walk a page where
  every section is visible at once (upload, then straight to the account
  picker). They are rewritten against the step navigation — behaviour
  unchanged, route through the page changed. This is the bulk of the
  work and it is in scope: a wizard nobody's tests can walk is not
  shippable.

Out of scope: detection logic, bank profiles, the parse itself, per-file
mapping memory, the transfer-detection card's behaviour, and anything
under `services/` beyond what a step boundary needs. No change to what
an import *does* — only to how many of its steps you see at once. The
seven other pages still carrying pre-restyle headings
(`institutions`, `rules`, `tags`, `planned_transactions`,
`credit_calculator`, `settings/page`, `budget_plan/toolbar`) are a
separate plan.

## Acceptance criteria

- `uv run pytest tests/unit/views/test_import_wizard_step.py -q`
- `uv run pytest tests/e2e/test_csv_import.py -q`
- `uv run pytest tests/e2e/test_transfer_detection.py tests/e2e/test_rules.py -q`
- `grep -q "KAL-CSV-028" docs/bdd.md`
- `grep -q "KAL-CSV-029" docs/bdd.md`
- `! grep -q "text-2xl font-bold" src/kaleta/views/import_view/page.py`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Upload `test_import.csv` at 1360px: step 3 shows the sample
  beside the pickers and **nothing else**, under an eyebrow naming the
  file and a light `Import` title, with `Back` and `Continue to
  settings` beneath — compare to artboard `2d` in light and dark. Then
  the same at 390px, where the two columns stack.

## Touchpoints

- `src/kaleta/views/import_view/page.py` (the shell and the footer),
  `wizard.py` (new: which steps a file has, and how you move between
  them), `state.py` (`current_step` gains nothing; the shell reads it,
  and `settings_block_reason` says what the settings step is missing),
  `step_indicator.py` (the line marks the work and rings the reader),
  `profile_section.py`, `upload_section.py`, `queue_section.py`,
  `preview_section.py`, `summary_section.py`, `coverage_section.py`,
  `metadata_section.py`, `settings_section.py`, `transfer_section.py`
- `src/kaleta/views/theme.py` (the wizard footer's tokens, and the ones
  for what Quasar paints itself: `FORMAT_CHIP`, `UPLOADER`,
  `DISCLOSURE`, `STEP_NODE_READING`)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `docs/product/` (no import doc exists — add one only if
  the wizard needs explaining beyond the scenarios)
- `tests/e2e/test_csv_import.py`, `tests/unit/views/test_import_wizard_step.py`,
  and the two other suites that walk `/import`: `tests/e2e/test_rules.py`,
  `tests/e2e/test_transfer_detection.py` (plus `seed_helpers.delete_account`,
  which is how a file is made to fail during an import)

## Open questions

1. **Can the user go back to a step they have finished?** Default:
   **yes** — `Back` walks the same six steps, and a node already behind
   you is clickable on the progress line. A wizard that only goes
   forward is a wizard you restart to fix a typo.
2. **What happens to the six-section page for a bank profile (mbank,
   pko, wise), which has no mapping step?** Default: the step is
   **skipped in both directions** — `Continue` from Upload lands on
   Settings, `Back` from Settings returns to Upload, and the node stays
   ticked, which is what `current_step` already claims for it.
3. **Does the queue stay visible on steps 3–5?** Default: **no**, only
   the `< file N of M >` control. The artboard shows one file's worth of
   screen, and a queue card under the mapping step is the scroll this
   plan exists to remove.
4. **Import runs from which step?** Default: **Preview** — the button
   moves out of the queue card's header (`Import N files`) into the
   Preview footer, where `Continue` would otherwise be, reading `Import
   N files`. Confirm is then the summary, which is what step 6 is for.
5. **Does the transfer-detection card get a step of its own?** Default:
   **no** — it belongs to Preview, under the table, where it already
   reads as "before you import, these look like transfers".

## Implementation notes

### Open questions, all taken at their default

1. **Back to a finished step: yes.** `wizard.py` walks the same steps in
   both directions, and every node up to `current_step` is clickable on
   the progress line. The reader's step and the work's step are separate:
   the line marks where the work is (`k-step--now`) and rings where the
   reader is (`k-step--reading`), so a reader three steps back can still
   see what the file is waiting on.
2. **A bank profile skips mapping in both directions.** `steps_for()`
   drops `STEP_MAPPING` for a non-generic profile, so `Continue` from
   Upload lands on Settings and `Back` from Settings returns to Upload.
   The node stays ticked, which is what `current_step` already claimed.
3. **No queue on steps 3–5.** The queue card lives on Upload; what those
   steps get is `< File 2 of 4 >` (`data-file-switcher`), which is the
   one thing they need from it.
4. **Import runs from the Preview footer** (`data-import-run`), where
   `Continue` would otherwise be, reading `Import N files`. The button is
   gone from the queue card's header.
5. **Transfers stay on Preview**, under the table.

### Decisions the plan did not ask about

- **`Continue`'s refusal is the readiness check's own message, not the
  file's `status_msg`.** A ready file's status message is "Loaded 2
  rows." — news, not an answer. `state.settings_block_reason()` returns
  the `(key, params)` that `validate_import_readiness` would block the
  import with ("Select a target account."), and the footer shows that on
  the settings step. Mapping keeps using `status_msg`, which there *is*
  the answer ("Map the required columns to continue.").
- **An upload never takes a step away from the reader.** Every upload
  handler ends by putting the page where its file is, which on a
  multi-file drop meant the fourth file yanking the reader off a step
  they had just walked to. The rule is now: a file dropped while the
  reader is on the upload step moves them to its first unanswered
  question, and so does any file that lands while the page — not the
  reader — is choosing the step (`state["step_chosen"]`). A reader
  standing anywhere else keeps their step. A new run and a finished
  import clear the flag: those are the page's to place.

  An earlier attempt keyed this on a token captured when each handler
  began, which loses to a handler that *starts* after the click — the
  browser issues one POST per file and the server takes them in turn.
- **A node for a step the file does not have is not a link.** The mapping
  node stays drawn and ticked for a bank profile (decision 2), but
  `render_step_indicator` now takes the file's own `steps_for()` and
  wires `on_step` only for those — clicking it used to go through
  `clamp_viewed` and land the reader somewhere they did not ask for.
- **One import run per click.** `do_import_all` returns early while
  `state["importing"]` is set: the footer draws the button disabled, but
  that is a websocket round trip away, and a second click inside it
  started a second loop over the same files.
- **The eyebrow's row count is a figure**: `k-mono`, and `f"{count:,}"`,
  which is the same call `mapping_caption` makes for the same number.
- **The mBank/Wise metadata banner moved to Upload**, with the file it
  describes and the queue it belongs to. It is not a step of its own and
  it is not part of the mapping card the artboard draws.
- **`settings_section` and `transfer_section` got the sand pass too**,
  though the plan's list did not name them. They are steps 4 and 5 of the
  same wizard; leaving two cards in the pre-restyle style between three
  restyled ones is worse than not restyling at all. Own commit.
- **Waits on the new route are 10s, not 5s.** `_wait_for_file` and
  `_wait_for_queue` wait on things that were not waited on before — the
  header naming a parsed file, a queue that has stopped growing — and a
  multi-file drop has to decode, parse and re-render once per file before
  either is true. Nothing that was 5s and stayed the same assertion was
  raised; those that had been went back down.
- **`data-*` hooks** (`data-step`, `data-step-panel`, `data-wizard-footer`,
  `data-continue`, `data-blocked-reason`, `data-import-run`,
  `data-file-switcher`, `data-page-eyebrow`, `data-queue-row`) are how
  the e2e suite walks a page whose cards are no longer all on screen.

### Noticed, not fixed (out of scope)

- A saved import rule that carries a column mapping keeps an mBank file
  on the generic path: `_parse_file` passes the mapping, so detection
  never runs and the file keeps a mapping step it does not need. Nothing
  to do with this plan's shell — for the chore inbox.
- Row counts are formatted `f"{n:,}"`, which is right in English and wrong
  in Polish ("1,234 wierszy" for what should be "1 234"). It is wrong in
  the mapping caption too, and `auth_common` solves it a third way
  (`.replace(",", " ")` for both locales). One locale-aware integer
  formatter would fix all three; that is a repo-wide change, not this
  plan's — for the chore inbox.
- `do_import_all`'s double-click guard has no test: a second click inside
  a websocket round trip is not something the e2e suite can time. Nor is
  a click landing *during* a multi-file upload storm — every refresh of
  the progress line replaces its nodes, so a click aimed at one that is
  being replaced is dropped. The `step_chosen` rule is covered at a
  slower beat instead: choose a step, drop another file, keep the step.

### What the e2e rewrite turned up

- Several assertions were passing on hidden elements once the wizard
  existed: `not_to_be_visible` is true of a card that is merely on
  another step. Those became `to_have_count(0)` scoped to the card the
  thing would be in.
- `test_disabled_import_rule_stops_matching` depended on the shared
  e2e database holding no *other* active rule with the same pattern —
  and an earlier test's "Remember this mapping" leaves one. The test now
  disables every rule of that pattern, which is the premise it always
  meant.
- A multi-file drop moved the page under the reader: each upload handler
  ended with `_sync_step(follow=True)`, so a click on a step node was
  undone by the next file landing. The tests first worked around it with
  a second click; the fix is `step_token` (above), and what the tests
  keep is `_wait_for_queue`, which waits for the queue to stop growing
  (`data-queue-row`) before asking anything of it.
- KAL-CSV-021 used to make a file fail by importing it with no target
  account, which the wizard will not let you do: `Continue` refuses at
  settings. The file now fails the way the branch it covers actually
  fires — the target account is deleted between choosing it on step 4
  and importing into it on step 5, so the insert cannot be written and
  `_import_one`'s `except` marks the file failed. That keeps the
  import-time failure path covered rather than swapping it for a parse
  failure.
