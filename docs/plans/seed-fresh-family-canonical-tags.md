---
plan_id: seed-fresh-family-canonical-tags
title: Example-data seeding fails on a fresh family's canonical tags
area: platform
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#seed
---

# Example-data seeding fails on a fresh family's canonical tags

## Intent
Dogfooding: "Seed everything" (Settings → Data → Example data, and the
`scripts/seed.py` CLI behind it) blew up on a brand-new family. The
`taxonomy` seeder inserted the eight `CANONICAL_TAGS` unconditionally, but
every family schema already carries them — migration `b9d4e2c8a1f5` seeds them
on create — so the insert died on `uq_tags_name_bidx`. After a wipe + reseed it
worked, because the wipe cleared the tags first; only the truly-fresh path hit
it. This blocks a clean first-run demo.

## Root cause
`taxonomy.py` built `tags = [Tag(...) for … in CANONICAL_TAGS]` and added them
blindly, while the subscription children a few lines above already guard
themselves by blind index (`exact_index(name) not in filed`). The tags lacked
the same skip.

## Scope
- **`src/kaleta/seeders/taxonomy.py` only:** read the existing tag blind
  indexes and insert only the canonical tags not already filed — mirroring the
  subscription-children guard. The returned `tags` count then reflects rows
  actually added, keeping the seeder idempotent.

**Not in scope:**
- Payees/categories: no migration pre-seeds them, so they do not collide on a
  fresh family; the feature-level "already seeded" check still covers reseeds.
- Consolidating the two Settings seed panels (wipe+seed vs per-feature) — a
  separate UX slice.

## Acceptance criteria
- `uv run pytest tests/integration/test_new_family_seed.py -q`
- `./scripts/verify.sh` green (no view change → short gate; seeder layer only).

## Implementation notes
- Verified fail-on-old / pass-on-new by swapping in `git show main:…taxonomy.py`:
  the new test fails on the old seeder with a `uq_tags_name_bidx` unique
  violation and passes on the fix.
- The integration schema is built by `create_all`, not Alembic, so migration-
  seeded rows are absent; the test plants the eight canonical tags itself to
  stand in for migration `b9d4e2c8a1f5`, exactly as the sibling KAL-PLT-010
  test plants the subscriptions root.
