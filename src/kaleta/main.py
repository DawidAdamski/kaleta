from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from nicegui import app as nicegui_app
from nicegui import ui

from kaleta.api import create_api_router
from kaleta.config import settings

# Cached OpenAPI spec — generated once from our router tree.
_openapi_spec: dict[str, Any] | None = None


def _api_spec() -> dict[str, Any]:
    global _openapi_spec  # noqa: PLW0603
    if _openapi_spec is None:
        tmp = FastAPI(
            title="Kaleta API",
            version="1.0.0",
            description="Public REST API for the Kaleta personal finance app.",
        )
        tmp.include_router(create_api_router())
        _openapi_spec = tmp.openapi()
    return _openapi_spec


def _setup_pwa() -> None:
    from kaleta.pwa import setup

    setup()


def _register_api() -> None:
    nicegui_app.include_router(create_api_router())

    @nicegui_app.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
    async def _swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api-docs/openapi.json",
            title="Kaleta API",
        )

    @nicegui_app.get("/api-docs/openapi.json", include_in_schema=False)
    async def _openapi_json() -> dict[str, Any]:
        return _api_spec()


def _preload_config() -> None:
    """Read ~/.kaleta/config.json and reconfigure the DB proxy before views are registered."""
    from kaleta.config import settings as app_settings
    from kaleta.config.setup_config import get_db_url

    db_url = get_db_url()
    if db_url:
        from kaleta.db import configure_database

        configure_database(db_url, debug=app_settings.debug)


def _register_views() -> None:
    from kaleta.views import (
        accounts,
        budget_builder,
        budget_plan,
        budgets,
        categories,
        credit_calculator,
        dashboard,
        forecast,
        import_view,
        institutions,
        monthly_readiness,
        net_worth,
        payees,
        payment_calendar,
        planned_transactions,
        reports,
        reports_canned,
        safety_funds,
        settings,
        setup,
        tags,
        transactions,
        wizard,
    )

    setup.register()
    dashboard.register()
    transactions.register()
    accounts.register()
    institutions.register()
    payees.register()
    categories.register()
    budgets.register()
    budget_plan.register()
    budget_builder.register()
    import_view.register()
    forecast.register()
    planned_transactions.register()
    payment_calendar.register()
    reports.register()
    reports_canned.register()
    safety_funds.register()
    monthly_readiness.register()
    net_worth.register()
    credit_calculator.register()
    tags.register()
    wizard.register()
    settings.register()


def create_api() -> FastAPI:
    api = FastAPI(title="Kaleta API", version="0.1.0")
    return api


def run_web() -> None:
    _preload_config()
    _setup_pwa()
    _register_api()
    _register_views()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        reload=False,
        show=False,
        storage_secret=settings.secret_key,
    )


def run_app() -> None:
    _preload_config()
    _setup_pwa()
    _register_api()
    _register_views()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        native=True,
        reload=False,
        storage_secret=settings.secret_key,
    )


def run_api() -> None:
    api = create_api()
    api.include_router(create_api_router())
    uvicorn.run(api, host=settings.host, port=settings.port)


def main() -> None:
    match settings.mode:
        case "web":
            run_web()
        case "app":
            run_app()
        case "api":
            run_api()
        case _:
            raise ValueError(f"Unknown KALETA_MODE: {settings.mode!r}. Use: web | app | api")


if __name__ in {"__main__", "__mp_main__"}:
    main()
