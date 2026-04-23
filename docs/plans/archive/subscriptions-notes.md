---
plan_id: subscriptions-notes
title: Subscriptions — free-text notes per subscription
area: wizard
effort: small
status: archived
archived_at: 2026-04-23
roadmap_ref: ../product/financial-wizard.md#3-subscriptions
---

# Subscriptions — free-text notes per subscription

## Intent

The Subscription record today holds structured fields (name, amount,
cadence, dates, URL) but nowhere to jot the context that makes a
tracked subscription actually useful to the user: "Shared with
Marek — he pays half on the 5th", "Cancelled online on 2025-10-12,
customer service ref #ABC", "Family plan through work until Dec
2027", "Free year with new phone, renews at full price". That
context has to live somewhere or the user maintains it outside the
app.

Add a `notes` field on Subscription and surface it in the list so
users can read what they wrote without re-opening the edit dialog.

## Scope

- New column `notes: TEXT NULL` on `subscriptions`.
- Add/Edit dialog gains a multiline textarea below the URL field.
- Subscription row in the panel shows the notes (truncated to one
  line by default, expandable on click) when present.
- Empty notes render nothing — zero layout cost when absent.

Out of scope:
- Markdown rendering / rich text.
- Per-subscription attachment uploads.
- Shared / collaborative notes.
- Search across notes (future cross-cutting search plan).

## Acceptance criteria

- A subscription saved with notes persists them across reload.
- A subscription row with non-empty notes shows a "note" indicator
  (icon + first ~60 chars) beneath the status line.
- Clicking the note indicator expands to show the full notes text
  in-line; clicking again collapses it.
- Edit dialog pre-fills the textarea with existing notes; save
  round-trips unchanged.
- Notes with linebreaks render with linebreaks preserved (whitespace
  pre-line).
- A subscription saved with empty notes stores NULL (not an empty
  string) and the row shows no note indicator.

## Touchpoints

- `src/kaleta/models/subscription.py` — add `notes: Mapped[str | None]`
  with `Text` column type (no length cap; nullable).
- `alembic/versions/<new>_add_subscription_notes.py` — `batch_alter_table`
  to add the column for SQLite compatibility; `server_default=None`,
  nullable=True.
- `src/kaleta/schemas/subscription.py` —
  - `SubscriptionBase`: `notes: str | None = Field(default=None, max_length=4000)`
  - `SubscriptionUpdate`: same optional shape.
  - `SubscriptionResponse`: inherits via Base.
- `src/kaleta/views/subscriptions.py` —
  - Dialog: multiline `ui.textarea(label=…notes…, rows=3)`; pre-fill
    in edit mode; submit normalises empty string to `None`.
  - Row: if `sub.notes`, render a muted "note" block under the
    subtitle with an expand/collapse toggle; use a `sticky_note_2`
    or `notes` icon.
- `src/kaleta/i18n/locales/{en,pl}.json` — add
  `subscriptions.field_notes`, `subscriptions.notes_show`,
  `subscriptions.notes_hide`, `subscriptions.note_indicator`
  (icon label for a11y).

## Open questions

1. **Length cap.** 4000 chars feels generous; SQLite TEXT has no
   hard limit but a Pydantic cap prevents pathological input.
   Default: 4000.
2. **Display collapsed preview length.** 60 chars? 80? 120? Default:
   80, tune after first look.
3. **Archived plan overlap.** The `wizard-subscriptions` plan is
   already archived — changes should not edit that plan file; just
   extend the surface it shipped. This plan is an independent
   follow-up.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `9b6b082` | Dawid | 2026-04-23 | feat(subscriptions): free-text notes per subscription |

**Files changed:**
- `alembic/versions/b6d9c5a2f8e3_add_subscription_notes.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `src/kaleta/models/subscription.py`
- `src/kaleta/schemas/subscription.py`
- `src/kaleta/views/subscriptions.py`

**What shipped:**
- `notes: TEXT NULL` column on subscriptions; batch migration works on SQLite dev DB and user's adamscy.db.
- Pydantic `Field` with `max_length=4000` caps pathological input without blocking realistic notes.
- Add/Edit dialog gains a multiline `ui.textarea` with `rows=3 autogrow` below the URL field; pre-filled on edit, normalised to `None` on empty-string save.
- Row renderer adds a `_sub_row_notes` helper that injects a `sticky_note_2` icon + preview (80 chars max, linebreaks collapsed to spaces) under the subtitle when `sub.notes` is truthy. Clicking the preview toggles to the full note with `whitespace-pre-line` so multi-line content keeps its layout.
- Click-to-toggle is skipped when the note fits in the preview (<=80 chars AND no linebreaks) — no meaningless affordance.
- Rows without notes render unchanged — zero vertical cost when absent.
- Verified live: saved a note through the Edit dialog on the dev DB, row showed the truncated preview with ellipsis, click expanded to the full text, delete cleared the record.

**Partial coverage / deferred:**
- **Markdown rendering** — notes render as plain text only; no links, bold, lists. The URL field already exists for cancellation URLs.
- **Attachments** — out of scope per plan.
- **Search across notes** — future cross-cutting search plan.
- **Collapsed-preview length** — fixed at 80 chars per plan's Open question #2 default; tune later if too tight/loose.
- **Known Quasar quirk** — `ui.textarea`'s reactive binding only fires on keystroke-level input events, not on one-shot DOM value replacement (Playwright `.fill()`). Real user typing works; automated E2E needs `press_sequentially` or `slowly=True` if future scenario tests are written. Not a bug, but flagged for future test authors.
