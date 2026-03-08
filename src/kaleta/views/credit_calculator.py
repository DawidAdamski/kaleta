from __future__ import annotations

import datetime

from nicegui import ui

from kaleta.views.layout import page_layout


def _next_month(d: datetime.date) -> datetime.date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 100 / 12
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def _amortization(
    principal: float,
    annual_rate: float,
    months: int,
    extra: float = 0.0,
    start: datetime.date | None = None,
) -> list[dict]:
    r = annual_rate / 100 / 12
    payment = _monthly_payment(principal, annual_rate, months)
    schedule: list[dict] = []
    balance = principal
    date = (start or datetime.date.today()).replace(day=1)

    for i in range(months):
        if balance < 0.005:
            break
        interest = balance * r
        principal_part = payment - interest
        if principal_part < 0:
            principal_part = 0.0
        # Last payment: don't overpay
        if principal_part >= balance:
            schedule.append(
                {
                    "month": i + 1,
                    "date": date.strftime("%b %Y"),
                    "payment": round(balance + interest, 2),
                    "principal": round(balance, 2),
                    "interest": round(interest, 2),
                    "extra": 0.0,
                    "balance": 0.0,
                }
            )
            break
        remaining = balance - principal_part
        extra_applied = min(extra, remaining)
        balance = remaining - extra_applied
        schedule.append(
            {
                "month": i + 1,
                "date": date.strftime("%b %Y"),
                "payment": round(payment, 2),
                "principal": round(principal_part, 2),
                "interest": round(interest, 2),
                "extra": round(extra_applied, 2),
                "balance": round(balance, 2),
            }
        )
        date = _next_month(date)

    return schedule


def _amortization_decreasing(
    principal: float,
    annual_rate: float,
    months: int,
    extra: float = 0.0,
    start: datetime.date | None = None,
) -> list[dict]:
    """Decreasing installments (raty malejące): fixed principal, falling total payment."""
    r = annual_rate / 100 / 12
    fixed_principal = principal / months
    schedule: list[dict] = []
    balance = principal
    date = (start or datetime.date.today()).replace(day=1)

    for i in range(months):
        if balance < 0.005:
            break
        interest = balance * r
        principal_part = min(fixed_principal, balance)
        remaining = balance - principal_part
        extra_applied = min(extra, remaining)
        balance = remaining - extra_applied
        schedule.append(
            {
                "month": i + 1,
                "date": date.strftime("%b %Y"),
                "payment": round(principal_part + interest, 2),
                "principal": round(principal_part, 2),
                "interest": round(interest, 2),
                "extra": round(extra_applied, 2),
                "balance": round(balance, 2),
            }
        )
        date = _next_month(date)

    return schedule


def _fmt(amount: float) -> str:
    return f"{amount:,.2f} PLN"


