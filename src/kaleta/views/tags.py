from __future__ import annotations

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.tag import Tag
from kaleta.schemas.tag import TagCreate, TagUpdate
from kaleta.services import TagService
from kaleta.views.layout import page_layout

_DEFAULT_COLOR = "#42A5F5"
_DEFAULT_ICON = "label"

_COMMON_ICONS = [
    # General / labels
    "label", "tag", "bookmark", "bookmark_border", "star", "star_border",
    "favorite", "favorite_border", "thumb_up", "check_circle", "flag",
    "new_releases", "priority_high", "info", "warning", "error", "help",
    # Home & lifestyle
    "home", "house", "apartment", "cottage", "cabin", "bed",
    "kitchen", "bathroom", "garage", "yard", "local_florist", "park",
    # Work & productivity
    "work", "business_center", "computer", "laptop", "phone", "devices",
    "schedule", "event", "calendar_today", "alarm", "task_alt", "description",
    "folder", "archive", "note", "category", "inbox", "send",
    # Finance
    "account_balance", "account_balance_wallet", "credit_card", "savings",
    "payments", "money", "attach_money", "euro", "paid", "sell",
    "trending_up", "trending_down", "bar_chart", "pie_chart", "show_chart",
    "receipt", "receipt_long", "request_quote", "price_check",
    # Shopping
    "shopping_cart", "shopping_bag", "local_grocery_store", "store",
    "local_mall", "redeem", "loyalty", "discount", "local_offer",
    # Food & drink
    "restaurant", "local_cafe", "local_bar", "fastfood", "bakery_dining",
    "lunch_dining", "dinner_dining", "local_pizza", "ramen_dining", "icecream",
    # Transport
    "directions_car", "local_gas_station", "ev_station", "local_taxi",
    "directions_bus", "train", "flight", "local_shipping", "two_wheeler",
    # Health
    "medical_services", "health_and_safety", "medication", "spa",
    "fitness_center", "sports_gymnastics", "self_improvement", "monitor_heart",
    # Education & learning
    "school", "menu_book", "import_contacts", "science", "psychology",
    "lightbulb", "emoji_objects", "auto_stories",
    # Entertainment
    "movie", "music_note", "headphones", "sports_esports", "sports_soccer",
    "sports_basketball", "sports_tennis", "casino", "celebration",
    # Travel
    "hotel", "beach_access", "luggage", "explore", "map", "location_on",
    "travel_explore", "hiking", "surfing",
    # Family & social
    "person", "group", "family_restroom", "child_care", "elderly", "pets",
    # Utilities
    "build", "handyman", "construction", "plumbing", "electrical_services",
    "water_drop", "eco", "energy_savings_leaf", "recycling",
]


