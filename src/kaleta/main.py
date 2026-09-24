# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

# Pin NiceGUI storage under ~/.kaleta/ before any import that may load nicegui
# (Storage.path is resolved at import time from NICEGUI_STORAGE_PATH).
import os
import sys
from pathlib import Path

_NICEGUI_STORAGE = (Path.home() / ".kaleta" / "nicegui").resolve()
_NICEGUI_STORAGE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(_NICEGUI_STORAGE))

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
from kaleta.api.v1.health import register_health_alias
from kaleta.auth.session import session_middleware_kwargs, warn_secure_cookie_in_debug
from kaleta.config import settings
from kaleta.logging_config import RequestContextMiddleware, configure_logging
from kaleta.services.backup_scheduler import BackupScheduler
from kaleta.services.nbp_startup import NbpStartupFetcher
from kaleta.services.nicegui_storage_service import NiceguiStorageService

# Cached OpenAPI spec — generated once from our router tree.
_openapi_spec: dict[str, Any] | None = None


def _api_spec() -> dict[str, Any]:
    global _openapi_spec
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


def _register_request_context() -> None:
    """Correlate every HTTP request; NiceGUI events use the UI resolver."""
    nicegui_app.add_middleware(RequestContextMiddleware)


def _register_error_tracker() -> None:
    """Optional Sentry-protocol forwarding (KALETA_ERROR_TRACKER_DSN)."""
    from kaleta.services.error_tracker import init_error_tracker

    init_error_tracker()


def _register_api() -> None:
    register_error_handlers(nicegui_app)
    nicegui_app.include_router(create_api_router())
    register_health_alias(nicegui_app)

    @nicegui_app.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
    async def _swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api-docs/openapi.json",
            title="Kaleta API",
        )

    @nicegui_app.get("/api-docs/openapi.json", include_in_schema=False)
    async def _openapi_json() -> dict[str, Any]:
        return _api_spec()


def _warn_repo_root_data_leftovers() -> None:
    """Log if the process CWD is a git checkout with leftover session/DB files."""
    import logging

    cwd = Path.cwd()
    if not (cwd / ".git").is_dir():
        return
    leftovers = [name for name in (".nicegui", "kaleta.db", "demo.db") if (cwd / name).exists()]
    if not leftovers:
        return
    logging.getLogger(__name__).warning(
        "Found %s in git working tree %s; prefer data under ~/.kaleta "
        "(NiceGUI sessions use ~/.kaleta/nicegui). Remove leftovers manually — "
        "they are not deleted automatically.",
        ", ".join(leftovers),
        cwd,
    )


async def _ensure_api_env_token_user() -> None:
    """When KALETA_API_TOKEN is set, ensure a real user exists for bearer auth."""
    import logging

    from kaleta.db import AsyncSessionFactory
    from kaleta.services.api_token_service import MIN_API_TOKEN_LENGTH
    from kaleta.services.auth_service import AuthService

    token = settings.api_token
    if not token or len(token) < MIN_API_TOKEN_LENGTH:
        return
    async with AsyncSessionFactory() as session:
        user = await AuthService(session).ensure_api_bootstrap_user()
    logging.getLogger(__name__).info(
        "API env-token bootstrap ready for user %r (id=%s)",
        user.username,
        user.id,
    )


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
        login_mfa,
        monthly_readiness,
        net_worth,
        payees,
        payment_calendar,
        personal_loans,
        planned_transactions,
        reports,
        reports_canned,
        rules,
        safety_funds,
        secure_app,
        settings,
        setup,
        subscriptions,
        tags,
        transactions,
        wizard,
        wizard_salary,
        wizard_scenarios,
        wizard_unplanned_radar,
    )

    setup.register()
    login.register()
    login_mfa.register()
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
    rules.register()
    wizard.register()
    wizard_salary.register()
    wizard_scenarios.register()
    wizard_unplanned_radar.register()
    settings.register()

    from kaleta.views.error_handling import install_session_resolver

    install_session_resolver()


