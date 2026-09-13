# SPDX-License-Identifier: AGPL-3.0-or-later
"""Theme tokens and stylesheet — the "sand" visual language.

Every colour in the app comes from a CSS custom property declared once on
``:root`` (light) and once on ``.body--dark`` (warm dark), so a ``.k-*``
utility class is written a single time and works in both modes. See
``docs/design/restyle/README.md`` for the token tables this file mirrors.
"""

from __future__ import annotations

from nicegui import ui

# Semantic colour tokens for transaction amounts. Every amount is IBM Plex
# Mono with tabular figures so columns align; the colour comes from the
# income/expense tokens, never from a Tailwind ramp.
AMOUNT_INCOME = "k-amount k-amount--in"
AMOUNT_EXPENSE = "k-amount k-amount--out"
AMOUNT_NEUTRAL = "k-amount k-amount--neutral"
#: A figure that is off-plan but not yet alarming (small budget overage).
AMOUNT_WARNING = "k-amount k-amount--warn"

# Opt-in monospace for non-amount numbers (dates, counts, percentages, the
# version string) — same family and tabular figures, inherited colour.
MONO = "k-mono"

# Shared surface tokens — paper on ground, 1px shadow instead of a border.
_SURFACE = "k-surface w-full rounded-xl"
_CARD_PAD = "p-5"

PAGE_SHELL = "k-ground"
PAGE_CONTAINER = "w-full mx-auto p-6 md:p-8 gap-6"
# The dashboard breathes wider than the working screens: 36/40/44 page
# padding and a 44px band gap (handoff geometry table, artboard 1c).
DASH_PAGE_CONTAINER = "k-dash-page w-full mx-auto"

HEADER = "k-header"
DRAWER = "k-drawer pt-3"

NAV_GROUP = "k-nav-group k-eyebrow flex-1"
NAV_GROUP_ROW = (
    "k-nav-row items-center h-9 px-3 mx-2 rounded-lg cursor-pointer select-none transition-colors"
)
NAV_ITEM = "k-nav-item min-h-11 rounded-lg mx-3 mb-[3px] px-3 cursor-pointer transition-colors"
NAV_ITEM_ACTIVE = "k-nav-item--active"

PAGE_TITLE = "k-page-title text-[32px] font-light tracking-tight"
SECTION_CARD = f"{_SURFACE} {_CARD_PAD}"
TOOLBAR_CARD = f"{_SURFACE} p-3"
SECTION_TITLE = "k-muted k-eyebrow"
SECTION_HEADING = "k-heading text-lg font-medium"
DIALOG_TITLE = "k-heading text-lg font-medium"
BODY_MUTED = "k-muted text-sm"

KPI_VALUE = "k-mono text-3xl font-medium tracking-tight"
KPI_TREND_POSITIVE = "k-trend--pos"
KPI_TREND_NEGATIVE = "k-trend--neg"
KPI_TREND_NEUTRAL = "k-trend--neutral"

TABLE_CARD = SECTION_CARD
TABLE_SURFACE = "k-table w-full"

# Dashboard chrome (handoff geometry table): 14px radius and 26/28px padding,
# against 12px / 22-24px on the working screens.
DASH_CARD = f"{_SURFACE} k-dash-card"
CARD_TITLE = "k-card-title"
CARD_SUBTITLE = "k-card-subtitle"

# Filled accent surface (banners, section headers, step markers) and the
# text colour that sits on it — apricot in light, ink on apricot in dark.
ACCENT_SURFACE = "k-accent-surface"
ON_ACCENT = "k-on-accent"

# Plain ink text for figures and dense grid cells (not a heading).
INK = "k-ink"

# Quasar brand colours. NiceGUI writes its own defaults onto <body> at runtime,
# which outranks any `:root` rule, so `apply_brand()` must run on every page that
# loads `theme_css()` — the `:root` block below is the static fallback.
QUASAR_BRAND = {
    "primary": "#B4591F",
    "secondary": "#6B6353",
    "accent": "#DE7B45",
    "positive": "#36684D",
    "negative": "#A44631",
    "info": "#9A4E1F",
    "warning": "#8A5A12",
    "dark": "#201F1A",
    "dark_page": "#171613",
}


