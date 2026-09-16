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
- `grep -qv "text-2xl font-bold" src/kaleta/views/import_view/page.py`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Upload `test_import.csv` at 1360px: step 3 shows the sample
  beside the pickers and **nothing else**, under an eyebrow naming the
  file and a light `Import` title, with `Back` and `Continue to
  settings` beneath — compare to artboard `2d` in light and dark. Then
  the same at 390px, where the two columns stack.

## Touchpoints

- `src/kaleta/views/import_view/page.py` (the shell and the footer),
  `state.py` (`current_step` gains nothing; the shell reads it),
  `profile_section.py`, `upload_section.py`, `queue_section.py`,
  `preview_section.py`, `summary_section.py`, `coverage_section.py`
- `src/kaleta/views/theme.py` (a wizard footer token, if the row needs
  one)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `docs/product/` (no import doc exists — add one only if
  the wizard needs explaining beyond the scenarios)
- `tests/e2e/test_csv_import.py`, `tests/unit/views/test_import_wizard_step.py`

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
- **The mBank/Wise metadata banner moved to Upload**, with the file it
  describes and the queue it belongs to. It is not a step of its own and
  it is not part of the mapping card the artboard draws.
- **`settings_section` and `transfer_section` got the sand pass too**,
  though the plan's list did not name them. They are steps 4 and 5 of the
  same wizard; leaving two cards in the pre-restyle style between three
  restyled ones is worse than not restyling at all. Own commit.
- **`data-*` hooks** (`data-step`, `data-step-panel`, `data-wizard-footer`,
  `data-continue`, `data-blocked-reason`, `data-import-run`,
  `data-file-switcher`, `data-page-eyebrow`, `data-queue-row`) are how
  the e2e suite walks a page whose cards are no longer all on screen.

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
- A multi-file drop moves the page under the reader: each upload handler
  ends with `_sync_step(follow=True)`, so a click on a step node can be
  undone by the next file landing. `_wait_for_queue` waits for the queue
  to stop growing (`data-queue-row`), and `_step` retries once.
- KAL-CSV-021 used to make a file fail by importing it with no target
  account. The wizard will not let that happen — `Continue` refuses at
  settings — so the failing file is now a truncated Wise QIF
  (`wise/truncated-download-sample.qif`), which fails at parse. The
  import-time failure path (an exception during persistence) is still
  there; nothing e2e can reach it any more.
