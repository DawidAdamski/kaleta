# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/tags`` — the tags a transaction can carry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import NotFoundError
from kaleta.models.tag import Tag
from kaleta.schemas.tag import TagCreate, TagResponse, TagUpdate
from kaleta.services.tag_service import TagService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Tag not found"}}
_409: dict[int | str, dict[str, Any]] = {409: {"description": "Another tag has that name"}}
_422: dict[int | str, dict[str, Any]] = {422: {"description": "A blank or null name"}}

router = APIRouter(prefix="/tags", tags=["Tags"])


def _found(tag: Tag | None, tag_id: int) -> TagResponse:
    if tag is None:
        raise NotFoundError(f"Tag {tag_id} not found")
    return TagResponse.model_validate(tag)


@router.get("/", response_model=list[TagResponse], summary="List tags")
async def list_tags(session: AsyncSession = Depends(get_session)) -> list[TagResponse]:
    return [TagResponse.model_validate(tag) for tag in await TagService(session).list()]


@router.post(
    "/",
    response_model=TagResponse,
    status_code=201,
    summary="Create a tag",
    description="The name is stripped, must not be blank, and must not be another tag's.",
    responses={**_409, **_422},
)
async def create_tag(data: TagCreate, session: AsyncSession = Depends(get_session)) -> TagResponse:
    return TagResponse.model_validate(await TagService(session).create(data))


@router.get("/{tag_id}", response_model=TagResponse, summary="Get a tag", responses=_404)
async def get_tag(tag_id: int, session: AsyncSession = Depends(get_session)) -> TagResponse:
    return _found(await TagService(session).get(tag_id), tag_id)


@router.put(
    "/{tag_id}",
    response_model=TagResponse,
    summary="Update a tag",
    description="Partially updates the tag. `null` clears color, icon or description.",
    responses={**_404, **_409, **_422},
)
async def update_tag(
    tag_id: int, data: TagUpdate, session: AsyncSession = Depends(get_session)
) -> TagResponse:
    return _found(await TagService(session).update(tag_id, data), tag_id)


@router.delete(
    "/{tag_id}",
    status_code=204,
    summary="Delete a tag",
    description="Removes the tag from every transaction; the transactions stay.",
    responses=_404,
)
async def delete_tag(tag_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await TagService(session).delete(tag_id):
        raise NotFoundError(f"Tag {tag_id} not found")
