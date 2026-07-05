---
adr_id: "019"
title: "Payee as a First-Class Entity with Merge Support"
status: accepted
---

# ADR-19: Payee as a First-Class Entity with Merge Support

- **Decision**: Introduce a `Payee` model (`payees` table, `name UNIQUE`) and a `PayeeService` with full CRUD, `find_or_create()`, and `merge(keep_id, merge_ids)`. Transactions gain a nullable `payee_id` FK. During mBank CSV import, `ImportService.to_transaction_creates_with_payees()` resolves payee names via `find_or_create()`.
- **Rationale**: Payee names in bank exports are often inconsistent (truncated, all-caps, with bank reference suffixes). A deduplicated `Payee` entity allows users to merge duplicates into a canonical record, after which all historical transactions automatically reflect the merged payee. Separating payee identity from transaction descriptions enables cleaner reporting and future rule-based auto-categorisation.
- **Consequence**: `PayeeService.merge()` bulk-reassigns transactions from the merged payees to the kept payee using a single `UPDATE` statement, then deletes the redundant rows. `find_or_create()` uses `flush()` rather than `commit()` so that the caller owns the transaction boundary. The migration is `alembic/versions/d2e3f4a5b6c7_add_payees.py`.
