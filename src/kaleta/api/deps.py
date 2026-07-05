# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import math
from collections.abc import AsyncGenerator
from typing import NoReturn, TypeVar

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.auth.session import user_id_from_request
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import UnauthorizedError
from kaleta.services.api_token_service import ApiTokenService

T = TypeVar("T")

_bearer_scheme = HTTPBearer(auto_error=False)


# ── Database session ──────────────────────────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


def _unauthorized() -> NoReturn:
    raise UnauthorizedError("Authentication required")


async def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> int:
    """Resolve the authenticated user from a bearer token or UI session cookie."""
    if credentials is not None and credentials.scheme.lower() == "bearer":
        user_id = await ApiTokenService(session).authenticate_bearer(credentials.credentials)
        if user_id is not None:
            return user_id

    session_user_id = user_id_from_request(request)
    if session_user_id is not None:
        return session_user_id

    _unauthorized()


async def require_api_auth(user_id: int = Depends(get_current_user_id)) -> int:
    """Router-level dependency that enforces authentication on /api/v1/*."""
    return user_id


# ── Pagination ────────────────────────────────────────────────────────────────


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PagedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PaginationParams) -> PagedResponse[T]:
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=max(1, math.ceil(total / params.page_size)),
        )
