# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared constants for dashboard widgets."""

from __future__ import annotations

from decimal import Decimal

#: Savings-rate target drawn as the tick on the month card's pace bar.
#: Open question 2 of the restyle-dashboard plan: there is no settings field
#: for this yet, so the widget uses a constant until one exists.
SAVINGS_RATE_TARGET_PCT = Decimal("20")
