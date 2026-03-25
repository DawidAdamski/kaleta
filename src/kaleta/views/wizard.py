from __future__ import annotations

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.institution_service import InstitutionService
from kaleta.views.layout import page_layout

# (icon, step_key, section)  — section groups them visually
_STEPS: list[tuple[str, str, str]] = [
    # Monthly readiness
    ("event_available", "next_month", "monthly"),
    ("search", "unplanned", "monthly"),
    # Safety & reserve funds
    ("local_fire_department", "emergency", "funds"),
    ("build_circle", "irregular", "funds"),
    ("beach_access", "vacation", "funds"),
    # Income planning
    ("payments", "salary", "income"),
    # Budget builder
    ("checklist", "budget_builder", "budget"),
    ("science", "scenarios", "budget"),
]

_SECTION_ICONS = {
    "monthly": "calendar_month",
    "funds": "savings",
    "income": "account_balance_wallet",
    "budget": "bar_chart",
}

_SECTION_COLORS = {
    "monthly": "blue-6",
    "funds": "green-7",
    "income": "orange-7",
    "budget": "purple-7",
}

# (icon, title_key, desc_key, url, done_hint_key)
_ONBOARDING: list[tuple[str, str, str, str, str]] = [
    (
        "account_balance",
        "wizard.setup_institution",
        "wizard.setup_institution_desc",
        "/institutions",
        "wizard.setup_institution_hint",
    ),
    (
        "account_balance_wallet",
        "wizard.setup_account",
        "wizard.setup_account_desc",
        "/accounts",
        "wizard.setup_account_hint",
    ),
    (
        "category",
        "wizard.setup_categories",
        "wizard.setup_categories_desc",
        "/categories",
        "wizard.setup_categories_hint",
    ),
    (
        "upload_file",
        "wizard.setup_import",
        "wizard.setup_import_desc",
        "/import",
        "wizard.setup_import_hint",
    ),
]


