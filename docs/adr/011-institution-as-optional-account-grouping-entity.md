---
adr_id: "011"
title: "Institution as Optional Account Grouping Entity"
status: accepted
---

# ADR-11: Institution as Optional Account Grouping Entity

- **Decision**: Introduce an `Institution` model that accounts optionally reference via a nullable `institution_id` FK with `ON DELETE SET NULL`.
- **Rationale**: Users hold accounts at multiple financial institutions (banks, fintechs, brokers, etc.). Grouping accounts by institution is a natural mental model and a frequently needed view. Making the relationship optional preserves backwards compatibility — existing accounts require no migration data entry.
- **Consequence**: `Account` gains `institution_id` (nullable) and an `institution` relationship. Deleting an institution unlinks its accounts rather than cascading deletion. The accounts view gains a toggle to group by Type or by Institution. `InstitutionService` provides full CRUD with eager-loading via `selectinload` for the accounts relationship. `InstitutionType` uses `SAEnum(..., native_enum=False)` for SQLite compatibility, consistent with the rest of the codebase.
