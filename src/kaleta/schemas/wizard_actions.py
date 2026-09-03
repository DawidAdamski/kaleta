# SPDX-License-Identifier: AGPL-3.0-or-later
"""Action items aggregated from every wizard section for the dashboard widget.

Items carry i18n *keys* plus interpolation ``params`` rather than rendered
strings: the services layer never imports ``kaleta.i18n`` (see
``WizardMentorService.MentorSuggestion`` for the same shape), so the widget
does the translating.
"""

from __future__ import annotations

import datetime
import enum

from pydantic import BaseModel, Field

__all__ = [
    "ActionItem",
    "ActionKind",
    "ActionSection",
    "ActionSeverity",
]


class ActionSeverity(enum.StrEnum):
    """How loudly an item asks for attention. Ordered least → most urgent."""

    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"


class ActionSection(enum.StrEnum):
    """Which wizard section produced the item — the widget groups by this."""

    SUBSCRIPTIONS = "subscriptions"
    SAFETY_FUNDS = "safety_funds"
    PERSONAL_LOANS = "personal_loans"
    MONTHLY_READINESS = "monthly_readiness"
    GETTING_STARTED = "getting_started"


class ActionKind(enum.StrEnum):
    """The specific rule that fired. One i18n message per kind."""

    SUBSCRIPTION_RENEWAL_DUE = "subscription_renewal_due"
    SUBSCRIPTION_CANDIDATES = "subscription_candidates"
    FUND_BELOW_TARGET = "fund_below_target"
    LOAN_DUE_SOON = "loan_due_soon"
    LOAN_OVERDUE = "loan_overdue"
    PLAN_NEXT_MONTH = "plan_next_month"
    MENTOR_HINT = "mentor_hint"


# Sort weight: danger first, then warning, then info.
_SEVERITY_RANK: dict[ActionSeverity, int] = {
    ActionSeverity.DANGER: 0,
    ActionSeverity.WARNING: 1,
    ActionSeverity.INFO: 2,
}


class ActionItem(BaseModel):
    """One row in the wizard action-items widget."""

    kind: ActionKind
    section: ActionSection
    severity: ActionSeverity
    title_key: str
    body_key: str
    href: str
    count: int | None = None
    params: dict[str, str | int] = Field(default_factory=dict)
    created_at: datetime.date = Field(
        ...,
        description="Date the item became actionable; newest first inside a severity bucket.",
    )
    # Only set for mentor hints, whose dismissals live in browser storage and
    # can therefore only be filtered by the view.
    dismiss_key: str | None = None

    @property
    def sort_key(self) -> tuple[int, int]:
        """``danger → warning → info``, newest first within each bucket."""
        return (_SEVERITY_RANK[self.severity], -self.created_at.toordinal())
