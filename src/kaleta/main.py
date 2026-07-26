# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from nicegui import app as nicegui_app
from nicegui import ui

from kaleta.api import create_api_router
from kaleta.api.errors import register_error_handlers
from kaleta.config import settings
from kaleta.logging_config import RequestLoggingMiddleware, configure_logging
from kaleta.services.backup_scheduler import BackupScheduler

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
    register_error_handlers(nicegui_app)
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
    """Read ~/.kaleta/config.json and reconfigure the DB proxy before views are registered.

    When a database is already configured, also bring its schema to the installed
    alembic head (with a pre-migration VACUUM INTO safety copy for on-disk SQLite).
    """
    import logging

    from kaleta.config import settings as app_settings
    from kaleta.config.setup_config import get_db_url
    from kaleta.exceptions import MigrationError

    db_url = get_db_url()
    if db_url:
        from kaleta.db import configure_database
        from kaleta.services.setup_service import ensure_schema_current

        configure_database(db_url, debug=app_settings.debug)
        try:
            ensure_schema_current(db_url)
        except MigrationError as exc:
            logging.getLogger(__name__).error("Refusing to start: %s", exc.message)
            raise SystemExit(f"Refusing to start: {exc.message}") from exc


def _register_auth() -> None:
    from kaleta.auth import register_auth_middleware

    register_auth_middleware()


def _register_views() -> None:
    from kaleta.views import (
        accounts,
        budget_builder,
        budget_plan,
        budgets,
        categories,
        create_account,
        credit,
        credit_calculator,
        dashboard,
        forecast,
        housekeeping,
        import_view,
        institutions,
        login,
        monthly_readiness,
        net_worth,
        payees,
        payment_calendar,
        personal_loans,
        planned_transactions,
        reports,
        reports_canned,
        safety_funds,
        secure_app,
        settings,
        setup,
        subscriptions,
        tags,
        transactions,
        wizard,
    )

    setup.register()
    login.register()
    create_account.register()
    secure_app.register()
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
    subscriptions.register()
    personal_loans.register()
    monthly_readiness.register()
    net_worth.register()
    credit_calculator.register()
    credit.register()
    housekeeping.register()
    tags.register()
    wizard.register()
    settings.register()


def _register_backup_scheduler() -> None:
    """Start/stop scheduled SQLite file backups with the NiceGUI process."""
    nicegui_app.on_startup(BackupScheduler.start)
    nicegui_app.on_shutdown(BackupScheduler.stop)


@asynccontextmanager
async def _api_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    BackupScheduler.start()
    try:
        yield
    finally:
        await BackupScheduler.stop()


def create_api() -> FastAPI:
    api = FastAPI(title="Kaleta API", version="0.1.0", lifespan=_api_lifespan)
    register_error_handlers(api)
    return api


def run_web() -> None:
    configure_logging()
    _preload_config()
    _setup_pwa()
    _register_api()
    _register_auth()
    _register_views()
    _register_backup_scheduler()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        reload=False,
        show=False,
        storage_secret=settings.secret_key,
    )


def run_app() -> None:
    configure_logging()
    _preload_config()
    _setup_pwa()
    _register_api()
    _register_auth()
    _register_views()
    _register_backup_scheduler()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        native=True,
        reload=False,
        storage_secret=settings.secret_key,
    )


def run_api() -> None:
    configure_logging()
    _preload_config()
    api = create_api()
    api.add_middleware(RequestLoggingMiddleware)
    api.include_router(create_api_router())
    uvicorn.run(api, host=settings.host, port=settings.port)


def main() -> None:
    if "--reset-password" in sys.argv:
        from kaleta.cli.reset_password import ResetPasswordCli

        raise SystemExit(ResetPasswordCli().run())

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