def apply_brand() -> None:
    """Push the sand brand onto Quasar for the current page."""
    ui.colors(**QUASAR_BRAND)


# Fonts, brand variables and the design tokens every .k-* class reads.
BASE_CSS = """
@font-face{
  font-family:'Libre Franklin';
  font-style:normal;
  font-weight:100 900;
  font-display:swap;
  src:url('/static/fonts/libre-franklin-var.woff2') format('woff2')
}
@font-face{
  font-family:'IBM Plex Mono';
  font-style:normal;
  font-weight:400;
  font-display:swap;
  src:url('/static/fonts/ibm-plex-mono-400.woff2') format('woff2')
}
@font-face{
  font-family:'IBM Plex Mono';
  font-style:normal;
  font-weight:500;
  font-display:swap;
  src:url('/static/fonts/ibm-plex-mono-500.woff2') format('woff2')
}
:root{
  --q-primary:#B4591F;
  --q-secondary:#6B6353;
  --q-accent:#DE7B45;
  --q-positive:#36684D;
  --q-negative:#A44631;
  --q-info:#9A4E1F;
  --q-warning:#8A5A12;

  --k-ground:#F3EFE7;
  --k-surface:#FCFAF6;
  --k-surface-sunken:#F3EFE7;
  --k-surface-warm:#F6F1E7;
  --k-ink:#1C1A15;
  --k-ink-2:#4A443A;
  --k-muted:#6B6353;
  --k-muted-strong:#6E6656;
  --k-disabled:#B5AB96;
  --k-hairline:#EDE7DA;
  --k-border:#E2DBCC;
  --k-border-strong:#C9BFA8;
  --k-accent:#B4591F;
  --k-accent-text:#9A4E1F;
  --k-accent-light:#DE7B45;
  --k-income:#36684D;
  --k-expense:#A44631;
  --k-warning:#8A5A12;
  --k-neutral-bar:#8E8676;

  --k-row-hover:#FAF4E9;
  --k-chip-dash:#CFC5AE;
  --k-card-shadow:0 1px 2px rgba(28,26,21,.05);
  --k-on-accent:#FCFAF6
}
.body--dark{
  --q-primary:#E8935B;
  --q-info:#E8935B;

  --k-ground:#171613;
  --k-surface:#201F1A;
  --k-surface-sunken:#2A2822;
  --k-surface-warm:#262420;
  --k-ink:#F0EBDF;
  --k-ink-2:#CFC7B6;
  --k-muted:#A8A08D;
  --k-muted-strong:#A19781;
  --k-disabled:#6E6656;
  --k-hairline:#2A2822;
  --k-border:#322F27;
  --k-border-strong:#453F34;
  --k-accent:#E8935B;
  --k-accent-text:#E8935B;
  --k-accent-light:#E8935B;
  --k-income:#6FAF87;
  --k-expense:#DE8672;
  --k-warning:#E3B457;

  --k-row-hover:#262420;
  --k-chip-dash:#453F34;
  --k-card-shadow:none;
  --k-on-accent:#241C13
}
body,.q-body--layout{
  font-family:'Libre Franklin',ui-sans-serif,system-ui,sans-serif
}
body{background-color:var(--k-ground);color:var(--k-ink)}
.k-ground{background-color:var(--k-ground)}

/* ── Surfaces & shell ─────────────────────────────────────────────── */
.k-surface{background:var(--k-surface);box-shadow:var(--k-card-shadow)}
.k-header{
  background:var(--k-surface);
  color:var(--k-ink);
  border-bottom:1px solid var(--k-border)
}
/* Quasar paints its own white on these; make them read the tokens so a
   plain ui.card() is paper on ground without every view opting in. */
.q-card{background:var(--k-surface);color:var(--k-ink)}
.q-tab-panels,.q-tab-panel{background-color:transparent}
.k-drawer,
.k-drawer .q-drawer__content{
  background:var(--k-ground);
  border-right-color:var(--k-border)
}

/* ── Navigation — a quiet index, no per-item boxes ────────────────── */
.k-nav-group{color:var(--k-muted-strong)}
.k-nav-row:hover{background:var(--k-surface)}
.k-nav-item{color:var(--k-ink-2)}
.k-nav-item:hover{background:var(--k-surface)}
.k-nav-item .q-item__label{color:var(--k-ink-2);font-size:13px;line-height:1.3}
/* Quasar reserves 56px for the avatar column; the handoff's drawer is a
   19px icon and a 12px gap, which is what lets 236px hold the long labels. */
.k-nav-item .q-item__section--avatar{
  min-width:0;
  width:31px;
  flex:0 0 31px;
  padding-right:12px
}
.k-nav-item .q-icon{font-size:19px}
.k-nav-item:not(.k-nav-item--active) .q-icon{color:var(--k-muted)!important}
.k-nav-item--active{background:var(--k-surface);box-shadow:var(--k-card-shadow)}
.k-nav-item--active .q-item__label{color:var(--k-ink);font-weight:600}
.k-nav-item--active .q-icon{color:var(--k-accent-text)!important}
.k-app-version{color:var(--k-muted)}

/* ── Typography ───────────────────────────────────────────────────── */
.k-page-title{color:var(--k-ink);letter-spacing:-.02em}
.k-heading,.k-ink{color:var(--k-ink)}
.k-eyebrow{
  font-size:10px;
  font-weight:600;
  letter-spacing:.2em;
  text-transform:uppercase;
  color:var(--k-muted-strong)
}
.k-muted{color:var(--k-muted)}
/* Links are actions: accent text, never the browser's default blue. */
a:not(.q-btn):not(.q-item){color:var(--k-accent-text)}
.k-mono,.k-amount{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums
}
.k-amount--in{color:var(--k-income)}
.k-amount--out{color:var(--k-expense)}
.k-amount--neutral{color:var(--k-muted)}
.k-amount--warn{color:var(--k-warning)}
.k-trend--pos{color:var(--k-income)}
.k-trend--neg{color:var(--k-expense)}
.k-trend--warn{color:var(--k-warning)}
.k-dot--danger{background:var(--k-expense)}
.k-dot--warn{background:var(--k-warning)}
.k-dot--info{background:var(--k-accent)}
.k-trend--neutral{color:var(--k-muted)}

/* ── Tables ───────────────────────────────────────────────────────── */
.k-table .q-table,
.k-table .q-table__container,
.k-table .q-table thead,
.k-table .q-table tbody,
.k-table .q-table thead tr,
.k-table .q-table tbody tr{background-color:transparent}
.k-table .q-table__top{padding-left:0;padding-right:0}
.k-table .q-table th{
  font-size:10px;
  font-weight:600;
  letter-spacing:.14em;
  text-transform:uppercase;
  color:var(--k-muted-strong)
}
.k-table .q-table td{font-size:13.5px;color:var(--k-ink)}
.k-table .q-table tbody tr:hover{background:var(--k-row-hover)}
.k-dash-page{padding:36px 40px 44px;gap:44px}
@media (max-width:768px){.k-dash-page{padding:20px 16px 28px;gap:28px}}
.k-dash-card{border-radius:14px;padding:26px 28px}
.k-account-chip{background:var(--k-surface-sunken)}
/* Hairline above a card's slow figures (month card footer, artboard 1c). */
.k-card-footer{border-top:1px solid var(--k-hairline)}
.k-card-title{
  font-size:17px;
  font-weight:500;
  color:var(--k-ink);
  line-height:1.3
}
.k-card-subtitle{font-size:12px;color:var(--k-muted);line-height:1.4}
.k-cat-row{border-bottom-color:var(--k-hairline)}
.k-cat-row:hover{background:var(--k-row-hover)}
.k-subcat-label{color:var(--k-ink-2)}
.k-selection-bar{background:var(--k-surface-warm);color:var(--k-ink)}

/* ── Shared utility classes (used by the per-screen restyle plans) ── */
.k-pace{
  position:relative;
  height:7px;
  border-radius:4px;
  background:var(--k-hairline)
}
.k-pace__fill{position:absolute;top:0;bottom:0;left:0;border-radius:4px}
.k-pace__tick{
  position:absolute;
  top:-3px;
  width:2px;
  height:13px;
  background:var(--k-ink)
}
.k-filter-chip{
  display:inline-flex;align-items:center;gap:.4rem;
  padding:6px 12px;border-radius:999px;
  background:var(--k-surface-sunken);
  color:var(--k-ink-2);
  font-size:12.5px;line-height:1.2;
  cursor:pointer
}
.k-filter-chip--empty{
  background:transparent;
  border:1px dashed var(--k-chip-dash);
  color:var(--k-muted)
}

/* ── Banners & chips ──────────────────────────────────────────────── */
.k-accent-surface{background:var(--k-accent);color:var(--k-on-accent)}
.k-accent-surface .q-icon,.k-on-accent{color:var(--k-on-accent)}
/* Dashboard "needs attention" strip (artboard 1c). */
.k-banner,.k-banner .k-banner-item{color:var(--k-on-accent)}
.k-banner .k-banner-item:hover{text-decoration:underline}
.k-banner-btn{
  background:var(--k-surface);
  color:var(--k-accent-text);
  font-weight:600;
  font-size:12.5px;
  border-radius:999px;
  padding:9px 18px
}
.k-info-banner{background:rgba(180,89,31,.08);color:var(--k-ink-2)}
.k-stat-chip{
  display:inline-flex;align-items:center;gap:.35rem;
  padding:.25rem .75rem;border-radius:9999px;
  font-size:.875rem;font-weight:500;line-height:1.25
}
.k-stat-chip--expense{background:rgba(164,70,49,.12);color:var(--k-expense)}
.k-stat-chip--income{background:rgba(54,104,77,.12);color:var(--k-income)}
.k-stat-chip--transfer{background:rgba(142,134,118,.18);color:var(--k-muted)}
.body--dark .k-info-banner{background:rgba(232,147,91,.14)}
.body--dark .k-stat-chip--expense{background:rgba(222,134,114,.18)}
.body--dark .k-stat-chip--income{background:rgba(111,175,135,.18)}
.body--dark .k-stat-chip--transfer{background:rgba(168,160,141,.18)}

/* ── Tailwind ramp → sand tokens ──────────────────────────────────────
   Views still spell muted text and sunken panels with Tailwind's cool
   slate ramp. Remapping the ramp here keeps those 250-odd call sites
   warm in both modes without a mechanical rewrite of every view. Only
   classes a grep of src/kaleta/views proves are still referenced are
   listed; see the plan's Implementation notes for the survivor table. */
.text-slate-400{color:var(--k-disabled)}
.text-slate-500{color:var(--k-muted)}
.text-slate-600{color:var(--k-muted-strong)}
.text-slate-700{color:var(--k-ink-2)}
.bg-slate-50{background-color:var(--k-surface-warm)}
.bg-slate-100{background-color:var(--k-surface-sunken)}
.bg-slate-200{background-color:var(--k-hairline)}
.bg-slate-600,.bg-slate-700{background-color:var(--k-ink)}
.hover\\:bg-slate-50:hover{background-color:var(--k-row-hover)}
.hover\\:bg-slate-100:hover{background-color:var(--k-surface-sunken)}
.hover\\:bg-slate-700:hover{background-color:var(--k-ink-2)}
.border-slate-200,.border-slate-300{border-color:var(--k-border)}
"""

