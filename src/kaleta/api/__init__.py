from fastapi import APIRouter

from kaleta.api.v1 import v1_router


def create_api_router() -> APIRouter:
    """Return the top-level /api router that includes all versioned sub-routers."""
    router = APIRouter(prefix="/api")
    router.include_router(v1_router)
    return router
