---
plan_id: dogfooding-bugs-wave-1
title: Dogfooding bugs — wave 1 (quick fixes from first real use)
area: cross-cutting (institutions, settings, categories, planned transactions, import)
effort: medium
status: archived
archived_at: 2026-10-14
roadmap_ref: ../../roadmap.md
---

# Dogfooding bugs — wave 1 (quick fixes from first real use)

## Intent
The maintainer started using Kaleta for real and reported a batch of
bugs. This plan captures the *quick, confirmed defects* ("wave 1") so
each ships as its own single-purpose PR. UX polish, discoverability and
larger features from the same report are deliberately **out of scope**
here and tracked separately (see "Out of scope" below).

## Scope
Each item ships as one PR (slice). Confirmed bugs only:

1. **Upload is broken under NiceGUI 3.x (institution logo + backup
   restore).** `institutions.py` (add + edit logo) and
   `settings/data_tab.py` (restore-from-file) used the removed 2.x upload
   event API (`e.name` / `e.content.read()`). NiceGUI 3.x exposes
   `e.file` with an async `read()`. The import view was already migrated;
   these two were missed. → `await e.file.read()` / `e.file.name`.
2. **"Add subcategory" sometimes saves a root category**
   (`categories.py`). Presetting the add dialog fires the Type
   `on_value_change` handler, whose async parent-reload resets the parent
   select to 0 *after* the preset set it — so the child is persisted with
   `parent_id=None`. Includes **#4**: the maintainer's "Nazwa jest
   wymagana" on a category create is the same add-dialog state defect
   (name value not read at save), **not** a uniqueness conflict —
   same-name-across-types is already allowed
   (`uq_categories_parent_type_name_bidx`).
3. **Planned transactions: category list not narrowed by type**
   (`planned_transactions.py`). The Type select has no `on_value_change`;
   the category dropdown lists both income and expense. The transactions
   add dialog already has the exact pattern to mirror.
4. **Double-click on "accept transfer" shows a spurious error toast**
   (`import_view`). The transfer accept/dismiss/accept-all buttons are
   not disabled during their async handler; a second click hits the
   already-linked guard and surfaces a confusing `ConflictError`. No data
   corruption (the guard prevents duplicates) — the fix is a re-entrancy
   guard mirroring `do_import_all`.
5. **The Subscriptions root category can be deleted**
   (`category_service.py` + `categories.py`), cascading away the whole
   subscription subtree and nulling linked transactions. There is already
   an `is_subscriptions_root` flag but no guard. → block in the service
   and hide the delete button in the view.