def _sweep_nicegui_storage() -> None:
    NiceguiStorageService().sweep_stale()


def _register_event_retention_scheduler() -> None:
    from kaleta.services.event_retention_scheduler import EventRetentionScheduler

    nicegui_app.on_startup(EventRetentionScheduler.start)
    nicegui_app.on_shutdown(EventRetentionScheduler.stop)


def _register_backup_scheduler() -> None:
    """Start/stop scheduled SQLite file backups with the NiceGUI process."""
    nicegui_app.on_startup(BackupScheduler.start)
    nicegui_app.on_shutdown(BackupScheduler.stop)


def _register_nbp_startup_fetch() -> None:
    """Opt-in NBP Table A import on process start (default OFF)."""
    nicegui_app.on_startup(NbpStartupFetcher.start)
    nicegui_app.on_shutdown(NbpStartupFetcher.stop)


def _register_storage_sweep() -> None:
    nicegui_app.on_startup(_sweep_nicegui_storage)


@asynccontextmanager
async def _api_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _warn_repo_root_data_leftovers()
    _sweep_nicegui_storage()
    await _ensure_api_env_token_user()
    BackupScheduler.start()
    from kaleta.services.event_retention_scheduler import EventRetentionScheduler

    EventRetentionScheduler.start()
    NbpStartupFetcher.start()
    try:
        yield
    finally:
        await NbpStartupFetcher.stop()
        await EventRetentionScheduler.stop()
        await BackupScheduler.stop()


def create_api() -> FastAPI:
    api = FastAPI(title="Kaleta API", version="0.1.0", lifespan=_api_lifespan)
    register_error_handlers(api)
    register_health_alias(api)
    return api


def run_web() -> None:
    configure_logging()
    _register_error_tracker()
    _warn_repo_root_data_leftovers()
    # Before the views register the log ring buffer's NiceGUI session resolver:
    # a warning logged after that, but before ui.run(), trips NiceGUI's script mode.
    warn_secure_cookie_in_debug()
    _preload_config()
    _setup_pwa()
    _register_request_context()
    _register_api()
    _register_auth()
    _register_views()
    _register_backup_scheduler()
    _register_event_retention_scheduler()
    _register_nbp_startup_fetch()
    _register_storage_sweep()
    from kaleta.config.setup_config import is_configured

    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        reload=False,
        show=not is_configured(),
        storage_secret=settings.secret_key,
        session_middleware_kwargs=session_middleware_kwargs(),
    )


def run_app() -> None:
    configure_logging()
    _register_error_tracker()
    _warn_repo_root_data_leftovers()
    # Before the views register the log ring buffer's NiceGUI session resolver:
    # a warning logged after that, but before ui.run(), trips NiceGUI's script mode.
    warn_secure_cookie_in_debug()
    _preload_config()
    _setup_pwa()
    _register_request_context()
    _register_api()
    _register_auth()
    _register_views()
    _register_backup_scheduler()
    _register_event_retention_scheduler()
    _register_nbp_startup_fetch()
    _register_storage_sweep()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        native=True,
        reload=False,
        storage_secret=settings.secret_key,
        session_middleware_kwargs=session_middleware_kwargs(),
    )


def run_api() -> None:
    configure_logging()
    _register_error_tracker()
    _preload_config()
    api = create_api()
    api.add_middleware(RequestContextMiddleware, access_log=True)
    api.include_router(create_api_router())
    uvicorn.run(api, host=settings.host, port=settings.port)


def main() -> None:
    if "--reset-password" in sys.argv:
        from kaleta.cli.reset_password import ResetPasswordCli

        raise SystemExit(ResetPasswordCli(disable_mfa="--disable-mfa" in sys.argv).run())

    if "--disable-mfa" in sys.argv:
        # Said out loud rather than ignored. This is the escape hatch
        # SECURITY.md points a locked-out self-hoster at, and the person
        # typing it has already lost their phone — starting the app normally
        # and saying nothing is the worst possible answer.
        sys.stderr.write("--disable-mfa only works together with --reset-password.\n")
        raise SystemExit(2)

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
