---
adr_id: "013"
title: "Service-Level Filtering and Pagination for Transactions"
status: accepted
---

# ADR-13: Service-Level Filtering and Pagination for Transactions

- **Decision**: `TransactionService.list()` accepts `account_ids`, `category_ids`, `tx_types`, `date_from`, `date_to`, `search`, `offset`, and `limit` (default 50). A companion `TransactionService.count()` method accepts the same filter parameters and returns the total matching row count.
- **Rationale**: Returning all transactions in one query is impractical as history grows. Placing filter and pagination logic in the service keeps controllers and views thin and makes the same capability available to both the UI and the REST API. Providing a separate `count()` method avoids fetching full rows just for pagination metadata.
- **Consequence**: Multiple values within the same filter field use OR logic; different filter fields combine with AND. The transactions UI exposes a filter panel (date range, multi-select accounts/categories/types, description search) and a pagination control that shows total count.