def register() -> None:
    @ui.page("/credit-calculator")
    async def credit_calculator_page() -> None:
        state: dict = {
            "principal": 300_000.0,
            "rate": 7.5,
            "months": 360,
            "extra": 0.0,
            "payment_type": "equal",
        }

        with page_layout("Credit Calculator"):
            ui.label("Credit Calculator").classes("text-2xl font-bold")

            with ui.row().classes("w-full gap-6 items-start flex-wrap"):

                # ── Form ─────────────────────────────────────────────────────
                with ui.card().classes("p-6 w-80 shrink-0"):
                    ui.label("Loan Parameters").classes("text-lg font-semibold mb-2")

                    type_in = ui.select(
                        {
                            "equal": "Equal installments (annuity)",
                            "decreasing": "Decreasing installments",
                        },
                        label="Payment Type",
                        value=state["payment_type"],
                    ).classes("w-full")

                    principal_in = ui.number(
                        "Loan Amount (PLN)",
                        value=state["principal"],
                        min=1000,
                        step=10_000,
                        format="%.0f",
                    ).classes("w-full")
                    rate_in = ui.number(
                        "Annual Interest Rate (%)",
                        value=state["rate"],
                        min=0.01,
                        max=50,
                        step=0.1,
                        format="%.2f",
                    ).classes("w-full")
                    months_in = ui.number(
                        "Term (months)",
                        value=state["months"],
                        min=1,
                        max=600,
                        step=12,
                        format="%.0f",
                    ).classes("w-full")

                    ui.separator().classes("my-3")
                    ui.label("Overpayment").classes("text-sm font-semibold text-grey-7")
                    extra_in = ui.number(
                        "Extra Monthly Payment (PLN)",
                        value=state["extra"],
                        min=0,
                        step=100,
                        format="%.0f",
                    ).classes("w-full")

                    def _calculate() -> None:
                        state["principal"] = float(principal_in.value or 0)
                        state["rate"] = float(rate_in.value or 0)
                        state["months"] = int(months_in.value or 1)
                        state["extra"] = float(extra_in.value or 0)
                        state["payment_type"] = type_in.value
                        results_ui.refresh()

                    ui.button("Calculate", icon="calculate", on_click=_calculate).props(
                        "color=primary"
                    ).classes("w-full mt-3")

                # ── Results ───────────────────────────────────────────────────
                with ui.column().classes("flex-1 min-w-0 gap-4"):

                    @ui.refreshable
                    def results_ui() -> None:
                        p = state["principal"]
                        r = state["rate"]
                        m = state["months"]
                        extra = state["extra"]

                        if p <= 0 or r <= 0 or m <= 0:
                            ui.label("Enter valid loan parameters.").classes("text-grey-5 mt-4")
                            return

                        decreasing = state["payment_type"] == "decreasing"
                        calc = _amortization_decreasing if decreasing else _amortization
                        schedule = calc(p, r, m)
                        schedule_extra = calc(p, r, m, extra=extra) if extra > 0 else []

                        monthly = _monthly_payment(p, r, m)
                        total_interest = sum(row["interest"] for row in schedule)
                        total_cost = sum(row["payment"] for row in schedule)

                        # ── Summary cards ─────────────────────────────────────
                        with ui.row().classes("w-full gap-4 flex-wrap"):
                            with ui.card().classes("flex-1 min-w-36 p-4"):
                                if decreasing:
                                    first_pay = schedule[0]["payment"] if schedule else 0.0
                                    last_pay = schedule[-1]["payment"] if schedule else 0.0
                                    ui.label("First → Last Payment").classes(
                                        "text-xs text-grey-6 uppercase tracking-wide"
                                    )
                                    ui.label(f"{_fmt(first_pay)} → {_fmt(last_pay)}").classes(
                                        "text-base font-bold text-primary mt-1"
                                    )
                                else:
                                    ui.label("Monthly Payment").classes(
                                        "text-xs text-grey-6 uppercase tracking-wide"
                                    )
                                    ui.label(_fmt(monthly)).classes(
                                        "text-xl font-bold text-primary mt-1"
                                    )

                            with ui.card().classes("flex-1 min-w-36 p-4"):
                                ui.label("Total Interest").classes(
                                    "text-xs text-grey-6 uppercase tracking-wide"
                                )
                                ui.label(_fmt(total_interest)).classes(
                                    "text-xl font-bold text-negative mt-1"
                                )

                            with ui.card().classes("flex-1 min-w-36 p-4"):
                                ui.label("Total Cost").classes(
                                    "text-xs text-grey-6 uppercase tracking-wide"
                                )
                                ui.label(_fmt(total_cost)).classes("text-xl font-bold mt-1")

                            with ui.card().classes("flex-1 min-w-36 p-4"):
                                ui.label("Loan Term").classes(
                                    "text-xs text-grey-6 uppercase tracking-wide"
                                )
                                actual_months = len(schedule)
                                years, rem = divmod(actual_months, 12)
                                term_str = f"{years}y {rem}m" if rem else f"{years}y"
                                ui.label(term_str).classes("text-xl font-bold mt-1")

                        # ── Overpayment savings card ───────────────────────────
                        if schedule_extra:
                            interest_extra = sum(row["interest"] for row in schedule_extra)
                            months_saved = len(schedule) - len(schedule_extra)
                            interest_saved = total_interest - interest_extra
                            years_s, rem_s = divmod(months_saved, 12)
                            saved_str = (
                                f"{years_s}y {rem_s}m earlier"
                                if years_s
                                else f"{months_saved} months earlier"
                            )
                            with ui.card().classes("w-full p-4 border-2 border-positive"), ui.row().classes("items-center gap-3"):  # noqa: E501
                                    ui.icon("savings", color="positive").classes("text-2xl")
                                    with ui.column().classes("gap-0"):
                                        ui.label("Overpayment Savings").classes(
                                            "text-sm font-semibold text-positive"
                                        )
                                        ui.label(
                                            f"Save {_fmt(interest_saved)} in interest · "
                                            f"finish {saved_str}"
                                        ).classes("text-sm text-grey-7")

                        # ── Balance chart ──────────────────────────────────────
                        with ui.card().classes("w-full"):
                            with ui.row().classes("items-center px-4 pt-3 pb-1"):
                                ui.icon("show_chart", color="primary").classes("text-xl")
                                ui.label("Remaining Balance").classes("text-sm font-semibold ml-2")

                            labels = [row["date"] for row in schedule]
                            # Show every Nth label to avoid crowding
                            tick_interval = max(len(labels) // 10, 1) - 1

                            series = [
                                {
                                    "name": "Standard",
                                    "type": "line",
                                    "data": [
                                        round(row["balance"] / 1000, 1) for row in schedule
                                    ],
                                    "smooth": True,
                                    "symbol": "none",
                                    "lineStyle": {"color": "#1976d2", "width": 2},
                                    "itemStyle": {"color": "#1976d2"},
                                    "areaStyle": {"color": "#1976d2", "opacity": 0.08},
                                }
                            ]

                            if schedule_extra:
                                # Pad shorter series with zeros to align x-axis
                                extra_balances = [
                                    round(row["balance"] / 1000, 1) for row in schedule_extra
                                ] + [0.0] * (len(schedule) - len(schedule_extra))
                                series.append(
                                    {
                                        "name": "With Overpayment",
                                        "type": "line",
                                        "data": extra_balances,
                                        "smooth": True,
                                        "symbol": "none",
                                        "lineStyle": {
                                            "color": "#2e7d32",
                                            "width": 2,
                                            "type": "dashed",
                                        },
                                        "itemStyle": {"color": "#2e7d32"},
                                        "areaStyle": {"color": "#2e7d32", "opacity": 0.06},
                                    }
                                )

                            legend_data = (
                                ["Standard", "With Overpayment"] if schedule_extra else ["Standard"]
                            )

                            ui.echart(
                                {
                                    "tooltip": {"trigger": "axis"},
                                    "legend": {"data": legend_data, "top": 0},
                                    "grid": {
                                        "left": "10%",
                                        "right": "4%",
                                        "top": "15%",
                                        "bottom": "18%",
                                    },
                                    "xAxis": {
                                        "type": "category",
                                        "data": labels,
                                        "axisLabel": {
                                            "rotate": 45,
                                            "fontSize": 10,
                                            "interval": tick_interval,
                                        },
                                    },
                                    "yAxis": {
                                        "type": "value",
                                        "name": "tys. PLN",
                                        "nameTextStyle": {"fontSize": 10},
                                        "axisLabel": {"formatter": "{value}k"},
                                    },
                                    "series": series,
                                }
                            ).classes("w-full h-72")

                        # ── Payment schedule table ─────────────────────────────
                        with ui.card().classes("w-full"):
                            with ui.row().classes("items-center px-4 pt-3 pb-1"):
                                ui.icon("table_rows", color="primary").classes("text-xl")
                                ui.label("Payment Schedule").classes("text-sm font-semibold ml-2")

                            cols = [
                                {"name": "month", "label": "#", "field": "month", "align": "right"},
                                {"name": "date", "label": "Date", "field": "date", "align": "left"},
                                {
                                    "name": "payment",
                                    "label": "Payment",
                                    "field": "payment",
                                    "align": "right",
                                },
                                {
                                    "name": "principal",
                                    "label": "Principal",
                                    "field": "principal",
                                    "align": "right",
                                },
                                {
                                    "name": "interest",
                                    "label": "Interest",
                                    "field": "interest",
                                    "align": "right",
                                },
                            ]
                            if extra > 0:
                                cols.append(
                                    {
                                        "name": "extra",
                                        "label": "Extra",
                                        "field": "extra",
                                        "align": "right",
                                    }
                                )
                            cols.append(
                                {
                                    "name": "balance",
                                    "label": "Balance",
                                    "field": "balance",
                                    "align": "right",
                                }
                            )

                            display_schedule = schedule_extra if schedule_extra else schedule
                            rows = [
                                {
                                    **row,
                                    "payment": _fmt(row["payment"]),
                                    "principal": _fmt(row["principal"]),
                                    "interest": _fmt(row["interest"]),
                                    "extra": _fmt(row["extra"]),
                                    "balance": _fmt(row["balance"]),
                                }
                                for row in display_schedule
                            ]

                            ui.table(
                                columns=cols,
                                rows=rows,
                                row_key="month",
                            ).classes("w-full").props("flat dense virtual-scroll").style(
                                "max-height: 420px"
                            )

                    results_ui()
