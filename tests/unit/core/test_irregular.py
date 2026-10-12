# SPDX-License-Identifier: AGPL-3.0-or-later
"""The irregular fund's ÷10 rule (``funds-irregular-items``)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from kaleta.core.irregular import monthly_contribution


@pytest.mark.parametrize(
    ("yearly", "monthly"),
    [
        ("1200.00", "120.00"),
        ("1450.00", "145.00"),
        # Half a grosz rounds up, never down to less than the year needs.
        ("1000.05", "100.01"),
        ("0.00", "0.00"),
    ],
)
def test_a_tenth_of_the_year_to_the_grosz(yearly: str, monthly: str) -> None:
    assert monthly_contribution(Decimal(yearly)) == Decimal(monthly)
