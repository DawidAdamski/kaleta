---
adr_id: "012"
title: "Split Transactions (GnuCash-style)"
status: accepted
---

# ADR-12: Split Transactions (GnuCash-style)

- **Decision**: Add a `TransactionSplit` child model. A `Transaction` with `is_split=True` carries one or more `TransactionSplit` rows that each hold a `category_id`, `amount`, and optional `note`. The parent transaction's category is unused when splits are present.
- **Rationale**: Single-category transactions cannot represent real-world receipts that span multiple budget categories (e.g., a supermarket run covering groceries, household, and personal care). GnuCash's split model is the established pattern for this.
- **Consequence**: `Transaction` gains `is_split: bool` and a `splits` relationship. `TransactionSplitCreate` validates that splits are present when `is_split=True`. `TransactionService.create()` uses `flush()` to obtain the transaction `id` before writing split rows. `get()` and `list()` eager-load splits with their category. The Alembic migration is `c4f9e2b1a837_add_transaction_splits.py`. The add-transaction dialog in the UI toggles split mode with a balance indicator and a Fill Last button.
