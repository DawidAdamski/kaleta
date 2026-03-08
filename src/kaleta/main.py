import uvicorn
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from nicegui import app as nicegui_app
from nicegui import ui

from kaleta.api import create_api_router
from kaleta.config import settings

# Cached OpenAPI spec — generated once from our router tree.
_openapi_spec: dict | None = None


def _api_spec() -> dict:
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


def _register_api() -> None:
    nicegui_app.include_router(create_api_router())

    @nicegui_app.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
    async def _swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api-docs/openapi.json",
            title="Kaleta API",
        )

    @nicegui_app.get("/api-docs/openapi.json", include_in_schema=False)
    async def _openapi_json() -> dict:
        return _api_spec()


def _register_views() -> None:
    from kaleta.views import (
        accounts,
        budget_plan,
        budgets,
        categories,
        credit_calculator,
        dashboard,
        forecast,
        import_view,
        institutions,
        net_worth,
        reports,
        settings,
        transactions,
    )

    dashboard.register()
    transactions.register()
    accounts.register()
    institutions.register()
    categories.register()
    budgets.register()
    budget_plan.register()
    import_view.register()
    forecast.register()
    reports.register()
    net_worth.register()
    credit_calculator.register()
    settings.register()


def create_api() -> FastAPI:
    api = FastAPI(title="Kaleta API", version="0.1.0")
    return api


def run_web() -> None:
    _register_api()
    _register_views()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Kaleta",
        reload=settings.debug,
        show=False,
        storage_secret=settings.secret_key,
    )


def run_app() -> None:
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
