# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the sand theme in kaleta.views.theme.

The stylesheet is a plain string, so these are pure assertions over its
content. Every hex literal below is quoted from the "Design tokens" tables
in ``docs/design/restyle/README.md`` — the handoff is the source of truth,
never the module under test.
"""

from __future__ import annotations

import re

from kaleta.views import theme

# Light mode, README "Design tokens" → Light mode.
LIGHT_TOKENS = {
    "--k-ground": "#F3EFE7",
    "--k-surface": "#FCFAF6",
    "--k-surface-sunken": "#F3EFE7",
    "--k-surface-warm": "#F6F1E7",
    "--k-ink": "#1C1A15",
    "--k-ink-2": "#4A443A",
    "--k-muted": "#6B6353",
    "--k-muted-strong": "#6E6656",
    "--k-disabled": "#B5AB96",
    "--k-hairline": "#EDE7DA",
    "--k-border": "#E2DBCC",
    "--k-border-strong": "#C9BFA8",
    "--k-accent": "#B4591F",
    "--k-accent-text": "#9A4E1F",
    "--k-accent-light": "#DE7B45",
    "--k-income": "#36684D",
    "--k-expense": "#A44631",
    "--k-warning": "#8A5A12",
    "--k-neutral-bar": "#8E8676",
}

# Dark mode, README "Design tokens" → Dark mode.
DARK_TOKENS = {
    "--k-ground": "#171613",
    "--k-surface": "#201F1A",
    "--k-surface-sunken": "#2A2822",
    "--k-ink": "#F0EBDF",
    "--k-ink-2": "#CFC7B6",
    "--k-muted": "#A8A08D",
    "--k-muted-strong": "#A19781",
    "--k-hairline": "#2A2822",
    "--k-border": "#322F27",
    "--k-accent": "#E8935B",
    "--k-income": "#6FAF87",
    "--k-expense": "#DE8672",
    "--k-warning": "#E3B457",
}

# README step 1.2 — the Quasar brand block.
QUASAR_LIGHT = {
    "--q-primary": "#B4591F",
    "--q-secondary": "#6B6353",
    "--q-accent": "#DE7B45",
    "--q-positive": "#36684D",
    "--q-negative": "#A44631",
    "--q-info": "#9A4E1F",
    "--q-warning": "#8A5A12",
}


def _block(css: str, selector: str) -> str:
    """Return the declarations of the first ``selector { … }`` rule in ``css``."""
    start = css.index(selector + "{")
    return css[start : css.index("}", start)]


def _root() -> str:
    return _block(theme.BASE_CSS, ":root")


def _dark_root() -> str:
    return _block(theme.BASE_CSS, ".body--dark")


# ── design tokens ─────────────────────────────────────────────────────────────


def test_light_tokens_match_the_handoff() -> None:
    root = _root()
    for token, value in LIGHT_TOKENS.items():
        assert f"{token}:{value}" in root, token


def test_dark_tokens_match_the_handoff() -> None:
    dark = _dark_root()
    for token, value in DARK_TOKENS.items():
        assert f"{token}:{value}" in dark, token


def test_quasar_brand_variables_are_the_sand_palette() -> None:
    root = _root()
    for token, value in QUASAR_LIGHT.items():
        assert f"{token}:{value}" in root, token


def test_runtime_brand_matches_the_css_fallback() -> None:
    # NiceGUI writes its own brand onto <body>, which outranks :root, so the
    # values pushed by apply_brand() must agree with the stylesheet.
    for token, value in QUASAR_LIGHT.items():
        assert theme.QUASAR_BRAND[token.removeprefix("--q-")] == value, token


def test_runtime_brand_sets_the_dark_page_colours() -> None:
    assert theme.QUASAR_BRAND["dark_page"] == "#171613"
    assert theme.QUASAR_BRAND["dark"] == "#201F1A"


def test_dark_mode_overrides_only_the_two_brand_variables() -> None:
    dark = _dark_root()
    assert "--q-primary:#E8935B" in dark
    assert "--q-info:#E8935B" in dark


def test_every_dark_token_is_also_declared_light() -> None:
    # A token defined only in dark mode would fall back to nothing in light.
    declared = set(re.findall(r"(--k-[a-z0-9-]+):", _dark_root()))
    light = set(re.findall(r"(--k-[a-z0-9-]+):", _root()))
    assert declared <= light


def test_no_teal_or_navy_survives() -> None:
    css = theme.theme_css()
    for retired in ("#0d9488", "#14b8a6", "rgb(10,14,23)", "rgb(21,25,34)"):
        assert retired not in css, retired


# ── typography ────────────────────────────────────────────────────────────────


def test_body_stack_is_libre_franklin() -> None:
    assert "font-family:'Libre Franklin',ui-sans-serif,system-ui,sans-serif" in theme.BASE_CSS


def test_inter_font_feature_settings_are_gone() -> None:
    assert "font-feature-settings" not in theme.BASE_CSS


def test_self_hosted_font_files_are_referenced() -> None:
    for url in (
        "/static/fonts/libre-franklin-var.woff2",
        "/static/fonts/ibm-plex-mono-400.woff2",
        "/static/fonts/ibm-plex-mono-500.woff2",
    ):
        assert url in theme.BASE_CSS, url


def test_amounts_are_mono_with_tabular_figures() -> None:
    block = _block(theme.BASE_CSS, ".k-mono,.k-amount")
    assert "'IBM Plex Mono'" in block
    assert "font-variant-numeric:tabular-nums" in block


def test_eyebrow_matches_the_type_scale() -> None:
    block = _block(theme.BASE_CSS, ".k-eyebrow")
    assert "font-size:10px" in block
    assert "font-weight:600" in block
    assert "letter-spacing:.2em" in block
    assert "text-transform:uppercase" in block


# ── class constants ───────────────────────────────────────────────────────────


def test_amount_classes_are_tokens_not_tailwind_ramps() -> None:
    assert theme.AMOUNT_INCOME == "k-amount k-amount--in"
    assert theme.AMOUNT_EXPENSE == "k-amount k-amount--out"
    assert theme.AMOUNT_NEUTRAL == "k-amount k-amount--neutral"


def test_amount_class_maps_transaction_types() -> None:
    assert theme.amount_class("income") == theme.AMOUNT_INCOME
    assert theme.amount_class("expense") == theme.AMOUNT_EXPENSE
    assert theme.amount_class("transfer") == theme.AMOUNT_NEUTRAL


def test_no_constant_carries_a_tailwind_palette_class() -> None:
    constants = {
        name: value
        for name, value in vars(theme).items()
        if isinstance(value, str) and name.isupper() and not name.endswith("_CSS")
    }
    banned = re.compile(r"\b(text|bg|border)-(slate|teal|green|red|blue|amber|orange)-")
    offenders = {n: v for n, v in constants.items() if banned.search(v)}
    assert not offenders, offenders


def test_nav_items_use_the_handoff_type_and_gutter() -> None:
    # 13px labels and a 19px icon column are what let 236px hold the long
    # entries on one line; a fixed height would clip a wrap.
    assert "min-h-11" in theme.NAV_ITEM
    assert "font-size:13px" in _block(theme.BASE_CSS, ".k-nav-item .q-item__label")
    avatar = _block(theme.BASE_CSS, ".k-nav-item .q-item__section--avatar")
    # 19px glyph + 12px gutter — the column must hold the icon, and the icon
    # must be sized to it, or the glyph overflows into the label.
    assert "width:31px" in avatar
    assert "padding-right:12px" in avatar
    assert "font-size:19px" in _block(theme.BASE_CSS, ".k-nav-item .q-icon")


def test_links_use_the_accent_text_token() -> None:
    # The Prophet-unavailable link rendered in the browser's default blue
    # until this rule existed.
    assert "color:var(--k-accent-text)" in _block(theme.BASE_CSS, "a:not(.q-btn):not(.q-item)")


def test_ink_is_a_separate_token_from_the_heading_class() -> None:
    # Figures and dense grid cells are ink, but they are not headings.
    assert theme.INK == "k-ink"
    assert "color:var(--k-ink)" in _block(theme.BASE_CSS, ".k-heading,.k-ink")


def test_headings_are_ink_not_the_brand_accent() -> None:
    for constant in (theme.PAGE_TITLE, theme.SECTION_HEADING, theme.DIALOG_TITLE):
        assert "text-primary" not in constant
    assert "color:var(--k-ink)" in _block(theme.BASE_CSS, ".k-page-title")


def test_surface_has_the_single_shadow_and_no_border() -> None:
    assert "border" not in theme.SECTION_CARD
    assert "box-shadow:var(--k-card-shadow)" in _block(theme.BASE_CSS, ".k-surface")
    assert "--k-card-shadow:0 1px 2px rgba(28,26,21,.05)" in _root()


def test_dark_mode_drops_the_card_shadow() -> None:
    assert "--k-card-shadow:none" in _dark_root()


# ── shared utility classes the per-screen plans build on ──────────────────────


def test_status_dot_classes_read_the_tokens() -> None:
    assert "background:var(--k-expense)" in _block(theme.BASE_CSS, ".k-dot--danger")
    assert "background:var(--k-warning)" in _block(theme.BASE_CSS, ".k-dot--warn")
    assert "background:var(--k-accent)" in _block(theme.BASE_CSS, ".k-dot--info")


def test_quasar_cards_and_tab_panels_follow_the_surface_tokens() -> None:
    assert "background:var(--k-surface)" in _block(theme.BASE_CSS, ".q-card")
    assert "background-color:transparent" in _block(theme.BASE_CSS, ".q-tab-panels,.q-tab-panel")


def test_pace_bar_classes_are_shipped() -> None:
    for cls in (".k-pace{", ".k-pace__fill{", ".k-pace__tick{"):
        assert cls in theme.BASE_CSS, cls


def test_pace_track_matches_the_handoff_geometry() -> None:
    block = _block(theme.BASE_CSS, ".k-pace")
    assert "height:7px" in block
    assert "border-radius:4px" in block
    assert "background:var(--k-hairline)" in block


def test_pace_tick_is_an_ink_marker() -> None:
    block = _block(theme.BASE_CSS, ".k-pace__tick")
    assert "width:2px" in block
    assert "height:13px" in block
    assert "background:var(--k-ink)" in block


def test_filter_chip_classes_are_shipped() -> None:
    filled = _block(theme.BASE_CSS, ".k-filter-chip")
    assert "border-radius:999px" in filled
    empty = _block(theme.BASE_CSS, ".k-filter-chip--empty")
    assert "dashed" in empty
    assert "--k-chip-dash:#CFC5AE" in _root()


# ── stylesheet assembly ───────────────────────────────────────────────────────


def test_theme_css_is_base_plus_dark() -> None:
    assert theme.theme_css() == theme.BASE_CSS + theme.DARK_CSS


def test_dark_overrides_use_tokens_not_raw_navy_rgb() -> None:
    # Every colour in the dark block should resolve through a token.
    leftovers = [
        line
        for line in theme.DARK_CSS.splitlines()
        if "rgb(" in line and "var(--k-" not in line and "rgba(" not in line
    ]
    assert not leftovers, leftovers
