---
plan_id: dogfooding-bugs-wave-1
title: Dogfooding bugs — wave 1 (quick fixes from first real use)
area: cross-cutting (institutions, settings, categories, planned transactions, import)
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
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
