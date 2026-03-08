import uvicorn
from fastapi import FastAPI
from nicegui import ui

from kaleta.config import settings


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
    net_worth.register()
    credit_calculator.register()


def create_api() -> FastAPI:
    api = FastAPI(title="Kaleta API", version="0.1.0")
    return api


def run_web() -> None:
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
