# SPDX-License-Identifier: AGPL-3.0-or-later
"""Financial Wizard — the index of everything the app can walk you through.

Hero, then one mentor suggestion, then Setup as four done-cards, then the
routines as a single list ranked by what you can actually open today. The
page used to rank them by topic across six cards in six colours, which meant
the five working steps were scattered among eight that were not built yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.category import CategoryType
from kaleta.services import (
    AccountService,
    CategoryService,
    InstitutionService,
    TransactionService,
    with_session,
)
from kaleta.services.wizard_mentor_service import MentorSuggestion, WizardMentorService
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    ACCENT_RULE,
    ACCENT_TEXT,
    BODY_MUTED,
    HAIRLINE_BOTTOM,
    HAIRLINE_ROW,
    INK,
    MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
    SECTION_TITLE,
)

# (icon, step_key, section)  — section groups them visually
_STEPS: list[tuple[str, str, str]] = [
    # Monthly readiness
    ("event_available", "next_month", "monthly"),
    ("search", "unplanned", "monthly"),
    # Subscriptions
    ("autorenew", "sub_tracker", "subscriptions"),
    ("notifications_active", "sub_renewals", "subscriptions"),
    ("cancel", "sub_audit", "subscriptions"),
    ("trending_up", "sub_cost_trends", "subscriptions"),
    # Safety & reserve funds
    ("local_fire_department", "emergency", "funds"),
    ("build_circle", "irregular", "funds"),
    ("beach_access", "vacation", "funds"),
    # Income planning
    ("payments", "salary", "income"),
    # Budget builder
    ("checklist", "budget_builder", "budget"),
    ("science", "scenarios", "budget"),
    # Personal loans
    ("handshake", "personal_loans", "loans"),
]

# Steps that link out to a working page. Everything else is listed too, so the
# index says what the app will do — but plainly, and below what it does now.
_STEP_ROUTES: dict[str, str] = {
    "budget_builder": "/wizard/budget-builder",
    "emergency": "/wizard/safety-funds",
    "irregular": "/wizard/safety-funds",
    "vacation": "/wizard/safety-funds",
    "next_month": "/wizard/monthly-readiness",
    "sub_tracker": "/wizard/subscriptions",
    "sub_renewals": "/wizard/subscriptions",
    "sub_audit": "/wizard/subscriptions",
    "sub_cost_trends": "/wizard/subscriptions",
    "personal_loans": "/wizard/personal-loans",
    "salary": "/wizard/pay-yourself",
    "scenarios": "/wizard/scenarios",
    "unplanned": "/wizard/unplanned-radar",
}


@dataclass(frozen=True, slots=True)
class WizardStep:
    """One row of the routines index."""

    icon: str
    key: str
    section: str
    route: str | None

    @property
    def is_open(self) -> bool:
        """Whether there is a page behind it today."""
        return self.route is not None


def ordered_steps() -> list[WizardStep]:
    """Every routine, the ones you can open today first.

    The page used to group these by topic across six cards, which scattered
    the five working steps among eight that are not built yet — so the index
    read as a roadmap rather than as a list of things to do. Section order is
    kept inside each half, so a reader who knows where a step lives still
    finds it near the ones beside it.
    """
    steps = [
        WizardStep(icon=icon, key=key, section=section, route=_STEP_ROUTES.get(key))
        for icon, key, section in _STEPS
    ]
    return [s for s in steps if s.is_open] + [s for s in steps if not s.is_open]


@dataclass(frozen=True, slots=True)
class SetupStep:
    """One of the four things that must exist before the ledger adds up."""

    key: str
    icon: str
    title_key: str
    url: str
    hint_key: str


_ONBOARDING: list[SetupStep] = [
    SetupStep(
        key="institution",
        icon="account_balance",
        title_key="wizard.setup_institution",
        url="/institutions",
        hint_key="wizard.setup_institution_hint",
    ),
    SetupStep(
        key="account",
        icon="account_balance_wallet",
        title_key="wizard.setup_account",
        url="/accounts",
        hint_key="wizard.setup_account_hint",
    ),
    SetupStep(
        key="categories",
        icon="category",
        title_key="wizard.setup_categories",
        url="/categories",
        hint_key="wizard.setup_categories_hint",
    ),
    SetupStep(
        key="import",
        icon="upload_file",
        title_key="wizard.setup_import",
        url="/import",
        hint_key="wizard.setup_import_hint",
    ),
]


def register() -> None:
    @ui.page("/wizard")
    async def wizard_page() -> None:
        async def _load(session: Any) -> tuple[int, int, int, int, int, list[MentorSuggestion]]:
            n_institutions = len(await InstitutionService(session).list())
            n_accounts = len(await AccountService(session).list())
            categories = await CategoryService(session).list()
            n_expense_cats = sum(1 for c in categories if c.type == CategoryType.EXPENSE)
            n_income_cats = sum(1 for c in categories if c.type == CategoryType.INCOME)
            n_transactions = await TransactionService(session).count()
            mentor_suggestions = await WizardMentorService(session).suggestions()
            return (
                n_institutions,
                n_accounts,
                n_expense_cats,
                n_income_cats,
                n_transactions,
                mentor_suggestions,
            )

        (
            n_institutions,
            n_accounts,
            n_expense_cats,
            n_income_cats,
            n_transactions,
            mentor_suggestions,
        ) = await with_session(_load)

        done_flags = [
            n_institutions > 0,
            n_accounts > 0,
            (n_expense_cats > 0 and n_income_cats > 0),
            n_transactions > 0,
        ]
        done_counts = [
            t("wizard.setup_institution_count", count=n_institutions),
            t("wizard.setup_account_count", count=n_accounts),
            t("wizard.setup_categories_count", expense=n_expense_cats, income=n_income_cats),
            t("wizard.setup_import_count", count=n_transactions),
        ]

        all_done = all(done_flags)

        with page_layout(t("nav.wizard"), wide=True):
            # ── Hero ──────────────────────────────────────────────────────────
            with ui.row().classes("w-full items-center gap-4"):
                ui.icon("auto_awesome", size="2.2rem").classes(ACCENT_TEXT)
                with ui.column().classes("gap-1 min-w-0"):
                    ui.label(t("wizard.title")).classes(PAGE_TITLE)
                    ui.label(t("wizard.subtitle")).classes(f"{BODY_MUTED} max-w-2xl")

            # ── Mentor ────────────────────────────────────────────────────────
            # One suggestion, above everything else, because it is the only
            # thing on the page that knows what this particular ledger needs.
            if all_done:
                dismissed: set[str] = set(app.storage.user.get("wizard_mentor_dismissed", []))
                visible = [s for s in mentor_suggestions if s.key not in dismissed]

                with ui.card().classes(f"{SECTION_CARD} {ACCENT_RULE} gap-2"):
                    mentor_slot = ui.column().classes("w-full gap-2")

                def _dismiss(key: str) -> None:
                    dismissed.add(key)
                    app.storage.user["wizard_mentor_dismissed"] = list(dismissed)
                    visible[:] = [s for s in visible if s.key != key]
                    _render_mentor()

                def _render_mentor() -> None:
                    mentor_slot.clear()
                    with mentor_slot:
                        if not visible:
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("check_circle", size="1.1rem").classes("k-trend--pos")
                                ui.label(t("wizard.mentor_all_quiet")).classes(BODY_MUTED)
                            return

                        suggestion: MentorSuggestion = visible[0]
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("lightbulb", size="1rem").classes(ACCENT_TEXT)
                            ui.label(t("wizard.mentor_heading")).classes(SECTION_TITLE)
                        ui.label(t(suggestion.title_key, **suggestion.params)).classes(
                            SECTION_HEADING
                        )
                        ui.label(t(suggestion.body_key, **suggestion.params)).classes(
                            f"{BODY_MUTED} leading-relaxed max-w-3xl"
                        )
                        with ui.row().classes("gap-2 mt-1"):
                            ui.button(
                                t(suggestion.cta_key, **suggestion.params),
                                icon="arrow_forward",
                                on_click=lambda u=suggestion.cta_url: ui.navigate.to(u),
                            ).props("color=primary unelevated size=sm")
                            ui.button(
                                t("wizard.mentor_dismiss"),
                                icon="close",
                                on_click=lambda k=suggestion.key: _dismiss(k),
                            ).props("flat size=sm").tooltip(t("wizard.mentor_dismiss_tooltip"))

                _render_mentor()

            # ── Setup ─────────────────────────────────────────────────────────
            # Four done-cards. Collapsed by default once they are all ticked,
            # open by default while they are not; the user's own choice wins.
            onboarding_open: bool = app.storage.user.get("wizard_onboarding_open", not all_done)

            with ui.card().classes(f"{SECTION_CARD} gap-3"):
                with ui.row().classes(
                    "w-full items-center gap-3 cursor-pointer select-none"
                ) as onboarding_header:
                    ui.icon("rocket_launch", size="1.2rem").classes(MUTED)
                    with ui.column().classes("gap-0 flex-1 min-w-0"):
                        ui.label(t("wizard.setup_title")).classes(SECTION_HEADING)
                        ui.label(t("wizard.setup_subtitle")).classes(f"{MUTED} text-xs")
                    if all_done:
                        ui.label(t("wizard.setup_all_done")).classes(
                            "k-trend--pos text-xs font-medium"
                        )
                    chevron = ui.icon(
                        "keyboard_arrow_up" if onboarding_open else "keyboard_arrow_down",
                        size="1.4rem",
                    ).classes(MUTED)

                # No `columns=`: NiceGUI writes that as an inline
                # grid-template-columns, which an `md:` class can never beat.
                cards = ui.grid().classes("w-full grid-cols-2 md:grid-cols-4").style("gap:0.75rem")
                cards.set_visibility(onboarding_open)

                def _toggle_onboarding() -> None:
                    new_open = not app.storage.user.get("wizard_onboarding_open", not all_done)
                    app.storage.user["wizard_onboarding_open"] = new_open
                    cards.set_visibility(new_open)
                    chevron.props(
                        "name=" + ("keyboard_arrow_up" if new_open else "keyboard_arrow_down")
                    )

                onboarding_header.on("click", _toggle_onboarding)

                with cards:
                    for i, setup in enumerate(_ONBOARDING):
                        _render_setup_card(setup, done=done_flags[i], status=done_counts[i])

            # ── Routines index ────────────────────────────────────────────────
            with ui.card().classes(f"{SECTION_CARD} gap-3"):
                ui.label(t("wizard.routines_title")).classes(SECTION_HEADING)
                with (
                    ui.grid()
                    .classes("w-full grid-cols-1 md:grid-cols-2")
                    .style("row-gap:0;column-gap:1.5rem")
                ):
                    for step in ordered_steps():
                        _render_step_row(step)

            # Footer note
            with ui.row().classes("items-center gap-2 mt-2"):
                ui.icon("info_outline", size="1rem").classes(MUTED)
                ui.label(t("wizard.cta_note")).classes(f"{MUTED} text-xs")


def _render_setup_card(setup: SetupStep, *, done: bool, status: str) -> None:
    """One compact done-card: what it is, where it stands, and the way in.

    The way in stays on a finished card. A ticked step is the one a user is
    most likely to want to revisit — it is where their institutions and
    accounts are — and a card with nothing to click would be a dead end.
    """
    tone = INK if done else MUTED
    with ui.column().classes(
        f"{HAIRLINE_ROW} rounded-lg items-center text-center gap-1.5 p-3"
    ) as card:
        card.props["data-setup-step"] = setup.key
        with ui.row().classes("items-center gap-1.5"):
            ui.icon(setup.icon, size="1.3rem").classes(tone)
            if done:
                ui.icon("check_circle", size="1rem").classes("k-trend--pos")
        ui.label(t(setup.title_key)).classes(f"text-xs font-medium {tone} leading-tight")
        ui.label(status if done else t(setup.hint_key)).classes(
            f"{MUTED} text-[10.5px] leading-tight"
        )
        ui.button(
            t("wizard.setup_edit") if done else t("wizard.setup_go"),
            on_click=lambda u=setup.url: ui.navigate.to(u),
        ).props("size=sm dense " + ("flat color=grey-7" if done else "color=primary unelevated"))


def _render_step_row(step: WizardStep) -> None:
    """One routine: what it is, and either a way in or a note that there is none."""
    tone = INK if step.is_open else MUTED
    with ui.row().classes(f"{HAIRLINE_BOTTOM} w-full items-start gap-3 py-3 no-wrap") as row:
        row.props["data-step"] = step.key
        ui.icon(step.icon, size="1.3rem").classes(f"{tone} flex-none mt-0.5")
        with ui.column().classes("gap-0.5 flex-1 min-w-0"):
            ui.label(t(f"wizard.section_{step.section}")).classes(f"{SECTION_TITLE} text-[9px]")
            ui.label(t(f"wizard.step_{step.key}")).classes(f"text-sm font-medium {tone}")
            ui.label(t(f"wizard.step_{step.key}_desc")).classes(
                f"{MUTED} text-[11.5px] leading-relaxed"
            )
        if step.route is not None:
            # The arrow is a glyph, not a word — it does not want translating.
            ui.link(f"{t('wizard.open')} \u2192", step.route).classes(
                f"{ACCENT_TEXT} text-xs font-medium flex-none mt-0.5 no-underline"
            )
        else:
            ui.label(t("wizard.not_built")).classes(
                f"{SECTION_TITLE} text-[10.5px] flex-none mt-0.5"
            )
