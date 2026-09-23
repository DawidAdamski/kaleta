# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auth response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

__all__ = ["MfaStatusResponse"]


class MfaStatusResponse(BaseModel):
    """Whether the signed-in user has a second factor, and how healthy it is.

    Read-only on purpose: enrolling needs a QR code in front of a person, so
    ``KALETA_MODE=api`` can report the state but never change it.
    """

    enabled: bool = Field(description="True once a code has confirmed the enrolment")
    enabled_at: datetime | None = Field(
        default=None,
        description="When the second factor was confirmed, or null when it is off",
    )
    recovery_codes_remaining: int = Field(
        description="How many one-time recovery codes are still unused"
    )
