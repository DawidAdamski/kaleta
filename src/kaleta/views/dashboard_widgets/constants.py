# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared constants for dashboard widgets."""

from __future__ import annotations

from decimal import Decimal

#: Savings-rate target drawn as the tick on the month card's pace bar.
#: Open question 2 of the restyle-dashboard plan: there is no settings field
#: for this yet, so the widget uses a constant until one exists.
SAVINGS_RATE_TARGET_PCT = Decimal("20")

#: Share of plan above which a budget-variance row reads as expense rather
#: than warning. 110 = 10% past the budget; artboard 1c colours 115% and 139%
#: as expense and 106% as warning.
SEVERE_SPENT_PCT = Decimal("110")
