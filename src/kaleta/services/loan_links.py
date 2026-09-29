# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which ledger transactions are personal-loan money rather than income/spending.

A transaction is loan money when a ``PersonalLoan`` points at it (the principal
changing hands) or a ``PersonalLoanRepayment`` does (money coming back). The
link itself is the single source of truth — there is no flag on the
transaction to keep in sync — so reports join through it.
"""

from __future__ import annotations

from sqlalchemy import Select, select, union

from kaleta.models.personal_loan import PersonalLoan, PersonalLoanRepayment


def loan_linked_transaction_ids() -> Select[tuple[int]]:
    """Return a select of every transaction id linked to a loan or repayment.

    NULLs are filtered out so the result is safe inside ``NOT IN`` — one NULL
    there would make the predicate unknown for every row.
    """
    principal = select(PersonalLoan.transaction_id.label("id")).where(
        PersonalLoan.transaction_id.is_not(None)
    )
    repayment = select(PersonalLoanRepayment.linked_transaction_id.label("id")).where(
        PersonalLoanRepayment.linked_transaction_id.is_not(None)
    )
    linked = union(principal, repayment).subquery("loan_linked")
    return select(linked.c.id)


__all__ = ["loan_linked_transaction_ids"]
