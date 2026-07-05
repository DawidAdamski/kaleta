---
adr_id: "023"
title: "Credit Calculator as a Stateless Pure-Python Service"
status: accepted
---

# ADR-23: Credit Calculator as a Stateless Pure-Python Service

- **Decision**: The credit calculator (`/credit-calculator`) performs all amortization math in `CreditService` without persisting any data to the database.
- **Rationale**: Loan amortization is a deterministic calculation: given principal, rate, term, and installment type, the full schedule can be derived on the fly. Storing schedules would require invalidation logic whenever inputs change. A stateless service keeps the feature simple.
- **Consequence**: Amortization logic lives directly in `views/credit_calculator.py` or a co-located helper, with no ORM dependency. Equal and decreasing installment schedules each return a list of dataclasses (period, installment, principal, interest, remaining balance). Overpayment variants accept an extra monthly amount or a one-off lump sum at a given period. The view renders results in an ECharts chart and a scrollable amortization table. No migration is required.
