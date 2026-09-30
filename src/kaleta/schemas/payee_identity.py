# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_pattern(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("pattern must not be blank")
    return cleaned


class PayeeIdentityCreate(BaseModel):
    """A spelling of a payee's name, as bank data writes it (literal, not a regex)."""

    pattern: str = Field(..., min_length=1, max_length=200)
    case_sensitive: bool = False

    @field_validator("pattern")
    @classmethod
    def _clean(cls, value: str) -> str:
        return _clean_pattern(value)


class PayeeIdentityUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    case_sensitive: bool | None = None

    @field_validator("pattern")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return None if value is None else _clean_pattern(value)


class PayeeIdentityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payee_id: int
    pattern: str
    case_sensitive: bool
    created_at: datetime


class PayeeMergeReason(enum.StrEnum):
    """Which part of the score carried a merge proposal the most."""

    NAME = "name"
    IDENTITY = "identity"
    MERCHANT_KEY = "merchant_key"


class PayeeMergeProposalResponse(BaseModel):
    """Two payees the merge scan thinks are one merchant.

    ``left_id`` is the payee that would be kept: the one with more
    transactions, the older one on a tie.
    """

    left_id: int
    left_name: str
    right_id: int
    right_name: str
    score: float = Field(..., ge=0, le=1)
    reason: PayeeMergeReason


class PayeeMergeDismiss(BaseModel):
    left_id: int
    right_id: int
