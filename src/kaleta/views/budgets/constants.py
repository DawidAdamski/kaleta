"""Budgets view constants."""

from __future__ import annotations

from kaleta.services.budget_service import RealizationStatus

STATUS_COLOUR: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "positive",
    RealizationStatus.WARNING: "amber-7",
    RealizationStatus.OVER: "negative",
}

STATUS_LABEL_KEY: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "budgets.realization.status_on_track",
    RealizationStatus.WARNING: "budgets.realization.status_warning",
    RealizationStatus.OVER: "budgets.realization.status_over",
}
