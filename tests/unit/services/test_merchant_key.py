# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the shared merchant-key normaliser.

Pins the behaviour across the move out of ``subscription_service`` — the
mappings are literal expectations, not computed from the function under test.
"""

from __future__ import annotations

import pytest

from kaleta.services.merchant_key import merchant_key_from_description


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Netflix", "NETFLIX"),
        ("HBO Europe S.R.O /Prague", "HBO EUROPE S.R.O"),
        ("Disney Plus /Hoofddorp", "DISNEY PLUS"),
        ("  spotify   ab ", "SPOTIFY AB"),
        ("", ""),
        (None, ""),
    ],
)
def test_merchant_key_from_description(description: str | None, expected: str) -> None:
    assert merchant_key_from_description(description) == expected


def test_merchant_key_is_length_capped() -> None:
    long_name = "A" * 100
    assert len(merchant_key_from_description(long_name)) == 40
