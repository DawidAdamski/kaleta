---
plan_id: subscriptions-notes
title: Subscriptions — free-text notes per subscription
area: wizard
effort: small
status: draft
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
