"""Credit cards and loans — utilization, amortisation, status computation."""

from __future__ import annotations

import builtins
import calendar
import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account, AccountType
from kaleta.models.credit import CreditCardProfile, LoanProfile
from kaleta.schemas.credit import (
    AmortisationRow,
    CardView,
    CreditCardProfileCreate,
    CreditCardProfileUpdate,
    CreditStatus,
    LoanProfileCreate,
    LoanProfileUpdate,
    LoanView,
)

# Grace period between the statement date and the overdue threshold. We treat
# the payment_due_day as the hard cutoff — a balance paid on or before that day
# is on-time; after it, overdue.
GRACE_DAYS = 0


class CreditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Credit-card CRUD ─────────────────────────────────────────────────

    async def create_card(self, payload: CreditCardProfileCreate) -> CreditCardProfile:
        profile = CreditCardProfile(
            account_id=payload.account_id,
            credit_limit=payload.credit_limit,
            statement_day=payload.statement_day,
            payment_due_day=payload.payment_due_day,
            min_payment_pct=payload.min_payment_pct,
            min_payment_floor=payload.min_payment_floor,
            apr=payload.apr,
        )
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_card(
        self, profile_id: int, payload: CreditCardProfileUpdate
    ) -> CreditCardProfile | None:
        result = await self.session.execute(
            select(CreditCardProfile).where(CreditCardProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def get_card_by_account(self, account_id: int) -> CreditCardProfile | None:
        result = await self.session.execute(
            select(CreditCardProfile).where(CreditCardProfile.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def list_cards(self) -> builtins.list[CardView]:
        """Join Accounts (type=CREDIT) with their CreditCardProfile."""
        result = await self.session.execute(
            select(Account, CreditCardProfile)
            .join(CreditCardProfile, CreditCardProfile.account_id == Account.id)
            .where(Account.type == AccountType.CREDIT)
            .order_by(Account.name)
        )
        today = datetime.date.today()
        views: list[CardView] = []
        for account, profile in result.all():
            # Current balance on a credit card is negative when money owed —
            # normalise to positive "amount owed".
            balance_owed = abs(min(account.balance, Decimal("0")))
            utilization = _compute_utilization(balance_owed, profile.credit_limit)
            min_payment = compute_min_payment(
                balance=balance_owed,
                pct=profile.min_payment_pct,
                floor=profile.min_payment_floor,
            )
            due = next_due_date(profile.payment_due_day, today)
            status = _card_status(balance_owed, due, today)
            views.append(
                CardView(
                    account_id=account.id,
                    account_name=account.name,
                    currency=account.currency,
                    current_balance=balance_owed,
                    credit_limit=profile.credit_limit,
                    utilization_pct=utilization,
                    min_payment=min_payment,
                    next_due_at=due,
                    status=status,
                )
            )
        return views

    # ── Loan CRUD ────────────────────────────────────────────────────────

    async def create_loan(self, payload: LoanProfileCreate) -> LoanProfile:
        monthly_payment = compute_monthly_payment(
            payload.principal, payload.apr, payload.term_months
        )
        profile = LoanProfile(
            account_id=payload.account_id,
            principal=payload.principal,
            apr=payload.apr,
            term_months=payload.term_months,
            start_date=payload.start_date,
            monthly_payment=monthly_payment,
        )
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_loan(
        self, profile_id: int, payload: LoanProfileUpdate
    ) -> LoanProfile | None:
        result = await self.session.execute(
            select(LoanProfile).where(LoanProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(profile, key, value)
        # If a contract field changed, recompute the monthly payment.
        if any(k in data for k in ("principal", "apr", "term_months")):
            profile.monthly_payment = compute_monthly_payment(
                profile.principal, profile.apr, profile.term_months
            )
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def get_loan_by_account(self, account_id: int) -> LoanProfile | None:
        result = await self.session.execute(
            select(LoanProfile).where(LoanProfile.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def list_loans(self) -> builtins.list[LoanView]:
        result = await self.session.execute(
            select(Account, LoanProfile)
            .join(LoanProfile, LoanProfile.account_id == Account.id)
            .order_by(LoanProfile.start_date)
        )
        today = datetime.date.today()
        views: list[LoanView] = []
        for account, profile in result.all():
            months_elapsed = _months_between(profile.start_date, today)
            months_elapsed = max(0, min(months_elapsed, profile.term_months))
            schedule = amortisation_schedule(profile)
            remaining = (
                schedule[months_elapsed - 1].remaining_principal
                if months_elapsed > 0
                else profile.principal
            )
            due = _loan_next_due(profile, today)
            status = _loan_status(profile, months_elapsed, today)
            views.append(
                LoanView(
                    account_id=account.id,
                    account_name=account.name,
                    currency=account.currency,
                    principal=profile.principal,
                    apr=profile.apr,
                    term_months=profile.term_months,
                    monthly_payment=profile.monthly_payment,
                    start_date=profile.start_date,
                    months_elapsed=months_elapsed,
                    remaining_balance=remaining,
                    next_due_at=due,
                    status=status,
                )
            )
        return views

    async def amortisation(self, account_id: int) -> builtins.list[AmortisationRow]:
        profile = await self.get_loan_by_account(account_id)
        if profile is None:
            return []
        return amortisation_schedule(profile)


# ── Pure helpers (exported so tests can exercise them without a session) ─────


def compute_monthly_payment(
    principal: Decimal, apr: Decimal, term_months: int
) -> Decimal:
    """Standard fixed-rate annuity: P * r / (1 - (1+r)^-n).

    APR is given as a percentage (e.g. 12.50 = 12.5%). Returns a 2-dp Decimal.
    """
    if term_months <= 0:
        return Decimal("0.00")
    if apr <= 0:
        return (principal / Decimal(term_months)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    monthly_rate = apr / Decimal("100") / Decimal("12")
    factor = (Decimal("1") + monthly_rate) ** term_months
    payment = principal * monthly_rate * factor / (factor - Decimal("1"))
    return payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amortisation_schedule(profile: LoanProfile) -> builtins.list[AmortisationRow]:
    """Per-month principal/interest breakdown. Last row absorbs rounding so
    the schedule's principal-paid column sums exactly to the initial principal.
    """
    rows: list[AmortisationRow] = []
    remaining = profile.principal
    monthly_rate = profile.apr / Decimal("100") / Decimal("12")
    payment = profile.monthly_payment
    for month_idx in range(1, profile.term_months + 1):
        interest = (remaining * monthly_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        principal_paid = payment - interest
        if month_idx == profile.term_months:
            # Absorb rounding residue into the last principal payment.
            principal_paid = remaining
            interest = (payment - principal_paid).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        remaining = (remaining - principal_paid).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        rows.append(
            AmortisationRow(
                month=month_idx,
                date=_add_months(profile.start_date, month_idx - 1),
                payment=payment,
                principal_paid=principal_paid.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                interest_paid=interest,
                remaining_principal=max(remaining, Decimal("0")),
            )
        )
    return rows


def compute_min_payment(
    *, balance: Decimal, pct: Decimal, floor: Decimal
) -> Decimal:
    """Minimum payment = max(pct × balance, floor), capped at the balance."""
    if balance <= 0:
        return Decimal("0.00")
    by_pct = (balance * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(balance, max(by_pct, floor))


def next_due_date(payment_due_day: int, today: datetime.date) -> datetime.date:
    """Return the next ``payment_due_day`` on or after today."""
    if today.day <= payment_due_day:
        return _clamp_to_month_day(today.year, today.month, payment_due_day)
    # Roll to next month.
    year = today.year + (1 if today.month == 12 else 0)
    month = 1 if today.month == 12 else today.month + 1
    return _clamp_to_month_day(year, month, payment_due_day)


def _compute_utilization(balance_owed: Decimal, limit: Decimal) -> Decimal:
    if limit <= 0:
        return Decimal("0")
    return (balance_owed / limit).quantize(Decimal("0.0001"))


def _card_status(
    balance_owed: Decimal, due: datetime.date, today: datetime.date
) -> CreditStatus:
    if balance_owed <= 0:
        return CreditStatus.ON_TIME
    if today > due + datetime.timedelta(days=GRACE_DAYS):
        return CreditStatus.OVERDUE
    # Within 5 days of the due date with a balance pending → "grace".
    if (due - today).days <= 5:
        return CreditStatus.GRACE
    return CreditStatus.ON_TIME


def _loan_next_due(profile: LoanProfile, today: datetime.date) -> datetime.date:
    """Loans bill on the same day-of-month as the start date."""
    return next_due_date(profile.start_date.day, today)


def _loan_status(
    profile: LoanProfile, months_elapsed: int, today: datetime.date
) -> CreditStatus:
    if months_elapsed >= profile.term_months:
        return CreditStatus.ON_TIME  # already paid off per schedule
    due = _loan_next_due(profile, today)
    if (due - today).days <= 5:
        return CreditStatus.GRACE
    return CreditStatus.ON_TIME


def _months_between(start: datetime.date, end: datetime.date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _add_months(d: datetime.date, months: int) -> datetime.date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return _clamp_to_month_day(year, month, d.day)


def _clamp_to_month_day(year: int, month: int, day: int) -> datetime.date:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, min(day, last_day))


__all__ = [
    "CreditService",
    "amortisation_schedule",
    "compute_min_payment",
    "compute_monthly_payment",
    "next_due_date",
]
