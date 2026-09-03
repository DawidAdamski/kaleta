# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregates open action items from every wizard section.

Each section contributes through its own service, so the rules here stay
thin: this module decides *what counts as needing attention* and how loud
it is, never how the underlying data is computed.

Rules are independent ``async`` collectors returning ``list[ActionItem]``,
mirroring ``WizardMentorService``'s per-rule shape.
"""

from __future__ import annotations

import builtins
import calendar
import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.personal_loan import LoanStatus
from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.wizard_actions import (
    ActionItem,
    ActionKind,
    ActionSection,
    ActionSeverity,
)
from kaleta.services.personal_loan_service import PersonalLoanService
from kaleta.services.reserve_fund_service import ReserveFundService
from kaleta.services.subscription_service import SubscriptionService
from kaleta.services.wizard_mentor_service import WizardMentorService


class WizardActionService:
    """Returns the open action items across all wizard sections, ranked."""

    # A loan whose due date is within this many days is "due soon".
    LOAN_DUE_SOON_DAYS = 7
    # Nudge to plan the next month once month-end is this close.
    PLAN_NEXT_MONTH_WITHIN_DAYS = 5
    # Detector candidates are collapsed into one row; below this, stay quiet.
    MIN_SUBSCRIPTION_CANDIDATES = 1

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_action_items(
        self, *, today: datetime.date | None = None
    ) -> builtins.list[ActionItem]:
        """Every open item, sorted ``danger → warning → info``, newest first."""
        ref = today or datetime.date.today()
        items: builtins.list[ActionItem] = []
        for rule in (
            self._subscriptions,
            self._safety_funds,
            self._personal_loans,
            self._monthly_readiness,
            self._getting_started,
        ):
            items.extend(await rule(ref))
        items.sort(key=lambda item: item.sort_key)
        return items

    # ── Subscriptions ─────────────────────────────────────────────────────

    async def _subscriptions(self, ref: datetime.date) -> builtins.list[ActionItem]:
        svc = SubscriptionService(self.session)
        items: builtins.list[ActionItem] = []

        # A renewal whose expected date has passed is the closest thing the
        # model has to "flagged for review" — the charge should have landed.
        # ACTIVE only: muted and cancelled subscriptions must not nag, the
        # same filter ``upcoming_renewals`` applies.
        for sub in await svc.list(status=SubscriptionStatus.ACTIVE):
            due = sub.next_expected_at
            if due is None or due > ref:
                continue
            items.append(
                ActionItem(
                    kind=ActionKind.SUBSCRIPTION_RENEWAL_DUE,
                    section=ActionSection.SUBSCRIPTIONS,
                    severity=ActionSeverity.INFO,
                    title_key="wizard_actions.subscription_renewal_due_title",
                    body_key="wizard_actions.subscription_renewal_due_body",
                    href=f"/wizard/subscriptions?focus={sub.id}",
                    params={"name": sub.name, "date": str(due)},
                    created_at=due,
                )
            )

        candidates = await svc.detect_candidates(today=ref)
        if len(candidates) >= self.MIN_SUBSCRIPTION_CANDIDATES:
            items.append(
                ActionItem(
                    kind=ActionKind.SUBSCRIPTION_CANDIDATES,
                    section=ActionSection.SUBSCRIPTIONS,
                    severity=ActionSeverity.INFO,
                    title_key="wizard_actions.subscription_candidates_title",
                    body_key="wizard_actions.subscription_candidates_body",
                    href="/wizard/subscriptions",
                    count=len(candidates),
                    params={"count": len(candidates)},
                    created_at=max(c.last_seen_at for c in candidates),
                )
            )
        return items

    # ── Safety funds ──────────────────────────────────────────────────────

    async def _safety_funds(self, ref: datetime.date) -> builtins.list[ActionItem]:
        # The model carries no contribution schedule, so "behind" is read off
        # the only progress signal available: balance vs target.
        funds = await ReserveFundService(self.session).list_with_progress(today=ref)
        return [
            ActionItem(
                kind=ActionKind.FUND_BELOW_TARGET,
                section=ActionSection.SAFETY_FUNDS,
                severity=ActionSeverity.WARNING,
                title_key="wizard_actions.fund_below_target_title",
                body_key="wizard_actions.fund_below_target_body",
                href=f"/wizard/safety-funds?focus={fund.id}",
                params={
                    "name": fund.name,
                    "pct": int(fund.progress_pct * 100),
                },
                created_at=ref,
            )
            for fund in funds
            if fund.target_amount > Decimal("0") and fund.progress_pct < Decimal("1")
        ]

    # ── Personal loans ────────────────────────────────────────────────────

    async def _personal_loans(self, ref: datetime.date) -> builtins.list[ActionItem]:
        loans = await PersonalLoanService(self.session).list_loans(status=LoanStatus.OUTSTANDING)
        horizon = ref + datetime.timedelta(days=self.LOAN_DUE_SOON_DAYS)
        items: builtins.list[ActionItem] = []
        for loan in loans:
            due = loan.due_at
            if due is None or due > horizon:
                continue
            overdue = due < ref
            items.append(
                ActionItem(
                    kind=ActionKind.LOAN_OVERDUE if overdue else ActionKind.LOAN_DUE_SOON,
                    section=ActionSection.PERSONAL_LOANS,
                    severity=ActionSeverity.DANGER if overdue else ActionSeverity.WARNING,
                    title_key=(
                        "wizard_actions.loan_overdue_title"
                        if overdue
                        else "wizard_actions.loan_due_soon_title"
                    ),
                    body_key=(
                        "wizard_actions.loan_overdue_body"
                        if overdue
                        else "wizard_actions.loan_due_soon_body"
                    ),
                    href=f"/wizard/personal-loans?focus={loan.id}",
                    params={
                        "name": loan.counterparty.name,
                        "days": abs((due - ref).days),
                    },
                    created_at=due,
                )
            )
        return items

    # ── Monthly readiness ─────────────────────────────────────────────────

    async def _monthly_readiness(self, ref: datetime.date) -> builtins.list[ActionItem]:
        days_left = calendar.monthrange(ref.year, ref.month)[1] - ref.day
        if days_left > self.PLAN_NEXT_MONTH_WITHIN_DAYS:
            return []
        return [
            ActionItem(
                kind=ActionKind.PLAN_NEXT_MONTH,
                section=ActionSection.MONTHLY_READINESS,
                severity=ActionSeverity.INFO,
                title_key="wizard_actions.plan_next_month_title",
                body_key="wizard_actions.plan_next_month_body",
                href="/wizard/monthly-readiness",
                params={"days": days_left},
                created_at=ref,
            )
        ]

    # ── Getting started ───────────────────────────────────────────────────

    async def _getting_started(self, ref: datetime.date) -> builtins.list[ActionItem]:
        suggestions = await WizardMentorService(self.session).suggestions()
        return [
            ActionItem(
                kind=ActionKind.MENTOR_HINT,
                section=ActionSection.GETTING_STARTED,
                severity=ActionSeverity.INFO,
                title_key=s.title_key,
                body_key=s.body_key,
                href=s.cta_url,
                count=int(s.params["count"]) if "count" in s.params else None,
                params={k: v for k, v in s.params.items() if isinstance(v, str | int)},
                created_at=ref,
                dismiss_key=s.key,
            )
            for s in suggestions
        ]


__all__ = ["WizardActionService"]
