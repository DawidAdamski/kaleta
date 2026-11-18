# SPDX-License-Identifier: AGPL-3.0-or-later
"""The unified Budgets page's routing rules, without a browser.

The old ``/budget-plan`` shim, which tab a ``?tab=`` value opens, and which tab
an Alt+digit asks for. The page itself is exercised end to end in
``tests/e2e/test_budgets_unified.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui.events import KeyboardAction, KeyboardKey, KeyboardModifiers, KeyEventArguments

from kaleta.views.budget_plan import plan_redirect
from kaleta.views.budgets.page import tab_key_for, tab_key_for_shortcut
from kaleta.views.layout import nav_destinations


def _key(
    code: str, *, alt: bool = True, keydown: bool = True, name: str = "1"
) -> KeyEventArguments:
    return KeyEventArguments(
        sender=MagicMock(),
        client=MagicMock(),
        action=KeyboardAction(keydown=keydown, keyup=not keydown, repeat=False),
        key=KeyboardKey(name=name, code=code, location=0),
        modifiers=KeyboardModifiers(alt=alt, ctrl=False, meta=False, shift=False),
    )


def test_the_old_planning_address_is_a_302_onto_the_plan_tab() -> None:
    response = plan_redirect()

    assert response.status_code == 302
    assert response.headers["location"] == "/budgets?tab=plan"


def test_the_sidebar_no_longer_links_the_old_planning_address() -> None:
    assert "/budget-plan" not in [path for _icon, path, _key in nav_destinations()]
    assert "/budgets" in [path for _icon, path, _key in nav_destinations()]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", "realization"),
        ("realization", "realization"),
        ("plan", "plan"),
        ("overview", "overview"),
        ("forecast", "realization"),
        ("PLAN", "realization"),
    ],
)
def test_a_tab_query_opens_its_tab_and_anything_else_opens_realization(
    query: str, expected: str
) -> None:
    assert tab_key_for(query) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [("Digit1", "overview"), ("Digit2", "realization"), ("Digit3", "plan")],
)
def test_alt_digit_picks_the_tab_standing_in_that_place(code: str, expected: str) -> None:
    # macOS types "¡" for Alt+1: the physical key decides, not the character.
    assert tab_key_for_shortcut(_key(code, name="¡")) == expected


@pytest.mark.parametrize(
    "event",
    [
        _key("Digit1", alt=False),
        _key("Digit1", keydown=False),
        _key("Digit4"),
        _key("Digit0"),
        _key("KeyP", name="p"),
    ],
    ids=["no-alt", "keyup", "no-fourth-tab", "zero", "not-a-digit"],
)
def test_other_keys_leave_the_tab_alone(event: KeyEventArguments) -> None:
    assert tab_key_for_shortcut(event) is None
