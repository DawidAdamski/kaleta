---
plan_id: dogfooding-bugs-wave-2
title: Dogfooding bugs — wave 2 (discoverability + UX)
area: views (transactions, import, theme)
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
---

# Dogfooding bugs — wave 2 (discoverability + UX)

## Intent
During dogfooding the user hit a cluster of discoverability and UX papercuts:
things that exist but are hard to find, controls with no feedback, and a
layout that overflows. None are data-correctness bugs; all erode trust in
the UI. This wave ships them one PR per bug, same rhythm as wave 1.

## Scope
Covers six reported items. Two of them (#2, #7) first looked like they
already worked — see Open questions. The user clarified both: #2 was
genuinely broken on the **Accounts** page (first map had looked at the
ledger toggle) and is fixed; #7's history exists but is buried two expanders
deep and will be surfaced.

1. **#9 — Truncated table cells have no hover tooltip.** account /
   description / category / added_by cells truncate with ellipsis but carry
   no `<q-tooltip>`, so the full value is unreachable. Add tooltips (the
   pattern already exists on the date cell and the notes/splits icons).
2. **#8 — Proposed-transfers section overflows, accept-all scrolls away.**
   The transfer section's `pairs` column has no height cap and the
   accept-all button sits below it, so many suggestions push it off-screen.
   Cap the list height + scroll, pin accept-all in a sticky footer.
3. **#10 — No link from the import page to saved column mappings.** Saved
   import rules (column mappings) are managed only in Settings → Import;
   the import flow never points there. Add a link.
4. **#13 — No global button click feedback.** Buttons give no pressed-state
   affordance. Add a global `:active` feedback (no per-button change; there
   is no shared button factory — ~394 ad-hoc `ui.button` sites).
5. **#2 — Accounts "group by": the active option is not visibly selected.**
   The user clarified this is the **Accounts** page (not the ledger): the
   type/institution toggle shows no clear selected state, so you cannot tell
   at a glance which grouping is active. The toggle was a plain
   `color=primary` toggle and never wore the brand's `k-segment` class (whose
   own CSS says it exists for group-by controls, filling the chosen option
   with ink). Apply `k-segment`.
6. **#7 — Import history (reframe: surface it).** History already exists in a
   collapsed expansion. Surfaced in slice 3; the Format-step reframe below
   grew out of looking at it.
7. **#7-followup — the import wizard opens a step past its first question.**
   Dogfooding slice 3 exposed a deeper flaw: the page landed on **Upload**
   (step 2), a step past the **Format** step (step 1) whose only control — the
   bank/format chooser — did nothing until a file existed (`_select_profile`
   returns early when there is no active file), so clicking a format on the
   empty landing was a dead no-op. User chose option A: land on Format, make
   the format a page-level default that highlights at once and carries to the
   files uploaded next.

Out of scope: new import-history data model (exists); a shared button
factory refactor (394 call sites — too broad for this wave); the wave-2
candidates #19/#22/#23 (deferred unless the user folds them in).

## Acceptance criteria

- `./scripts/verify.sh --e2e`
- `uv run python scripts/spec_coverage.py`

(Per-slice BDD + e2e added as each slice lands; see Implementation notes.)

