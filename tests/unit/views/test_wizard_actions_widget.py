# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the wizard action-items widget's pure helpers.

``drop_dismissed`` is the one piece of logic the widget owns: mentor-hint
dismissals live in browser storage, so the services layer cannot filter them.
"""

from __future__ import annotations

import datetime

from kaleta.schemas.wizard_actions import (
    ActionItem,
    ActionKind,
    ActionSection,
    ActionSeverity,
)
from kaleta.views.dashboard_widgets.wizard_actions import drop_dismissed

TODAY = datetime.date(2026, 6, 10)


def _mentor(dismiss_key: str) -> ActionItem:
    return ActionItem(
        kind=ActionKind.MENTOR_HINT,
        section=ActionSection.GETTING_STARTED,
        severity=ActionSeverity.INFO,
        title_key="wizard.mentor_uncategorised_title",
        body_key="wizard.mentor_uncategorised_body",
        href="/transactions",
        created_at=TODAY,
        dismiss_key=dismiss_key,
    )


def _loan() -> ActionItem:
    return ActionItem(
        kind=ActionKind.LOAN_OVERDUE,
        section=ActionSection.PERSONAL_LOANS,
        severity=ActionSeverity.DANGER,
        title_key="wizard_actions.loan_overdue_title",
        body_key="wizard_actions.loan_overdue_body",
        href="/wizard/personal-loans?focus=1",
        created_at=TODAY,
    )


def test_dismissed_mentor_hint_is_removed() -> None:
    items = [_loan(), _mentor("uncategorised")]

    result = drop_dismissed(items, {"uncategorised"})

    assert [i.kind for i in result] == [ActionKind.LOAN_OVERDUE]


def test_other_dismissals_leave_the_hint_alone() -> None:
    items = [_mentor("uncategorised")]

    assert drop_dismissed(items, {"no_budget"}) == items


def test_items_without_a_dismiss_key_always_survive() -> None:
    items = [_loan()]

    # Even a matching-looking key cannot dismiss a non-mentor item.
    assert drop_dismissed(items, {"uncategorised", "no_budget"}) == items


def test_empty_dismissal_set_returns_the_list_unchanged() -> None:
    items = [_loan(), _mentor("uncategorised")]

    assert drop_dismissed(items, set()) == items


def test_every_hint_dismissed_leaves_an_empty_list() -> None:
    items = [_mentor("uncategorised"), _mentor("no_budget")]

    assert drop_dismissed(items, {"uncategorised", "no_budget"}) == []