def register() -> None:
    @ui.page("/wizard")
    async def wizard_page() -> None:
        async with AsyncSessionFactory() as session:
            n_institutions = len(await InstitutionService(session).list())
            n_accounts = len(await AccountService(session).list())
            categories = await CategoryService(session).list()
            n_expense_cats = sum(1 for c in categories if c.type.value == "expense")
            n_income_cats = sum(1 for c in categories if c.type.value == "income")
            n_transactions = await TransactionService(session).count()

        done_flags = [
            n_institutions > 0,
            n_accounts > 0,
            (n_expense_cats > 0 and n_income_cats > 0),
            n_transactions > 0,
        ]
        done_counts = [
            t("wizard.setup_institution_count", count=n_institutions),
            t("wizard.setup_account_count", count=n_accounts),
            t("wizard.setup_categories_count",
              expense=n_expense_cats, income=n_income_cats),
            t("wizard.setup_import_count", count=n_transactions),
        ]

        all_done = all(done_flags)

        with page_layout(t("nav.wizard")):
            # Hero
            with ui.row().classes("w-full items-center gap-4"):
                ui.icon("auto_awesome", size="3rem").classes("text-primary")
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-3"):
                        ui.label(t("wizard.title")).classes("text-2xl font-bold")
                        ui.badge(t("wizard.coming_soon"), color="orange").classes(
                            "text-xs"
                        )
                    ui.label(t("wizard.subtitle")).classes(
                        "text-sm text-grey-6 max-w-2xl"
                    )

            # ── Onboarding section ────────────────────────────────────────────
            with ui.card().classes("w-full p-0 overflow-hidden"):
                # Header
                with ui.row().classes(
                    "items-center gap-3 px-5 py-4 bg-teal-7"
                ):
                    ui.icon("rocket_launch", size="1.4rem").classes("text-white")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(t("wizard.setup_title")).classes(
                            "text-white font-semibold text-base"
                        )
                        ui.label(t("wizard.setup_subtitle")).classes(
                            "text-teal-1 text-xs"
                        )
                    if all_done:
                        ui.badge(t("wizard.setup_all_done"), color="green").classes(
                            "text-xs"
                        )

                # Steps
                with ui.column().classes("gap-0 w-full"):
                    for i, (icon, title_key, desc_key, url, hint_key) in enumerate(
                        _ONBOARDING
                    ):
                        done = done_flags[i]
                        count_text = done_counts[i]
                        border = (
                            "" if i == len(_ONBOARDING) - 1 else "border-b"
                        )
                        bg = "bg-green-1" if done else ""

                        with ui.row().classes(
                            f"items-center gap-4 px-5 py-4 {border} {bg} w-full"
                        ):
                            # Step number / checkmark
                            with ui.element("div").classes(
                                "flex-shrink-0 w-8 h-8 rounded-full flex items-center"
                                " justify-center text-sm font-bold "
                                + ("bg-green-6 text-white" if done else "bg-grey-3 text-grey-6")
                            ):
                                if done:
                                    ui.icon("check", size="1.1rem").classes("text-white")
                                else:
                                    ui.label(str(i + 1)).classes("text-sm font-bold")

                            ui.icon(icon, size="1.5rem").classes(
                                "flex-shrink-0 "
                                + ("text-green-7" if done else "text-grey-5")
                            )

                            with ui.column().classes("gap-0.5 flex-1"):
                                ui.label(t(title_key)).classes(
                                    "font-medium text-sm "
                                    + ("text-green-8" if done else "")
                                )
                                ui.label(t(desc_key)).classes(
                                    "text-xs text-grey-6 leading-relaxed"
                                )
                                if done:
                                    ui.label(count_text).classes(
                                        "text-xs text-green-7 font-medium mt-0.5"
                                    )
                                else:
                                    ui.label(t(hint_key)).classes(
                                        "text-xs text-amber-7 mt-0.5"
                                    )

                            ui.button(
                                t("wizard.setup_go") if not done else t("wizard.setup_edit"),
                                icon="arrow_forward" if not done else "edit",
                                on_click=lambda u=url: ui.navigate.to(u),
                            ).props(
                                "color=primary unelevated size=sm"
                                if not done
                                else "color=grey-4 flat size=sm"
                            ).classes("flex-shrink-0")

            # ── Planning sections (coming soon) ───────────────────────────────
            # Group steps by section
            sections: dict[str, list[tuple[str, str]]] = {}
            for icon, step_key, section in _STEPS:
                sections.setdefault(section, []).append((icon, step_key))

            section_order = ["monthly", "funds", "income", "budget"]

            with ui.grid(columns=2).classes("w-full gap-4"):
                for section in section_order:
                    steps = sections.get(section, [])
                    color = _SECTION_COLORS[section]
                    sec_icon = _SECTION_ICONS[section]

                    with ui.card().classes("p-0 overflow-hidden"):
                        # Section header bar
                        with ui.row().classes(
                            f"items-center gap-3 px-4 py-3 bg-{color}"
                        ):
                            ui.icon(sec_icon, size="1.4rem").classes("text-white")
                            ui.label(t(f"wizard.section_{section}")).classes(
                                "text-white font-semibold text-sm uppercase tracking-wide"
                            )

                        with ui.column().classes("gap-0"):
                            for i, (step_icon, step_key) in enumerate(steps):
                                border = "" if i == len(steps) - 1 else "border-b"
                                with ui.row().classes(
                                    f"items-start gap-4 px-4 py-4 {border}"
                                ):
                                    ui.icon(step_icon, size="1.6rem").classes(
                                        f"text-{color} flex-shrink-0 mt-0.5"
                                    )
                                    with ui.column().classes("gap-1 flex-1"):
                                        ui.label(t(f"wizard.step_{step_key}")).classes(
                                            "font-medium text-sm"
                                        )
                                        ui.label(
                                            t(f"wizard.step_{step_key}_desc")
                                        ).classes("text-xs text-grey-6 leading-relaxed")
                                        ui.badge(
                                            t("wizard.coming_soon"), color="grey-4"
                                        ).classes("text-xs w-fit mt-1").props("outline")

            # Footer note
            with ui.row().classes("items-center gap-2 text-grey-5 mt-2"):
                ui.icon("info_outline", size="1.1rem")
                ui.label(t("wizard.cta_note")).classes("text-xs")
