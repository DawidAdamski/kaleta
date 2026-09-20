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

from kaleta.i18n import plural_key, t
from kaleta.schemas.category import CategoryType
from kaleta.services import (
    AccountService,
    CategoryService,
    InstitutionService,
    TransactionService,
    with_session,
)
from kaleta.services.wizard_mentor_service import MentorSuggestion, WizardMentorService
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    ACCENT_RULE,
    ACCENT_TEXT,
    BUTTON_INK,
    BUTTON_OUTLINE,
    INK,
    INK_2,
    LINK_ACTION,
    MENTOR_EYEBROW,
    MUTED,
    PAGE_CONTAINER,
    PAGE_EYEBROW,
    PAGE_GAP_26,
    PAGE_ROOMY,
    PAGE_TITLE,
    ROUTINE_DESC,
    ROUTINE_ROW,
    SECTION_CARD_FEATURE,
    SECTION_RULE,
    SECTION_RULE_TITLE,
    SECTION_TITLE,
    SETUP_CARD,
    SETUP_TICK,
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
    #: What the way-in says once the step is ticked. "Edit" for the three
    #: that hold a list you go back to; the import is never finished.
    done_action_key: str = "wizard.setup_edit"


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
        done_action_key="wizard.setup_import_more",
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
        # Terse, the way artboard `3d` sets them: the tick already says the
        # step is done, so the line under it only has to say how much of it
        # there is.
        done_counts = [
            t(plural_key("wizard.setup_institution_count", n_institutions), count=n_institutions),
            t(plural_key("wizard.setup_account_count", n_accounts), count=n_accounts),
            t("wizard.setup_categories_count", expense=n_expense_cats, income=n_income_cats),
            t(
                plural_key("wizard.setup_import_count", n_transactions),
                count=spaced_thousands(f"{n_transactions:,}"),
            ),
        ]

        all_done = all(done_flags)

        with page_layout(
            t("nav.wizard"),
            wide=True,
            container=f"{PAGE_CONTAINER} {PAGE_ROOMY} {PAGE_GAP_26}",
        ):
            # ── Hero ──────────────────────────────────────────────────────────
            # No mark beside the title: the drawer already carries this page's
            # icon, and the accent on this screen belongs to the one
            # suggestion under the title.
            with ui.column().classes("gap-0 max-w-[640px]"):
                ui.label(_hero_eyebrow(all_done, mentor_suggestions)).classes(PAGE_EYEBROW).props(
                    "data-page-eyebrow"
                )
                ui.label(t("wizard.title")).classes(PAGE_TITLE)
                ui.label(t("wizard.subtitle")).classes(f"{INK_2} text-[13.5px] leading-[1.6] mt-3")

            # ── Mentor ────────────────────────────────────────────────────────
            # One suggestion, above everything else, because it is the only
            # thing on the page that knows what this particular ledger needs.
            if all_done:
                dismissed: set[str] = set(app.storage.user.get("wizard_mentor_dismissed", []))
                visible = [s for s in mentor_suggestions if s.key not in dismissed]

                with (
                    ui.card().classes(f"{SECTION_CARD_FEATURE} {ACCENT_RULE} gap-0"),
                    ui.row().classes("w-full items-start gap-5 no-wrap"),
                ):
                    ui.icon("lightbulb", size="26px").classes(f"{ACCENT_TEXT} mt-0.5 flex-none")
                    mentor_slot = ui.column().classes("flex-1 min-w-0 gap-0")

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
                                quiet = t("wizard.mentor_all_quiet")
                                ui.label(quiet).classes(f"{INK_2} text-[13px]")
                            return

                        suggestion: MentorSuggestion = visible[0]
                        ui.label(t("wizard.mentor_heading")).classes(MENTOR_EYEBROW)
                        ui.label(t(suggestion.title_key, **suggestion.params)).classes(
                            f"{INK} text-lg font-medium mt-1.5"
                        )
                        ui.label(t(suggestion.body_key, **suggestion.params)).classes(
                            f"{INK_2} text-[13px] leading-[1.6] max-w-[660px] mt-1.5"
                        )
                        with ui.row().classes("gap-2.5 mt-4"):
                            ui.button(
                                t(suggestion.cta_key, **suggestion.params),
                                icon="arrow_forward",
                                on_click=lambda u=suggestion.cta_url: ui.navigate.to(u),
                                color=None,
                            ).props("flat dense no-caps").classes(BUTTON_INK)
                            ui.button(
                                t("wizard.mentor_dismiss"),
                                on_click=lambda k=suggestion.key: _dismiss(k),
                                color=None,
                            ).props("flat dense no-caps").classes(BUTTON_OUTLINE).tooltip(
                                t("wizard.mentor_dismiss_tooltip")
                            )

                _render_mentor()

            # ── Setup ─────────────────────────────────────────────────────────
            # Four done-cards. Collapsed by default once they are all ticked,
            # open by default while they are not; the user's own choice wins.
            onboarding_open: bool = app.storage.user.get("wizard_onboarding_open", not all_done)

            # Neither section is a card: artboard `3d` heads each with an
            # eyebrow over one rule and puts what follows on the ground, so
            # the one card on the page is the suggestion above them.
            with ui.column().classes("w-full gap-0"):
                with ui.row().classes(
                    f"{SECTION_RULE} cursor-pointer select-none"
                ) as onboarding_header:
                    onboarding_header.props["data-section"] = "setup"
                    ui.label(t("wizard.setup_title")).classes(SECTION_RULE_TITLE)
                    ui.label(
                        t("wizard.setup_all_done") if all_done else t("wizard.setup_subtitle")
                    ).classes(f"{MUTED} text-xs")
                    ui.space()
                    chevron = ui.icon(
                        "keyboard_arrow_up" if onboarding_open else "keyboard_arrow_down",
                        size="20px",
                    ).classes(INK_2)

                # No `columns=`: NiceGUI writes that as an inline
                # grid-template-columns, which an `md:` class can never beat.
                cards = (
                    ui.grid().classes("w-full grid-cols-2 md:grid-cols-4 mt-4").style("gap:16px")
                )
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
            steps = ordered_steps()
            with ui.column().classes("w-full gap-0"):
                with ui.row().classes(SECTION_RULE):
                    ui.label(t("wizard.routines_title")).classes(SECTION_RULE_TITLE)
                    ui.label(
                        t(
                            "wizard.routines_count",
                            ready=sum(1 for s in steps if s.route is not None),
                            planned=sum(1 for s in steps if s.route is None),
                        )
                    ).classes(f"{MUTED} text-xs")
                with (
                    ui.grid()
                    .classes("w-full grid-cols-1 md:grid-cols-2")
                    .style("row-gap:0;column-gap:44px")
                ):
                    for step in steps:
                        _render_step_row(step)

            # The footnote explains the "Not built" label, so it belongs on
            # the page only while there is one to explain.
            if any(s.route is None for s in steps):
                with ui.row().classes("items-center gap-2 mt-2"):
                    ui.icon("info_outline", size="1rem").classes(MUTED)
                    ui.label(t("wizard.cta_note")).classes(f"{MUTED} text-xs")


