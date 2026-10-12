# SPDX-License-Identifier: AGPL-3.0-or-later
"""The household's additions to the ledger: the "Added by" column and filter.

``hosted-household-sharing`` §4 (KAL-HHS-016 drives the query through the
services); these pin what the page draws from it.
"""

from __future__ import annotations

from kaleta.services.member_name_service import MemberNameService
from kaleta.views.components.filter_bar import active_filter_count, filter_chip_label
from kaleta.views.components.transaction_table import attach_added_by, transaction_columns

MEMBERS = {1: "jan", 2: "ania"}


def test_each_row_names_who_added_it_and_a_plan_reads_as_a_dash() -> None:
    rows = [{"id": 5, "user_id": 2}, {"id": 6, "user_id": None}, {"id": "p1", "is_planned": True}]
    assert [r["added_by"] for r in attach_added_by(rows, MEMBERS)] == ["ania", "—", "—"]


def test_the_column_sits_before_the_row_actions_only_when_asked() -> None:
    assert "added_by" not in [c["name"] for c in transaction_columns()]
    names = [c["name"] for c in transaction_columns(added_by=True)]
    assert names[-2:] == ["added_by", "actions"]


def test_the_chip_reads_the_members_chosen() -> None:
    label = filter_chip_label(
        "members",
        {"user_ids": [2, 1]},
        account_options={},
        category_options={},
        type_options={},
        tag_options={},
        member_options=MEMBERS,
    )
    assert label == ("ania", "+1")
    assert active_filter_count({"user_ids": [2]}) == 1


def test_a_member_is_their_chosen_name_else_their_address_before_the_at() -> None:
    assert MemberNameService.name("Ania", "ania@example.com") == "Ania"
    assert MemberNameService.name(None, "ania@example.com") == "ania"
    assert MemberNameService.name("", "jan") == "jan"


def test_a_household_is_two_or_more() -> None:
    assert not MemberNameService.is_household({1: "jan"})
    assert MemberNameService.is_household(MEMBERS)
