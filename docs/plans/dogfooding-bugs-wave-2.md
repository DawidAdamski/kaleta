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
Covers six reported items. Two of them (#2, #7) turned out to already have a
working implementation — see Open questions; their slices are reframed as
"make it obvious / surface it", pending the user's steer, and are **not**
started until that steer lands.

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
5. **#2 — Group-by active highlight (reframe: make it obvious).** A highlight
   already exists (ink fill + weight). Pending user steer on whether to
   strengthen it.
6. **#7 — Import history (reframe: surface it).** History already exists in a
   collapsed expansion. Pending user steer on prominence.

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
- `src/kaleta/views/theme.py`, `transaction_table.py` — grouping highlight (#2)
- `src/kaleta/views/import_view/coverage_section.py` — history prominence (#7)
- `docs/bdd.md` — KAL scenarios per slice

## Open questions
- **#2 and #7 already work.** The map found: the grouping toggle already
  fills the active option with ink + bumps its weight
  (`theme.py` `.k-segment .q-btn.bg-primary`), and import history already
  renders via `ImportRun` + `list_recent_runs` in a `ui.expansion` in
  `coverage_section.py`. So neither is "broken". Need the user's steer:
  strengthen the grouping highlight? expand history out of the collapsed
  expansion? Do not ship a speculative restyle (Working Agreement §4).

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
