from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t
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


def register() -> None:
    @ui.page("/wizard")
    async def wizard_page() -> None:
        with page_layout(t("nav.wizard")):
            # Hero
            with ui.row().classes("w-full items-center gap-4"):
                ui.icon("auto_awesome", size="3rem").classes("text-primary")
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-3"):
                        ui.label(t("wizard.title")).classes("text-2xl font-bold")
                        ui.badge(t("wizard.coming_soon"), color="orange").classes("text-xs")
                    ui.label(t("wizard.subtitle")).classes("text-sm text-grey-6 max-w-2xl")

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
                        with ui.row().classes(f"items-center gap-3 px-4 py-3 bg-{color}"):
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
                                        ui.label(t(f"wizard.step_{step_key}_desc")).classes(
                                            "text-xs text-grey-6 leading-relaxed"
                                        )
                                        ui.badge(
                                            t("wizard.coming_soon"), color="grey-4"
                                        ).classes("text-xs w-fit mt-1").props("outline")

            # Footer note
            with ui.row().classes("items-center gap-2 text-grey-5 mt-2"):
                ui.icon("info_outline", size="1.1rem")
                ui.label(t("wizard.cta_note")).classes("text-xs")