def _hero_eyebrow(all_done: bool, suggestions: list[MentorSuggestion]) -> str:
    """ "Setup complete · 1 suggestion waiting" — artboard `3d`'s title line.

    Two facts, in the order the page answers them: whether the ledger is set
    up at all, and whether anything is asking for a decision today.
    """
    left = t("wizard.hero_eyebrow_done" if all_done else "wizard.hero_eyebrow_setup")
    if not all_done or not suggestions:
        right = t("wizard.hero_eyebrow_quiet")
    else:
        right = t(
            plural_key("wizard.hero_eyebrow_suggestions", len(suggestions)),
            count=len(suggestions),
        )
    return f"{left} · {right}"


def _render_setup_card(setup: SetupStep, *, done: bool, status: str) -> None:
    """One compact done-card: what it is, where it stands, and the way in.

    The way in stays on a finished card. A ticked step is the one a user is
    most likely to want to revisit — it is where their institutions and
    accounts are — and a card with nothing to click would be a dead end.
    """
    with ui.column().classes(f"{SETUP_CARD} gap-0") as card:
        card.props["data-setup-step"] = setup.key
        with ui.row().classes("items-center gap-[9px] no-wrap"):
            # A tick, not the step's own icon: on a done card the only thing
            # worth a mark is that it is done, and four different glyphs in a
            # row of four cards read as four unrelated things.
            with ui.element("span").classes(
                SETUP_TICK if done else f"{SETUP_TICK} k-setup-tick--todo"
            ):
                ui.icon("check" if done else setup.icon)
            ui.label(t(setup.title_key)).classes(f"{INK} text-[13.5px] font-medium truncate")
        ui.label(status if done else t(setup.hint_key)).classes(f"{MUTED} text-xs mt-2")
        ui.button(
            t(setup.done_action_key) if done else t("wizard.setup_go"),
            on_click=lambda u=setup.url: ui.navigate.to(u),
            color=None,
        ).props("flat dense no-caps").classes(f"{LINK_ACTION} mt-2.5 self-start")


def _render_step_row(step: WizardStep) -> None:
    """One routine: what it is, and either a way in or a note that there is none."""
    tone = INK if step.is_open else MUTED
    desc = t(f"wizard.step_{step.key}_desc")
    with ui.row().classes(f"{ROUTINE_ROW} w-full no-wrap") as row:
        row.props["data-step"] = step.key
        ui.icon(step.icon, size="20px").classes(f"{INK_2 if step.is_open else MUTED} flex-none")
        with ui.column().classes("gap-0 flex-1 min-w-0"):
            ui.label(t(f"wizard.step_{step.key}")).classes(f"text-sm font-medium {tone}")
            ui.label(desc).classes(ROUTINE_DESC)
        # The section and the full description are on the row rather than in
        # it: artboard `3d` reads the index as one list, and a two-line
        # paragraph on every row makes thirteen rows a page you must read.
        row.tooltip(f"{t(f'wizard.section_{step.section}')} — {desc}")
        if step.route is not None:
            ui.link(t("wizard.open"), step.route).classes(
                f"{ACCENT_TEXT} text-xs font-medium flex-none no-underline"
            )
        else:
            ui.label(t("wizard.not_built")).classes(f"{SECTION_TITLE} text-[10.5px] flex-none")