# Dark-mode overrides via Quasar `.body--dark` on <body>.
#
# Everything token-driven above already follows the mode; what remains here
# are Quasar components that paint their own colours (menus, dialogs,
# fields, pickers, uploader, scrollbars) plus the `!important` survivors
# for Tailwind classes the views still use directly.
DARK_CSS = """
body.body--dark{background-color:var(--k-ground);color-scheme:dark}
.body--dark .q-header{
  background:var(--k-surface);
  color:var(--k-ink);
  border-bottom-color:var(--k-border)
}
.body--dark .q-drawer,
.body--dark .q-drawer__content{
  background:var(--k-ground);
  border-right-color:var(--k-border)
}
.body--dark .q-card--dark,
.body--dark .q-card.q-dark{
  background:var(--k-surface);
  color:var(--k-ink);
  border-color:var(--k-border)
}
.body--dark .q-table--dark,
.body--dark .q-table--dark .q-table__top,
.body--dark .q-table--dark .q-table__bottom,
.body--dark .q-table--dark thead,
.body--dark .q-table--dark tbody,
.body--dark .q-table--dark tr{background-color:transparent}
.body--dark .q-table--dark td{color:var(--k-ink)}
.body--dark .q-table--dark .q-table th{color:var(--k-muted-strong)}
.body--dark .nicegui-expansion-content .border-b{border-bottom-color:var(--k-border)}
.body--dark .q-toggle__track{background:rgba(168,160,141,.35)}

@layer quasar_importants {
  /* Survivors only. A class the BASE_CSS ramp already remaps needs no entry
     here: that rule resolves through a var() which flips under .body--dark
     (measured in the browser, see Implementation notes). What remains is the
     classes whose dark value must *differ* from the light one, plus the
     tints BASE_CSS leaves alone. bg-slate-600/700 are inverted chips: the
     base rule gives them --k-ink, which is right in light (dark chip, white
     text) but resolves to near-white on white in dark — hence the override
     to the mid surface tone below. */
  .body--dark .bg-slate-600,
  .body--dark .bg-slate-700{background:var(--k-surface-sunken) !important}
  .body--dark .bg-green-1{background:rgba(111,175,135,.15) !important}
  .body--dark .bg-blue-1{background:rgba(232,147,91,.12) !important}
  .body--dark .bg-amber-1{background:rgba(227,180,87,.15) !important}
  .body--dark .text-orange-8{color:var(--k-accent-text) !important}
}
.body--dark .bg-slate-100{border-color:var(--k-border)}
.body--dark .hover\\:bg-slate-50:hover{background:var(--k-row-hover) !important}
.body--dark .hover\\:bg-slate-100:hover{background:var(--k-surface-sunken) !important}
.body--dark .hover\\:bg-slate-700:hover{background:var(--k-surface-warm) !important}

.body--dark .q-menu{
  background:var(--k-surface);
  color:var(--k-ink);
  border:1px solid var(--k-border)
}
.body--dark .q-menu .q-item{color:var(--k-ink)}
.body--dark .q-menu .q-item__label--caption,
.body--dark .q-menu .q-item__label--header{color:var(--k-muted)}
.body--dark .q-menu .q-item:hover,
.body--dark .q-menu .q-item--active,
.body--dark .q-menu .q-item.q-manual-focusable--focused{
  background:var(--k-surface-sunken)
}
.body--dark .q-menu .q-separator{background:var(--k-border)}
.body--dark .q-tooltip{
  background:var(--k-surface-sunken);
  color:var(--k-ink)
}
.body--dark .q-date,
.body--dark .q-time{background:var(--k-ground);color:var(--k-ink)}
.body--dark .q-date__header,
.body--dark .q-time__header{background:var(--k-surface);color:var(--k-ink)}
.body--dark .q-date__calendar-item--fill,
.body--dark .q-date__calendar-item--out{color:var(--k-muted)}
.body--dark .q-date__calendar-item > div,
.body--dark .q-date__calendar-weekdays > div{color:var(--k-ink)}
.body--dark .q-date__navigation .q-btn,
.body--dark .q-date__view .q-btn{color:var(--k-ink)}
.body--dark .q-dialog__inner > .q-card{
  background:var(--k-surface);
  color:var(--k-ink);
  border:1px solid var(--k-border)
}
.body--dark .q-dialog .q-separator{background:var(--k-border)}
.body--dark .q-field--outlined .q-field__control{color:var(--k-ink)}
.body--dark .q-field--outlined .q-field__control:before{border-color:var(--k-border)}
.body--dark .q-field--outlined:hover .q-field__control:before{border-color:var(--k-muted)}
.body--dark .q-field__native,
.body--dark .q-field__input,
.body--dark .q-field__prefix,
.body--dark .q-field__suffix{color:var(--k-ink)}
.body--dark .q-field__label{color:var(--k-muted)}
.body--dark .q-field--filled .q-field__control{background:var(--k-surface-sunken)}
.body--dark .q-placeholder::placeholder{color:var(--k-muted)}
.body--dark .q-chip{background:var(--k-surface-sunken);color:var(--k-ink)}
.body--dark .q-separator{background:var(--k-border)}
.body--dark hr.q-separator--horizontal{background:var(--k-border)}
.body--dark .q-table__bottom,
.body--dark .q-table__top{
  color:var(--k-muted);
  border-color:var(--k-border)
}
.body--dark .q-pagination .q-btn{color:var(--k-ink)}
.body--dark .nicegui-echart text{fill:var(--k-muted)}
.body--dark .q-expansion-item__toggle-icon,
.body--dark .q-expansion-item .q-item__label{color:var(--k-ink)}
.body--dark .q-notification{background:var(--k-surface);color:var(--k-ink)}
.body--dark .q-uploader--dark,
.body--dark .q-uploader{
  background:var(--k-surface);
  color:var(--k-ink);
  border-color:var(--k-border)
}
.body--dark .q-uploader__header{background:var(--k-ground);color:var(--k-ink)}
.body--dark .q-uploader__subtitle,
.body--dark .q-uploader__title{color:var(--k-ink)}
.body--dark .q-uploader__list{background:var(--k-surface)}
.body--dark ::-webkit-scrollbar{width:10px;height:10px}
.body--dark ::-webkit-scrollbar-track{background:var(--k-ground)}
.body--dark ::-webkit-scrollbar-thumb{
  background:var(--k-border-strong);
  border-radius:4px;
  border:2px solid var(--k-ground)
}
.body--dark ::-webkit-scrollbar-thumb:hover{background:var(--k-muted-strong)}
.body--dark ::-webkit-scrollbar-corner{background:var(--k-ground)}
.body--dark *{scrollbar-color:var(--k-border-strong) var(--k-ground);scrollbar-width:thin}
.q-drawer__content{overflow-x:hidden}
.q-drawer--mini .k-nav-row,
.q-drawer--mini .k-app-version{display:none !important}
.q-drawer--mini .q-drawer__content{padding:8px 0 !important}
.q-drawer--mini .nicegui-column{width:100% !important;gap:2px;align-items:center}
.q-drawer--mini .q-item{
  margin:2px 4px !important;
  padding:8px 0 !important;
  min-height:44px;
  width:calc(100% - 8px);
  display:flex;
  justify-content:center !important;
  align-items:center
}
.q-drawer--mini .q-item__section--avatar{
  min-width:0 !important;
  padding:0 !important;
  width:24px;
  flex:0 0 24px;
  justify-content:center;
  align-items:center
}
.q-drawer--mini .q-item__section:not(.q-item__section--avatar){
  display:none !important
}
.q-drawer--mini .q-separator{margin:6px 12px}
"""


def theme_css() -> str:
    """Full theme stylesheet: fonts, sand tokens, dark overrides."""
    return BASE_CSS + DARK_CSS


def amount_class(tx_type: str) -> str:
    """Return the colour class for an amount cell given its transaction type."""
    if tx_type == "income":
        return AMOUNT_INCOME
    if tx_type == "expense":
        return AMOUNT_EXPENSE
    return AMOUNT_NEUTRAL


def kpi_card_classes() -> str:
    return f"{_SURFACE} flex-1 min-w-52 {_CARD_PAD}"


def icon_badge_classes(color: str) -> str:
    return f"h-10 w-10 rounded-xl bg-{color}-500/10 text-{color}-600"
