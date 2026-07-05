---
adr_id: "020"
title: "Transfer Detection via Counterparty Account Number Matching"
status: accepted
---

# ADR-20: Transfer Detection via Counterparty Account Number Matching

- **Decision**: During mBank CSV import, `ImportService.to_transaction_creates_with_payees()` marks a row as `TRANSFER` (with `is_internal_transfer=True`) only when the row's `Numer rachunku` field (digits-only) appears in the caller-supplied `known_account_digits` set — the digit-normalised `external_account_number` values of the user's own accounts.
- **Rationale**: Generic heuristics (description keyword matching, amount pairing) produce false positives. Matching against the literal counterparty account number is deterministic and requires no fuzzy logic. Using a `known_account_digits` parameter keeps the import service stateless with respect to account data; the caller queries and passes the set.
- **Consequence**: Rows whose counterparty account is not in `known_account_digits` are classified as normal income/expense. After import, `ImportService.detect_and_link_transfers()` can pair unlinked `TRANSFER` legs across accounts (same amount ± tolerance, dates within `max_days_apart`) and write `linked_transaction_id` on both rows.