def register() -> None:
    @ui.page("/tags")
    async def tags_page() -> None:
        # ── Icon picker dialog ─────────────────────────────────────────────────
        icon_picker_dialog = ui.dialog()

        # ── Add / Edit dialog ─────────────────────────────────────────────────
        dialog_tag_id: dict = {"value": None}
        icon_state: dict = {"name": _DEFAULT_ICON, "color": _DEFAULT_COLOR}

        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[520px] gap-3"):
            dialog_title = ui.label("").classes("text-lg font-bold")

            name_input = ui.input(t("tags.name")).classes("w-full")

            with ui.row().classes("w-full items-center gap-2"):
                icon_input = ui.input(
                    t("tags.icon_name"), value=_DEFAULT_ICON
                ).classes("flex-1")
                ui.button(
                    icon="grid_view",
                    on_click=icon_picker_dialog.open,
                ).props("flat round dense color=primary").tooltip(t("tags.pick_icon"))

            @ui.refreshable
            def icon_preview_ui() -> None:
                with ui.row().classes("items-center gap-3 py-1"):
                    ui.icon(icon_state["name"], size="2rem").style(
                        f"color: {icon_state['color']}"
                    )
                    ui.label(t("tags.preview")).classes("text-sm text-grey-6")

            icon_preview_ui()

            color_input = ui.color_input(t("tags.color"), value=_DEFAULT_COLOR).classes("w-full")

            desc_input = ui.textarea(
                t("tags.description"), placeholder=t("tags.description_hint")
            ).classes("w-full").props("rows=2 autogrow")

            def _on_icon_change(e: object) -> None:
                raw = (getattr(e, "value", None) or "").strip()
                icon_state["name"] = raw or _DEFAULT_ICON
                icon_preview_ui.refresh()

            def _on_color_change(e: object) -> None:
                raw = (getattr(e, "value", None) or "").strip()
                icon_state["color"] = (raw[:7] if raw.startswith("#") else raw) or _DEFAULT_COLOR
                icon_preview_ui.refresh()

            icon_input.on_value_change(_on_icon_change)
            color_input.on_value_change(_on_color_change)

            async def _submit() -> None:
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify(t("tags.name_required"), type="negative")
                    return
                raw_color = (color_input.value or "").strip()
                color_val = (raw_color[:7] if raw_color.startswith("#") else raw_color) or None
                payload = TagCreate(
                    name=name,
                    color=color_val,
                    icon=(icon_input.value or "").strip() or None,
                    description=(desc_input.value or "").strip() or None,
                )
                async with AsyncSessionFactory() as session:
                    svc = TagService(session)
                    if dialog_tag_id["value"] is None:
                        await svc.create(payload)
                        ui.notify(t("tags.created"), type="positive")
                    else:
                        await svc.update(dialog_tag_id["value"], TagUpdate(**payload.model_dump()))
                        ui.notify(t("tags.updated"), type="positive")
                dialog.close()
                tags_grid.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=_submit).props("color=primary")
            ui.keyboard(on_key=lambda e: (
                _submit() if e.key == "Enter" and e.action.keydown else
                dialog.close() if e.key == "Escape" and e.action.keydown else None
            ))

        # ── Icon picker dialog content ─────────────────────────────────────────
        icon_search_state: dict = {"query": ""}

        with icon_picker_dialog, ui.card().classes("w-[600px] gap-3"):
            ui.label(t("tags.pick_icon")).classes("text-base font-bold")

            icon_search_input = ui.input(
                t("tags.search_icon"), placeholder="filter…"
            ).classes("w-full").props("clearable dense")

            @ui.refreshable
            def icon_grid_ui() -> None:
                query = icon_search_state["query"].lower()
                filtered = [ic for ic in _COMMON_ICONS if not query or query in ic]
                with ui.element("div").style(
                    "display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));"
                    "gap:4px;max-height:340px;overflow-y:auto;padding:4px"
                ):
                    for ic in filtered:
                        ui.button(icon=ic, on_click=lambda i=ic: _pick_icon(i)).props(
                            "flat round dense"
                        ).tooltip(ic).style("font-size:1.4rem;width:48px;height:48px")

            icon_grid_ui()

            def _on_search_change(e: object) -> None:
                icon_search_state["query"] = (getattr(e, "value", None) or "").strip()
                icon_grid_ui.refresh()

            icon_search_input.on_value_change(_on_search_change)

            with ui.row().classes("w-full justify-end mt-1"):
                ui.button(t("common.close"), on_click=icon_picker_dialog.close).props("flat")

        def _pick_icon(name: str) -> None:
            icon_input.set_value(name)
            icon_state["name"] = name
            icon_preview_ui.refresh()
            icon_picker_dialog.close()

        # ── Delete dialog ─────────────────────────────────────────────────────
        delete_id: dict = {"value": None}
        delete_dialog = ui.dialog()
        with delete_dialog, ui.card().classes("w-[360px]"):
            delete_label = ui.label("").classes("text-base")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")

                async def _do_delete() -> None:
                    if delete_id["value"] is not None:
                        async with AsyncSessionFactory() as session:
                            await TagService(session).delete(delete_id["value"])
                    ui.notify(t("tags.deleted"), type="positive")
                    delete_dialog.close()
                    tags_grid.refresh()

                ui.button(
                    t("common.delete"), icon="delete", on_click=_do_delete
                ).props("color=negative")

        # ── Helpers ───────────────────────────────────────────────────────────
        def _open_add() -> None:
            dialog_tag_id["value"] = None
            icon_state["name"] = _DEFAULT_ICON
            icon_state["color"] = _DEFAULT_COLOR
            dialog_title.set_text(t("tags.add"))
            name_input.set_value("")
            color_input.set_value(_DEFAULT_COLOR)
            icon_input.set_value(_DEFAULT_ICON)
            desc_input.set_value("")
            icon_preview_ui.refresh()
            dialog.open()

        def _open_edit(tag: Tag) -> None:
            dialog_tag_id["value"] = tag.id
            icon_state["name"] = tag.icon or _DEFAULT_ICON
            icon_state["color"] = tag.color or _DEFAULT_COLOR
            dialog_title.set_text(t("tags.edit"))
            name_input.set_value(tag.name)
            color_input.set_value(tag.color or _DEFAULT_COLOR)
            icon_input.set_value(tag.icon or _DEFAULT_ICON)
            desc_input.set_value(tag.description or "")
            icon_preview_ui.refresh()
            dialog.open()

        def _open_delete(tag: Tag) -> None:
            delete_id["value"] = tag.id
            delete_label.set_text(t("tags.delete_confirm", name=tag.name))
            delete_dialog.open()

        # ── Tags grid ─────────────────────────────────────────────────────────
        @ui.refreshable
        async def tags_grid() -> None:
            async with AsyncSessionFactory() as session:
                all_tags = await TagService(session).list()

            if not all_tags:
                with ui.column().classes("w-full items-center py-20 gap-3 text-grey-5"):
                    ui.icon("label_off", size="4rem")
                    ui.label(t("tags.no_tags")).classes("text-lg")
                    ui.label(t("tags.no_tags_hint")).classes("text-sm")
                return

            with ui.grid(columns="repeat(auto-fill, minmax(280px, 1fr))").classes("w-full gap-4"):
                for tag in all_tags:
                    color = tag.color or "#9E9E9E"
                    icon_name = tag.icon or "label"
                    with ui.card().classes("p-0 overflow-hidden"):
                        ui.element("div").style(f"height:4px;background:{color};width:100%")
                        with ui.column().classes("p-4 gap-2"):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon(icon_name, size="1.6rem").style(f"color: {color}")
                                ui.label(tag.name).classes("text-base font-bold flex-1")
                            if tag.description:
                                ui.label(tag.description).classes(
                                    "text-sm text-grey-6 leading-snug"
                                )
                            with ui.row().classes("items-center gap-2 mt-1"):
                                ui.element("div").style(
                                    f"width:12px;height:12px;border-radius:50%;"
                                    f"background:{color};flex-shrink:0"
                                )
                                ui.label(color).classes("text-xs text-grey-5 font-mono flex-1")
                                ui.button(
                                    icon="edit",
                                    on_click=lambda tg=tag: _open_edit(tg),
                                ).props("flat round dense size=sm color=primary")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda tg=tag: _open_delete(tg),
                                ).props("flat round dense size=sm color=negative")

        # ── Page ──────────────────────────────────────────────────────────────
        with page_layout(t("tags.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("tags.title")).classes("text-2xl font-bold")
                ui.button(t("tags.add"), icon="add", on_click=_open_add).props("color=primary")

            await tags_grid()
