# SPDX-License-Identifier: AGPL-3.0-or-later
"""``account_number_matches``: one rule for "this statement row names that own account".

Plan ``import-mbank-transfer-account-suffix``: the statement's counterparty
must be a full number (at least 26 digits), the stored number at least the
blind-index width (8), and the statement number must end with the stored one.
"""

from __future__ import annotations

import pytest

from kaleta.db.types import account_number_matches

FULL = "55 1140 2004 0000 3302 7888 6836"


def test_account_number_matches_full_against_full() -> None:
    assert account_number_matches("55114020040000330278886836", FULL) is True


def test_account_number_matches_stored_ten_digit_tail() -> None:
    """What every mBank import before this plan stored."""
    assert account_number_matches("0278886836", FULL) is True


def test_account_number_matches_stored_eight_digit_tail() -> None:
    assert account_number_matches("78886836", FULL) is True


def test_account_number_matches_ignores_spaces_and_dashes() -> None:
    assert account_number_matches("02 7888-6836", "PL55114020040000330278886836") is True


@pytest.mark.parametrize("stored", ["8886836", "", None])
def test_account_number_matches_rejects_a_stored_number_under_eight_digits(
    stored: str | None,
) -> None:
    assert account_number_matches(stored, FULL) is False


@pytest.mark.parametrize(
    "statement",
    ["0278886836", "5511402004000033027888683", "", None, "4111 **** **** 6836"],
)
def test_account_number_matches_rejects_a_statement_number_under_26_digits(
    statement: str | None,
) -> None:
    """References, masked cards and short columns never match, whatever is stored."""
    assert account_number_matches("0278886836", statement) is False


def test_account_number_matches_rejects_a_different_tail() -> None:
    assert account_number_matches("0299991234", FULL) is False


def test_account_number_matches_rejects_a_stored_number_in_the_middle() -> None:
    """The stored digits must be the statement number's end, not any part of it."""
    assert account_number_matches("11402004", FULL) is False