## Touchpoints
- `src/kaleta/views/components/transaction_table.py` — body-slot cells (#9)
- `src/kaleta/views/import_view/transfer_section.py` — pairs column + accept-all (#8)
- `src/kaleta/views/import_view/mapping_section.py` / `page.py` — link to settings (#10)
- `src/kaleta/views/theme.py` / `layout.py` — global `:active` feedback (#13)
- `src/kaleta/views/accounts.py` — group-by toggle active highlight (#2)
- `src/kaleta/views/import_view/coverage_section.py` + `page.py` — history prominence (#7)
- `src/kaleta/views/import_view/page.py` + `constants.py` — land on Format, page-default format (#7-followup)
- `docs/bdd.md` — KAL scenarios per slice

## Open questions
- **#2 — resolved by the user.** The first map looked at the *ledger*
  grouping toggle (which does wear `k-segment`); the user meant the
  **Accounts** page toggle, which did not. So it was genuinely broken there.
  Fixed in slice 2 by applying `k-segment`.
- **#7 — the history exists but is buried two expanders deep.** It lives
  inside `_panel(STEP_FORMAT)` → `ui.expansion("reference_panels")` →
  `ui.expansion("history_heading")` (`page.py:995–997`,
  `coverage_section.py:99`), both collapsed, on the Format step — which is
  why the user never found it. Slice to surface it (user asked for a
  screenshot of the current state first, then the fix).

## Implementation notes
_(filled per slice)_

### Slice 1 — #9 truncated-cell tooltips
- The body slot (`transaction_table._body_slot`) already uses `<q-tooltip>`
  on the date cell, notes icon, splits icon and planned action — the pattern
  exists; the truncatable text cells (account / description / category /
  added_by) simply lacked one. The truncation basis is a fixed column width
  (account 166px, category 168px) with `overflow:hidden; text-overflow:
  ellipsis` — per KAL-TXN-018 a cell must not widen the table, so the full
  value needs the tooltip to stay reachable.
- The e2e reaches a cell by its text, not a `key=` selector: Quasar does not
  render QTd's `key` prop as a DOM attribute. Tooltips fire on hover of the
  text node (the account cell's own text, the description `<span>`), which is
  why the test moves the mouse away between the two hovers.
- Fail-on-old / pass-on-new confirmed by swapping `main`'s
  `transaction_table.py` under the new test.

### Slice 2 — #2 accounts group-by active highlight
- Root cause: the Accounts toggle (`accounts.py`) used
  `.props("color=primary …")` with no `k-segment` class, so Quasar's default
  selected fill was the accent (`--q-primary` ≈ #B4591F) — close enough to
  the unpicked option that the user could not tell which was active. The
  ledger's grouping toggle already uses `k-segment`, which remaps
  `--q-primary → --k-ink`, filling the chosen option with ink. Applied the
  same class + `toggle-text-color=info` here.
- The e2e asserts the selected button's computed background sums to a dark
  (ink) value, which fails on the old accent fill and passes on ink —
  verified by swapping `main`'s `accounts.py` under the test.

### Slice 3 — #7 surface import history
- The history was buried: it lives on the **Format** step (`page.py`), inside
  a collapsed `ui.expansion("reference_panels")`, which in turn holds a second
  collapsed `ui.expansion("history_heading")` (`coverage_section.py`). The
  page also hard-lands on the **Upload** step (`state["step"] = STEP_UPLOAD`),
  so the user never even reaches the step the panel sits on — confirmed by
  screenshots (scratchpad: lands on Upload; history is two expanders deep on
  Format).
- Fix is bounded: open **both** expanders by default (`value=True`). I did
  **not** change the landing step — forcing Format-first would add friction to
  the main upload flow for everyone and risk the import e2e. So walking back to
  Format (the natural "where's my history" move) now shows it with no further
  clicks, instead of two.
- Residual (flagged to the user): history is still only on the Format step, not
  the Upload step the user lands on. Whether to surface it further is a UX
  decision left open.
- e2e walks to the Format step and asserts the inner "File history" expander
  is both **visible** (which needs the outer reference panel open) and carries
  `q-expansion-item--expanded` (the inner one open). It deliberately does NOT
  assert on the empty-history text: the e2e app's import state is shared, so
  other tests may record runs and the "No imports recorded yet." line is not
  reliably present — the expander *state* is. Fail-on-old / pass-on-new
  re-verified for this final (class) assertion by swapping both `main` files
  under the test: on `main` both expanders collapse, so the outer hides the
  inner (`to_be_visible` fails) and the inner lacks the expanded class.

### Slice 4 — #7-followup: import wizard opens on Format (option A)
- Root cause of the three dogfooded symptoms is one inversion: `profile` is a
  per-file attribute, but its chooser sat on step 1 *before* a file could
  exist. `current_step(None)` returns Upload, and the page both defaulted
  `state["step"]` to Upload and did `_sync_step(follow=True)` on first render,
  so it opened a step past Format; and `_select_profile` returned early with
  no active file, so a format click on the empty landing selected nothing.
- Fix (option A, user's choice):
  1. Land on Format: `state["step"] = STEP_FORMAT`, and first render calls
     `_sync_step()` (no `follow`) so the clamp keeps the reader on Format
     instead of chasing the work to Upload.
  2. A page-level default format: `state["default_profile"]` (starts
     `GENERIC_PROFILE`). `_select_profile` stores it and, when there is no
     active file, lights the chip directly (`set_active_profile(key)`) and
     returns — no parse, but no longer a dead click. `_repaint_active` shows
     the default on the chip whenever no file is active.
  3. `handle_upload` starts each new file on `state["default_profile"]`. A
     `generic` default still auto-detects on parse (unchanged); an explicit
     bank applies that profile and degrades to generic+mapping if the file
     does not match it (`parse_queued_file`'s own fallback), so no dead end.
- `current_step` and the wizard navigation functions are untouched: only the
  *reader's* landing and the format's scope changed, not where the work is —
  the `test_import_wizard_step` unit suite still holds as written.
- Three existing e2e in `test_csv_import.py` asserted the old Upload landing
  (or reached for an upload-step control on load): `test_a_late_upload…`,
  `test_continue_refuses…`, `test_bulk_default_skips_matched_rule`. Updated to
  open on Format and walk to Upload where an upload-step control is needed —
  `set_input_files` still works on the now-hidden input (actionability skips
  file inputs), so only the visible-click/landing assertions moved. This is a
  deliberate behaviour change, not a loosened assertion.
- New e2e `test_import_format_first.py` (KAL-CSV-034) asserts the Format panel
  is up (Upload hidden) on load and that an mBank click lights the chip with
  no file. Fail-on-old / pass-on-new verified by swapping `main`'s `page.py`
  under it: on `main` it lands on Upload (first assert fails).
- The "default carries to the next upload" half of the fix is covered by code
  and this note, not by an e2e assertion, on purpose: for a generic CSV it has
  no *user-visible* tell. A carried `generic` default and no default both
  auto-detect; a carried bank default on a non-matching file falls back to
  generic+mapping — the same mapping step a generic upload reaches. So the two
  worlds look identical on screen, and an e2e claiming to tell them apart would
  be asserting on nothing. KAL-CSV-034's scenario was reworded to the landing +
  chip-highlight it actually proves, rather than over-claiming the carry.
- verify.sh --e2e: 248 passed, 1 failed — `test_map_unrecognised_csv_and_import`,
  which passes alone and with its whole file (`test_csv_import.py`, 27/27). A
  newly-observed cross-file shared-state flake (the e2e suite shares one app
  family), not this slice: every import test passes together, and this slice
  touches only the import page. Logged in `chores.md`.

### Slice 4a — follow-up fix: re-clicking the current step wedged navigation
- Landing on Format (Slice 4) surfaced a latent bug: the progress line lets you
  click the step already on screen, which ran the full `_goto` → `_sync_step`
  repaint for a step that did not move. A click landing mid-rebuild (four
  refreshables) was dropped, so clicking the current step and then the next one
  left the reader stuck. Before Slice 4 the landing was Upload, so re-picking
  the step you were on was rare; once Format became the landing, a test (and a
  user) re-picking Format before moving on hit it every time.
- The wedge is a race: the repaint of the unchanged step has to finish before
  the next step-node click lands, or that click is dropped. It is timing, not
  ordering — but the timing depends on load. `test_wise_qif_auto_detect_and_import`
  (which does `_step(FORMAT)` then `_step(UPLOAD)`) hit it deterministically in
  isolation (3/3) yet stayed green in-file (27/27) and under the parallel
  `-n auto` suite that Slice 4's `verify.sh --e2e` ran — which is why it slipped.
  Shipped as its own PR, separate from the #10 "link to saved mappings" slice,
  to keep each diff single-purpose.
- Fix: `_goto` records the choice (`step_chosen`) but returns before
  `_sync_step` when the step is not changing — no panel moves, no line
  changes, nothing to rebuild, nothing to drop. Regression test
  `test_import_step_reclick.py` (KAL-CSV-036) re-clicks Format then clicks
  Upload and asserts Upload is shown; fails 2/2 on `main`, passes on the fix.
- `test_rules.py::test_rules_apply_during_csv_import` failed once in a parallel
  `--e2e` run during this work and passed on re-run and 2/2 in isolation — the
  same step-node-click-under-`-n auto` fragility, not this fix. Logged in
  `chores.md`.