### Out of scope (other waves / separate plans)
- Discoverability: surface import history (#7) and saved mappings (#10).
- UX: group-by active highlight (#2), truncated-cell tooltips (#9),
  global button press feedback (#13), proposed-transfers layout (#8).
- Features: persist default grouping (#14), "family without children"
  template (#5), category colours (#15), bulk change-category (#17).
- Investment accounts (#3) — explicitly deferred by the maintainer.
- Custom-CSV mapping wizard (#12) — needs its own design plan.

## Acceptance criteria
- `uv run pytest tests/unit tests/integration -q`
- `./scripts/verify.sh --e2e` (every slice touches `src/kaleta/views/`)
- `uv run python scripts/spec_coverage.py`
- Each slice retags its `KAL-*` scenario(s) in `docs/bdd.md`.

## Touchpoints
- Slice 1: `src/kaleta/views/institutions.py`,
  `src/kaleta/views/settings/data_tab.py`; e2e `tests/e2e/`.
- Slice 2: `src/kaleta/views/categories.py`
  (`src/kaleta/services/category_service.py` already enforces type/parent
  rules server-side).
- Slice 3: `src/kaleta/views/planned_transactions.py`.
- Slice 4: `src/kaleta/views/import_view/page.py`,
  `src/kaleta/views/import_view/transfer_section.py`.
- Slice 5: `src/kaleta/services/category_service.py`,
  `src/kaleta/views/categories.py`, `src/kaleta/schemas/category.py`
  (expose `is_subscriptions_root` to drive the UI).

## Open questions
- Resolved (maintainer, 2026-10-14): keep the institution logo and fix
  the upload (do not remove the feature); defer investment accounts (#3);
  #4 is the add-dialog "name required" defect, folded into slice 2.
- Slice 5: protect the root only, or also its children? Also block
  rename/re-parent of the root, or only delete? (Decide at slice time;
  default = protect the root from delete, both service + hidden button.)

## Implementation notes
### Slice 1 — upload under NiceGUI 3.x (institution logo + backup restore)
- Root cause: NiceGUI 3.x replaced the upload event's `.name` / `.content`
  (a sync buffer) with `e.file` (a `FileUpload` whose `read()` is async).
  `institutions.py` `_add_upload`/`_edit_upload` and `data_tab.py`
  `_on_upload` were never migrated; `import_view/page.py:377` already was.
- Fix: made the three handlers `async` and switched to
  `await e.file.read()` / `e.file.name`. Dropped the now-unneeded
  `# type: ignore[attr-defined]` and typed `data_tab._on_upload`'s event
  as `events.UploadEventArguments` (was `object`) — no type erosion.
- Why no test caught it: there was no e2e exercising the logo upload or
  the backup restore-from-file (settings data-safety e2e only covered the
  wipe-confirmation path). Added coverage at that level.
- Coverage note: the e2e (KAL-INS-009) walks the *add*-logo path; the
  *edit* handler is identical in shape, and the backup restore handler
  shares the same upload-event API the add test now exercises. A dedicated
  UI-level restore e2e is logged in `chores.md`.

### Slice 2 — add-subcategory saved a root; and #4 "Nazwa jest wymagana"
- #16 root cause: `open_add_dialog` preset the dialog, but when the
  parent's type differed from the dialog's last-used type, `set_value` on
  the Type select scheduled its async `on_value_change` reload, which
  landed after the preset and reset the Parent select to 0 — so the child
  was persisted with `parent_id=None` (a silent root). Fixed by guarding
  the Type handler to react only to interactive changes while the dialog
  is open (`add_dialog.value`); the preset flow is the single authoritative
  source via `_load_add_parents(..., select=...)`. e2e KAL-CAT-013 fails on
  the old code and passes now. Shipped as PR #249.
- #4 ("Nazwa jest wymagana" with a typed name) **could not be reproduced**
  on `main`: typed-name + Save creates the category reliably, including
  aggressive fast-typing + immediate Save (3/3). A duplicate name raises a
  distinct "already exists", not "name required". Deferred to the chore
  inbox with a request to retry on a fresh deploy + environment details
  (hypothesis: an older deployed build, or an input value-sync timing issue
  that only shows under real network latency, never on localhost).
- Separate finding: Enter does not submit the category dialogs because
  NiceGUI's `ui.keyboard` defaults to `ignore=['input','select','button',
  'textarea']` — a cross-cutting dialog-UX issue (same pattern in other
  dialogs), logged to chores for later, per the maintainer.

### Slice 3 — planned transactions: category list narrows by type (#18)
- `planned_transactions.py` listed every category regardless of type. Now
  `_load_refs` builds `expense_cats`/`income_cats` separately, a Type
  `on_value_change` swaps the category options (empty for a transfer) and
  clears the stale selection, and `_open_add`/`_open_edit` set the options
  for the chosen type explicitly (so the open case is correct even when the
  type value does not change). Mirrors the transactions add dialog. e2e
  KAL-PLN-028 fails on the old code (income category offered under Expense)
  and passes now.

### Slice 4 — double-click on "accept transfer" (#11)
- The transfer accept/dismiss/accept-all handlers in `import_view/page.py`
  had no re-entrancy guard (only `do_import_all` did). An impatient
  double-click fired the handler twice; the second hit `pair_as_transfer`'s
  already-linked guard and surfaced a confusing `ConflictError` toast — no
  data corruption (the guard prevents duplicates), just a bad message.
- Fix: a shared `transfer_busy` flag, set at the top of each handler and
  cleared in `finally`, mirroring `do_import_all`'s `state["importing"]`
  pattern. The second click returns immediately.
- Test: KAL-TRF-004 is `@manual` — reliably triggering the sub-round-trip
  race in Playwright (and making the *un*guarded failure deterministic) is
  not feasible, so it is not automated. `verify.sh --e2e` confirms the
  existing transfer e2e (KAL-TRF-001..003) still pass.

### Slice 5 — protect the Subscriptions root from deletion (#6)
- Decision (maintainer, 2026-10-14): protect only the flagged root, and only
  from deletion (renaming/re-parenting left alone).
- `CategoryService.delete` now raises `ConflictError` when
  `category.is_subscriptions_root` (before it would `session.delete` and
  cascade away the subtree, nulling linked transactions). `CategoryResponse`
  gained `is_subscriptions_root` so the view can read it, and the Categories
  view hides the delete button on that root (service guard + hidden button,
  defence in depth).
- Test: integration `test_subscriptions_root_cannot_be_deleted`
  (KAL-CAT-014) — the root is refused, it survives, an ordinary category
  still deletes. The hidden-button view change is the same rule's UX surface;
  not given a separate e2e because locating the flagged root in the seed is
  ambiguous (a flat same-named category may also exist), and `verify.sh
  --e2e` confirms the page still renders.

## Implementation

Landed on 2026-10-14.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4016cd2` | Dawid (Ani) | 2026-10-14 | fix(upload): migrate upload handlers to the NiceGUI 3.x event API |
| `c1dcacc` | Dawid (Ani) | 2026-10-14 | test(institutions): type the e2e tmp_path; note edit/restore coverage |
| `f1b6794` | Dawid (Ani) | 2026-10-14 | fix(categories): add-subcategory no longer saves a root category |
| `16140d4` | Dawid (Ani) | 2026-10-14 | fix(planned): narrow the category list to the selected type |
| `1e6cb2b` | Dawid (Ani) | 2026-10-14 | fix(import): guard transfer accept/dismiss against a double-click |
| `e47833f` | Dawid (Ani) | 2026-10-14 | fix(categories): protect the Subscriptions root from deletion |
| `bd7c516` | Dawid (Ani) | 2026-10-14 | docs(chores): log subscriptions-root protection follow-ups |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/dogfooding-bugs-wave-1.md
- src/kaleta/schemas/category.py
- src/kaleta/services/category_service.py
- src/kaleta/views/categories.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/institutions.py
- src/kaleta/views/planned_transactions.py
- src/kaleta/views/settings/data_tab.py
- tests/e2e/test_categories_add.py
- tests/e2e/test_institutions.py
- tests/e2e/test_planned_category_by_type.py
- tests/integration/test_subscription_categories.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/unit tests/integration -q` | 0 |
| `./scripts/verify.sh --e2e` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |

**Notes:** Touchpoints of all five slices are covered by the listed commits (the script's automatic overlap warning was a false positive: the Touchpoints bullets are not in its expected format). PRs: #248 (slice 1), #249 (slice 2), #250 (slice 3), #251 (slice 4), #252 (slice 5).
- Bug #4 ("Nazwa jest wymagana") was NOT fixed: it could not be reproduced on main; logged in `docs/plans/chores.md` for retest on a fresh deploy.
- "Enter does not submit dialogs" and the subscriptions-root protection follow-ups are logged in `docs/plans/chores.md`.
