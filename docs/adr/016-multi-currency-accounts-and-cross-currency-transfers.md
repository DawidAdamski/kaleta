---
adr_id: "016"
title: "Multi-Currency Accounts and Cross-Currency Transfers"
status: accepted
---

# ADR-16: Multi-Currency Accounts and Cross-Currency Transfers

- **Decision**: Each `Account` carries a `currency` field (3-char ISO 4217 code, `VARCHAR(3) NOT NULL DEFAULT 'PLN'`). Each `Transaction` carries a nullable `exchange_rate` field (`NUMERIC(15,6)`), storing dest_currency per 1 src_currency for cross-currency transfers. `TransactionService.create_transfer(outgoing, incoming)` atomically creates both legs with linked IDs. `NetWorthService.get_summary(rates, default_currency)` accepts a `rates` dict (`currency → Decimal`) and converts all account balances to the user's default currency before aggregation.
- **Rationale**: Users holding accounts in multiple currencies need balances and net worth totals expressed in a single reporting currency. Storing the exchange rate on the transaction preserves the historical rate at the time of transfer, which would otherwise be lost if only a rates table were kept. Atomically creating both transfer legs in one service call prevents orphaned half-transfers.
- **Consequence**: The migration `alembic/versions/a1b2c3d4e5f6_add_currency_and_exchange_rate.py` adds `accounts.currency` and `transactions.exchange_rate`. The Settings page exposes a default currency selector and per-currency manual rate editor. The Accounts add/edit dialog includes a currency selector. The Transactions page shows a "To Account" selector when Transfer type is chosen, and an exchange rate panel for cross-currency transfers (enter rate OR source+destination amounts; the remaining field auto-calculates). The Net Worth page displays each foreign-currency account row with native balance alongside the converted balance, and all summary totals in the default currency.
