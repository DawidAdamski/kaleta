---
plan_id: settings-seed-panel-unify
title: One example-data panel in Settings, not two
area: settings
effort: medium
status: archived
archived_at: 2026-10-15
roadmap_ref: ../../roadmap.md#seed
---

# One example-data panel in Settings, not two

## Intent
Dogfooding: Settings → Data had two cards about example data and nobody could
say why. One ("Demo data") held **wipe + seed** and **Clear all data**; a
separate "Example data" card held the per-feature additive buttons. Two places
for "fill the app with examples" is confusing — especially when preparing a
demo. Fold them into one.

## Decision (chosen with the maintainer)
One **"Example data"** card owns all *seeding*:
- the per-feature additive buttons with live row counts (unchanged),
- "Seed everything" (additive, skips what exists),
- "Populate with example data" — the **wipe + seed** reset — as a clearly
  separate, confirmed destructive action at the foot of the same card.

**Clear all data** is not seeding, so it moves beside Backup/Restore (the
card is retitled "Backups & clearing"). The old "Demo data" card is removed.

## Scope
- **`example_data_section.py`:** add the wipe+seed "Populate with example
  data" action (confirm dialog → `DataService.seed()`, toast, refresh counts)
  below a divider under the additive buttons. Reuses the existing
  `settings.seed_*` i18n.
- **`data_tab.py`:** delete the "Demo data" card; move the Clear-all-data
  button, its DELETE-gated dialog and handler into the Backup card; retitle it
  "Backups & clearing". The clear button keeps its exact label and dialog so
  `test_settings_data_safety` stays green.
- **i18n:** retitle `settings.backup_title` / `backup_hint`; drop the now-unused
  `settings.data_title` / `data_hint`. No change to `seed_*` / `clear_*`.

**Not in scope:**
- The seeders themselves and the fresh-family fix (shipped in
  `seed-fresh-family-canonical-tags`).
- Reordering the Data tab's other cards.

## Acceptance criteria
- `uv run pytest tests/e2e/test_settings_data_safety.py -q` (clear moved, still green)
- `uv run pytest tests/e2e/test_settings_seed_panel.py -q` (new: one seeding card)
- `./scripts/verify.sh --e2e` green (views changed → e2e mandatory, rule 8).

## Implementation notes
- The new e2e asserts structure only — it must never *run* wipe+seed or clear
  against the shared e2e worker DB (that would wipe every other test's data),
  so it opens the confirm dialogs and cancels, exactly as the safety test does.
- Clear-all-data moved into the Backup card (retitled "Backups & clearing")
  with its exact label and DELETE-gated dialog unchanged, so the existing
  `test_settings_data_safety` keeps passing in its new home.
- The reset reuses the `settings.seed_*` i18n; the removed "Demo data" card's
  `settings.data_title` / `data_hint` were dropped from both locales (no other
  reference in `src/` or `tests/`, confirmed by i18n-verifier).
- Verified fail-on-old by swapping both views to `git show main:…`: both new
  e2e tests fail on the old two-card structure and pass on the fix;
  `./scripts/verify.sh --e2e` is green (260 e2e).

## Implementation

Landed on 2026-10-15 (PR #274).

| SHA | Author | Date | Message |
|---|---|---|---|
| `751d3ab` | Dawid Adamski | 2026-10-15 | feat(settings): one example-data panel, not two |
| `e9f2a67` | Dawid Adamski | 2026-10-15 | Merge pull request #274 from DawidAdamski/feat/settings-seed-panel-unify |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/settings-seed-panel-unify.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/settings/data_tab.py
- src/kaleta/views/settings/example_data_section.py
- tests/e2e/test_settings_seed_panel.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/e2e/test_settings_data_safety.py -q` | 0 |
| `uv run pytest tests/e2e/test_settings_seed_panel.py -q` | 0 |
| `./scripts/verify.sh --e2e` | 0 |
