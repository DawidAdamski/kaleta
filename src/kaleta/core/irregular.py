# SPDX-License-Identifier: AGPL-3.0-or-later
"""The irregular-expenses fund's saving rule (``funds-irregular-items``, ``KAL-IRR``).

A yearly cost is saved for at a tenth of it a month, not a twelfth: it is
always dearer than last time, and the two months of slack cover the rise and
whatever surprise the year brings. One rule, used for the user's own items and
for the radar's suggestion alike.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

#: Months a yearly cost is spread over.
IRREGULAR_DIVISOR = 10
_CENTS = Decimal("0.01")


def monthly_contribution(yearly: Decimal) -> Decimal:
    """What to set aside each month for ``yearly``, to the grosz."""
    return (yearly / IRREGULAR_DIVISOR).quantize(_CENTS, rounding=ROUND_HALF_UP)
