# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi import APIRouter, Depends

from kaleta.api.deps import require_api_auth
from kaleta.api.v1.accounts import router as accounts_router
from kaleta.api.v1.budgets import router as budgets_router
from kaleta.api.v1.categories import router as categories_router
from kaleta.api.v1.import_rules import router as import_rules_router
from kaleta.api.v1.institutions import router as institutions_router
from kaleta.api.v1.net_worth import router as net_worth_router
from kaleta.api.v1.payees import router as payees_router
from kaleta.api.v1.personal_loans import router as personal_loans_router
from kaleta.api.v1.reports import router as reports_router
from kaleta.api.v1.reserve_funds import router as reserve_funds_router
from kaleta.api.v1.subscriptions import router as subscriptions_router
from kaleta.api.v1.transactions import router as transactions_router

v1_router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_auth)])
v1_router.include_router(accounts_router)
v1_router.include_router(institutions_router)
v1_router.include_router(categories_router)
v1_router.include_router(import_rules_router)
v1_router.include_router(transactions_router)
v1_router.include_router(budgets_router)
v1_router.include_router(payees_router)
v1_router.include_router(subscriptions_router)
v1_router.include_router(personal_loans_router)
v1_router.include_router(reserve_funds_router)
v1_router.include_router(net_worth_router)
v1_router.include_router(reports_router)
