from fastapi import APIRouter

from kaleta.api.v1.accounts import router as accounts_router
from kaleta.api.v1.budgets import router as budgets_router
from kaleta.api.v1.categories import router as categories_router
from kaleta.api.v1.institutions import router as institutions_router
from kaleta.api.v1.transactions import router as transactions_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(accounts_router)
v1_router.include_router(institutions_router)
v1_router.include_router(categories_router)
v1_router.include_router(transactions_router)
v1_router.include_router(budgets_router)
