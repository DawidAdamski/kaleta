---
adr_id: "015"
title: "Physical Assets as a Separate Model from Bank Accounts"
status: accepted
---

# ADR-15: Physical Assets as a Separate Model from Bank Accounts

- **Decision**: Introduce a standalone `Asset` model (table `assets`) for physical, non-liquid assets such as real estate, vehicles, and valuables. Physical assets are not represented as `Account` rows.
- **Rationale**: Bank accounts have transaction history, balances derived from ledger entries, and institution relationships. Physical assets have none of these: their value is a single user-supplied figure, optionally paired with a purchase date and purchase price for gain/loss context. Forcing them into the `Account` model would require nullable columns for transaction-irrelevant fields and special-casing throughout the transaction, import, and budget logic. A dedicated model keeps both concepts clean.
- **Consequence**: `Asset` has fields `name`, `type` (`AssetType`: `REAL_ESTATE`, `VEHICLE`, `VALUABLES`, `OTHER`), `value` (Decimal), `description`, `purchase_date` (optional), and `purchase_price` (optional). `AssetType` uses `SAEnum(..., native_enum=False)` for SQLite compatibility. `AssetService` provides full CRUD (`list`, `get`, `create`, `update`, `delete`). `NetWorthService.get_summary()` loads physical assets via `_load_physical_assets()` and exposes them as `PhysicalAssetSnapshot` dataclasses inside `NetWorthSummary`. `total_assets` includes `total_physical_assets`; the monthly history reconstruction adds the physical asset total to the running net worth baseline. The net worth page gains an Add/Edit/Delete CRUD section for physical assets. The migration is `alembic/versions/d7a3e1f2b8c5_add_assets.py`.
