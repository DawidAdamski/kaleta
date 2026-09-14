# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budgets view constants."""

from __future__ import annotations

from kaleta.services.budget_service import RealizationStatus

#: The pace bar's fill, by the same threshold the status word used.
PACE_FILL: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "var(--k-income)",
    RealizationStatus.WARNING: "var(--k-warning)",
    RealizationStatus.OVER: "var(--k-expense)",
}

STATUS_LABEL_KEY: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "budgets.realization.status_on_track",
    RealizationStatus.WARNING: "budgets.realization.status_warning",
    RealizationStatus.OVER: "budgets.realization.status_over",
}
