---
plan_id: institutions-logos
title: Bank logos on institutions
area: institutions
effort: small
status: draft
roadmap_ref: ../roadmap.md#institutions
---

# Bank logos on institutions

## Intent

Institutions should be instantly recognisable by their logo.

## Scope

- Add an optional `logo_path` column on `Institution`.
- Serve logos from a static folder (`static/logos/` or similar).
- Render the logo on the Institutions list, the Accounts list
  (next to the account), and any card displaying an institution
  name.
- Fallback when no logo exists: first-letter circular avatar in
  the institution's primary colour.
- Ship a small starter set for common Polish banks (user can
  drop more into the folder later).

Starter set candidates: PKO BP, mBank, Santander, ING BSK, Pekao,
BNP Paribas, Millennium, Alior, Credit Agricole, Revolut, Wise.

Out of scope:
- Auto-matching a bank based on institution name (deferred —
  user picks the logo from a dropdown or uploads one).
- Colour extraction from logos.

## Acceptance criteria

- Institutions view shows the logo next to each row.
- Accounts view shows a small logo next to the institution label.
- Missing logo shows the letter avatar, never a broken image.
- Logo upload or pick-from-shipped-set UI works.

## Touchpoints

- Alembic migration adding `logo_path VARCHAR NULL` on
  `institutions`.
- `src/kaleta/models/institution.py`.
- `src/kaleta/schemas/institution.py`.
- `src/kaleta/views/institutions.py` — logo upload / pick control.
- `src/kaleta/views/accounts.py` — render small logo.
- A new folder e.g. `static/logos/` served by FastAPI/NiceGUI.
- A shipped subfolder with starter SVGs/PNGs.

## Open questions

- Where exactly do we mount static assets in NiceGUI? Check
  existing static handling first.
- File format: prefer SVG for crispness at any size; accept PNG
  for uploads.
- Can we legally redistribute bank logos? Safer path: ship
  generic placeholders, let user upload.

## Implementation notes

_(filled as work progresses)_
