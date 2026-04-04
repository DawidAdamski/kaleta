from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.models.category import CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from kaleta.services.category_service import CategoryService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Category not found"}}

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get(
    "/",
    response_model=list[CategoryResponse],
    summary="List categories",
    description=(
        "Returns all categories. Each category may contain nested `children` (subcategories). "
        "Use the `type` filter to return only `income` or `expense` categories."
    ),
)
async def list_categories(
    type: CategoryType | None = Query(None, description="Filter by category type"),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryResponse]:
    return await CategoryService(session).list(type=type)  # type: ignore[return-value]


@router.post(
    "/",
    response_model=CategoryResponse,
    status_code=201,
    summary="Create a category",
    description=(
        "Creates a new category. Set `parent_id` to nest it under an existing category. "
        "`type` must match the parent's type when `parent_id` is provided."
    ),
)
async def create_category(
    data: CategoryCreate,
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    return await CategoryService(session).create(data)  # type: ignore[return-value]


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get category by ID",
    responses=_404,
)
async def get_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    category = await CategoryService(session).get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category  # type: ignore[return-value]


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update a category",
    description=(
        "Partially updates a category. Only fields included in the request body are changed."
    ),
    responses=_404,
)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    svc = CategoryService(session)
    if not await svc.get(category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    updated = await svc.update(category_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{category_id}", status_code=204, summary="Delete a category", responses=_404)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = CategoryService(session)
    if not await svc.get(category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    await svc.delete(category_id)
