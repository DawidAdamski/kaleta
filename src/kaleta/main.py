# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

# Point NiceGUI at its storage before any import that may load nicegui
# (Storage.path and Storage.redis_url are read at import time from the env):
# files under ~/.kaleta/nicegui, or Redis when KALETA_REDIS_URL is set.
import sys
from pathlib import Path

from kaleta.config import settings
from kaleta.services.nicegui_storage_service import NiceguiStorageService

NiceguiStorageService.configure_environment(redis_url=settings.redis_url)

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import ui

from kaleta.api import create_api_router
from kaleta.api.docs import mount_api_docs
from kaleta.api.errors import register_error_handlers
from kaleta.api.v1.health import register_health_alias
from kaleta.auth.session import session_middleware_kwargs, warn_secure_cookie_in_debug
from kaleta.logging_config import RequestContextMiddleware, configure_logging


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
    # Swagger UI + OpenAPI JSON only when the flag allows it (F-2, KAL-SEC-002).
    mount_api_docs(nicegui_app)


def _warn_repo_root_data_leftovers() -> None:
    """Log if the process CWD is a git checkout with leftover NiceGUI session files."""
    import logging

    cwd = Path.cwd()
    if not (cwd / ".git").is_dir():
        return
    leftovers = [name for name in (".nicegui",) if (cwd / name).exists()]
    if not leftovers:
        return
    logging.getLogger(__name__).warning(
        "Found %s in git working tree %s; prefer data under ~/.kaleta "
        "(NiceGUI sessions use ~/.kaleta/nicegui). Remove leftovers manually — "
        "they are not deleted automatically.",
        ", ".join(leftovers),
        cwd,
    )


def _preload_database() -> None:
    """The registry first, then every family's schema, to head (ADR-35, ADR-38)."""
    import logging

    from kaleta.db import configure_database
    from kaleta.exceptions import MigrationError
    from kaleta.services.setup_service import ensure_multi_tenant_current

    configure_database(settings.db_url, debug=settings.debug)
    try:
        run = ensure_multi_tenant_current(settings.db_url)
    except MigrationError as exc:
        logging.getLogger(__name__).error("Refusing to start: %s", exc.message)
        raise SystemExit(f"Refusing to start: {exc.message}") from exc
    logging.getLogger(__name__).info(
        "Database ready (%d family schema(s) upgraded, %d suspended)",
        len(run.migrated),
        len(run.suspended),
    )


def _register_auth() -> None:
    from kaleta.auth import register_auth_middleware, register_session_routes

    register_auth_middleware()
    register_session_routes()


def _register_views() -> None:
    from kaleta.views import (
        accounts,
        admin,
        annual_review,
        budget_builder,
        budget_plan,
        budgets,
        categories,
        change_password,
        create_account,
        credit,
        credit_calculator,
        dashboard,
        forecast,
        gifts,
        housekeeping,
        import_view,
        institutions,
        irregular_fund,
        join,
        login,
        login_mfa,
        magic_link,
        monthly_readiness,
        net_worth,
        payees,
        payment_calendar,
        personal_loans,
        planned_transactions,
        reports,
        reports_canned,
        reset_password,
        rules,
        safety_funds,
        settings,
        subscriptions,
        tags,
        transactions,
        unlock,
        wizard,
        wizard_salary,
        wizard_scenarios,
        wizard_unplanned_radar,
    )

    login.register()
    login_mfa.register()
    unlock.register()
    magic_link.register()
    create_account.register()
    join.register()
    reset_password.register()
    change_password.register()
    admin.register()
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
    annual_review.register()
    irregular_fund.register()
    gifts.register()
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
    storage = NiceguiStorageService()
    storage.sweep_stale()
    storage.tighten_permissions()


def _register_event_retention_scheduler() -> None:
    from kaleta.services.event_retention_scheduler import EventRetentionScheduler

    # On the registry layout one sweep visits every family's schema.
    nicegui_app.on_startup(EventRetentionScheduler.start)
    nicegui_app.on_shutdown(EventRetentionScheduler.stop)


def _register_nbp_rate_scheduler() -> None:
    from kaleta.services.nbp_rate_scheduler import NbpRateScheduler

    # One fetch for the whole instance, into public.nbp_rates (KALETA_NBP_FETCH).
    nicegui_app.on_startup(NbpRateScheduler.start)
    nicegui_app.on_shutdown(NbpRateScheduler.stop)


def _register_storage_sweep() -> None:
    nicegui_app.on_startup(_sweep_nicegui_storage)


@asynccontextmanager
async def _api_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _warn_repo_root_data_leftovers()
    _sweep_nicegui_storage()
    from kaleta.services.event_retention_scheduler import EventRetentionScheduler
    from kaleta.services.nbp_rate_scheduler import NbpRateScheduler

    EventRetentionScheduler.start()
    NbpRateScheduler.start()
    try:
        yield
    finally:
        await NbpRateScheduler.stop()
        await EventRetentionScheduler.stop()


def create_api() -> FastAPI:
    from kaleta.observability import app_version

    api = FastAPI(title="Kaleta API", version=app_version(), lifespan=_api_lifespan)
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
    _preload_database()
    _setup_pwa()
    _register_request_context()
    _register_api()
    _register_auth()
    _register_views()
    _register_event_retention_scheduler()
    _register_nbp_rate_scheduler()
    _register_storage_sweep()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        reload=False,
        show=False,
        storage_secret=settings.secret_key,
        session_middleware_kwargs=session_middleware_kwargs(),
    )


def run_api() -> None:
    configure_logging()
    _register_error_tracker()
    _preload_database()
    api = create_api()
    api.add_middleware(RequestContextMiddleware, access_log=True)
    api.include_router(create_api_router())
    uvicorn.run(api, host=settings.host, port=settings.port)


def main() -> None:
    # Here rather than at import: importing this module (tests, tools) must not
    # change the umask of whoever imported it. Child processes inherit it.
    NiceguiStorageService.restrict_new_files()

    if "--reset-password" in sys.argv or "--disable-mfa" in sys.argv:
        # Said out loud rather than ignored: SECURITY.md once pointed a
        # locked-out self-hoster here, and starting the app instead would be
        # the worst possible answer.
        sys.stderr.write(
            "kaleta --reset-password is gone (ADR-38): logins live in the registry now.\n"
            "Run: kaleta-admin reset-password <e-mail> [--disable-mfa]\n"
        )
        raise SystemExit(2)

    match settings.mode:
        case "web":
            run_web()
        case "api":
            run_api()


if __name__ in {"__main__", "__mp_main__"}:
    main()
