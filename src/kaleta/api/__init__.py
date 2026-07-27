# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi import APIRouter

from kaleta.api.v1 import v1_router
from kaleta.api.v1.health import router as health_router


def create_api_router() -> APIRouter:
    """Return the top-level /api router that includes all versioned sub-routers."""
    router = APIRouter(prefix="/api")
    # Health is public — mount outside the authenticated v1 router dependencies.
    public_v1 = APIRouter(prefix="/v1")
    public_v1.include_router(health_router)
    router.include_router(public_v1)
    router.include_router(v1_router)
    return router
