---
plan_id: tags-seed-list
title: Seed tags on first run
area: tags
effort: small
status: draft
roadmap_ref: ../roadmap.md#tags
---

# Seed tags on first run

## Intent

Common tags should exist out-of-the-box so the user isn't greeted
with an empty list. User can delete any of them freely.

## Scope

- Define a canonical seed list (see below).
- Insert tags on fresh database initialisation only — never on an
  existing database.
- Translate labels through the i18n layer (so a Polish install gets
  Polish names).

Proposed seed list:

| Key | EN | PL |
|---|---|---|
| transfer | Transfer | Przelew |
| card | Card | Karta |
| cash | Cash | Gotówka |
| online | Online | Online |
| subscription | Subscription | Subskrypcja |
| refundable | Refundable | Do zwrotu |
| business | Business | Firmowe |
| recurring | Recurring | Cykliczne |

Out of scope:
- Colour for each tag — add once a colour column exists on the `Tag`
  model (separate plan).

## Acceptance criteria

- New DB: after `alembic upgrade head` the 8 seeded tags exist.
- Existing DB: no duplicates created; existing user tags untouched.
- Deleting a seeded tag does not bring it back on next boot.

## Touchpoints

- `scripts/seed.py` — add the seed block (or a dedicated
  `scripts/seed_tags.py`).
- `src/kaleta/i18n/locales/en.json`, `pl.json` — add translation
  keys if we render localised names, OR insert the native-language
  label directly based on current locale at seed time.
- No schema changes.

## Open questions

- Are the 8 above the right set? Candidates dropped: "paid",
  "unpaid", "tip", "refund". Revisit once we see real usage.
- Translation strategy: store the English key and translate at
  render time, OR insert whichever language was active at
  seed time? Lean on the first — the `Tag.name` becomes the
  display value only if no translation key matches.

## Implementation notes

_(filled as work progresses)_
