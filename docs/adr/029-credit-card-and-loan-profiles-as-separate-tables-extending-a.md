---
adr_id: "029"
title: "Credit Card and Loan Profiles as Separate Tables Extending Account"
status: accepted
---

# ADR-29: Credit Card and Loan Profiles as Separate Tables Extending Account

- **Decision**: `CreditCardProfile` and `LoanProfile` are standalone tables (`credit_card_profiles`, `loan_profiles`), each with a one-to-one FK to `accounts.id` (CASCADE delete, one profile per account). Credit accounts use `type=CREDIT` with a **negative** balance convention (money owed is stored negative; views normalise to positive "amount owed" for display). Rich credit fields live in the profile tables rather than on `accounts`.
- **Rationale**: Stuffing credit-specific columns (APR, credit limit, billing cycle, loan term, amortisation type, etc.) directly onto `Account` would bloat the table and add nullable columns that are meaningless for non-credit accounts. A separate profile preserves a clean `Account` schema while allowing credit-specific queries to operate on a dedicated table. Reusing `Account` for the balance ledger avoids duplicating transaction, transfer, and multi-currency machinery.
- **Consequence**: Migration `c7e9b3f1a2d5_add_credit_and_loan_profiles.py`. `CreditService` provides card CRUD (`create_card`, `update_card`, `get_card_by_account`, `list_cards`) and loan CRUD (`create_loan`, `update_loan`, `get_loan_by_account`, `list_loans`, `amortisation`). Pure helpers (`compute_monthly_payment`, `amortisation_schedule`, `compute_min_payment`, `next_due_date`) contain no ORM dependency. Utilization thresholds: green < 30 %, amber < 70 %, red ≥ 70 %. Minimum payment = max(2 % × balance, 30 PLN), capped at balance. Amortisation uses the standard fixed-rate annuity formula; the last row absorbs rounding so `Σ principal_paid == principal` exactly. Status chips: on-time / due-soon (≤ 5 days) / overdue. Variable-rate loans and mid-life APR changes are out of scope.
