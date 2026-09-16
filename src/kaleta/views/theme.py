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
#: Secondary text — a label beside a figure, an empty cell's em dash.
MUTED = "k-muted"

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
#: The same figure in a toolbar row rather than its own card. Appending a
#: smaller size to ``KPI_VALUE`` would not work: Tailwind resolves conflicting
#: utilities by stylesheet order, not by their order in the class string, so
#: ``text-3xl`` would win wherever it appeared.
KPI_VALUE_COMPACT = "k-mono text-2xl font-medium tracking-tight"
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

# Ledger toolbar (artboard 2a): a filter is a pill that shows its value, and a
# dashed one when it has none to show.
FILTER_CHIP = "k-filter-chip"
FILTER_CHIP_EMPTY = "k-filter-chip--empty"
#: A word inside a sentence that is also a control (artboard 3e). Reads as
#: prose until the pointer is over it, so the query stays legible while every
#: part of it stays editable.
SENTENCE_SLOT = "k-slot"
#: A slot that accepts a dragged field. Carried at all times and lit only
#: while ``body`` has ``k-dragging`` — a drag highlight must not cost a server
#: round trip, because rebuilding the slot mid-drag destroys the drop target
#: the browser is aiming at.
SENTENCE_SLOT_TARGET = "k-slot--drop"
#: Set on ``body`` by the rail's own dragstart handler, cleared on dragend.
DRAGGING_BODY = "k-dragging"
SELECTION_BAR = "k-selection-bar"
#: Hover tint for a hand-built row (one that is not inside a ``k-table``).
ROW_HOVER = "k-row-hover"
#: A hand-built row's own outline — the same hairline the tables draw, so a
#: list built out of rows sits at the same weight as one built out of a table.
HAIRLINE_ROW = "k-hairline-row"
#: One rule under a row, for a list that is separated rather than boxed.
HAIRLINE_BOTTOM = "k-hairline-bottom"
#: Accent-coloured text — the recurring column, a link that is not an <a>.
ACCENT_TEXT = "k-accent-text"
#: A 3px accent rule down a card's left edge. One card on a page may say
#: "read this first"; two would say nothing.
ACCENT_RULE = "k-accent-rule"

# ── Budget plan grid (artboard 2c) ────────────────────────────────────────────
#: The annual grid is not a card: hairlines only, and the paper is the table.
PLAN_GRID = "k-plan-grid"
PLAN_HEAD = "k-plan-head"
PLAN_ROW = "k-plan-row"
PLAN_TOTAL = "k-plan-total"
#: This month's column, so the eye finds "now" in twelve identical columns.
PLAN_MONTH_NOW = "k-plan-month-now"
#: The quiet line under a category's plan, carrying what it actually spent.
PLAN_ACTUAL_ROW = "k-plan-actual"
#: A rule with nothing behind it — a heading, not a row you can act on.
PLAN_RULE = "k-plan-rule"
#: A month cell you can click to edit. Square, so the tinted column is a band.
PLAN_CELL_EDIT = "k-plan-cell"

# ── Import wizard progress line (artboard 2d) ────────────────────────────────
STEP_LINE = "k-steps"
STEP_NODE = "k-step"
STEP_NODE_DONE = "k-step--done"
STEP_NODE_NOW = "k-step--now"
STEP_LABEL = "k-step-label"
STEP_LABEL_NOW = "k-step-label k-step-label--now"
#: "auto" — this column came from detection, not from the user.
AUTO_BADGE = "k-auto-badge"
#: A warning that belongs to the step you are on, not a toast that flies past.
WARNING_STRIP = "k-warning-strip"

# ── Auth (artboard 3f) ────────────────────────────────────────────────────────
#: The ink panel beside the login form. Ink ground, paper text — the inverse
#: of every other surface in the app, because it is the one panel that is not
#: holding any of the user's figures.
AUTH_PANEL = "k-auth-panel"
#: A line kept for a message that is usually not there. Reserving it is the
#: difference between a failed login telling you something and a failed login
#: moving the button out from under the pointer. Carries its own colour, so
#: no caller has to remember which tone an error wears.
ERROR_SLOT = "k-error-slot"
#: A count on that panel: large, mono, and paper-coloured.
AUTH_PANEL_FIGURE = "k-auth-figure"
#: Its label underneath, dimmed against the ink rather than muted on paper.
AUTH_PANEL_LABEL = "k-auth-label"

# ── Top bar (artboard 1e) ─────────────────────────────────────────────────────
#: The desktop navigation, in the header. Its own breakpoint rather than
#: `hidden md:flex`, for the reason `.k-auth-panel` and `.k-tabbar` have one.
TOP_NAV = "k-topnav"
#: One pinned link or one section button in that bar.
TOP_NAV_ITEM = "k-topnav-item"
#: The section (or page) you are on.
TOP_NAV_ITEM_ACTIVE = "k-topnav-item--active"
#: The menu a section drops.
TOP_NAV_MENU = "k-topnav-menu"
#: "Jump to… ⌘K" — a search field's clothes on a button that opens a dialog.
TOP_NAV_SEARCH = "k-topnav-search"

#: The hamburger + mini pair, and the header's search icon: phone-side
#: controls that a desktop top bar makes redundant.
DRAWER_CONTROLS = "k-drawer-controls"
PHONE_SEARCH = "k-phone-search"

#: The command palette dialog, and one row in it.
PALETTE_CARD = "k-palette"
PALETTE_ROW = "k-palette-row"

# ── Phone dashboard (artboard 1f) ─────────────────────────────────────────────
#: The bottom tab bar. It has its own breakpoint rather than `md:hidden`: which
#: of two utilities wins is stylesheet order, and the auth panel already lost
#: that argument once (see `.k-auth-panel`).
TAB_BAR = "k-tabbar"
#: One tab. 44px is the floor, not the look — a thumb is not a pointer.
TAB_BAR_ITEM = "k-tabbar-item"
#: The tab you are on.
TAB_BAR_ITEM_ACTIVE = "k-tabbar-item--active"
#: The centre add button: filled accent, raised above the bar's own line.
TAB_BAR_ADD = "k-tabbar-add"
#: Room at the foot of every page so the bar never sits on the last card.
TAB_BAR_SPACER = "k-tabbar-spacer"

#: A band heading on the phone dashboard — Now, Month, Watch. Plain type on
#: the ground, no card behind it: the bands are how the page is read, not
#: three more boxes.
BAND_TITLE = "k-band-title"
#: A figure in the Watch band: label above, number below, nothing around it.
WATCH_FIGURE = "k-watch-figure"
WATCH_LABEL = "k-watch-label"

# ── Payment calendar (artboard 3c) ────────────────────────────────────────────
#: One day. Thirty-one of them fit on a screen only if each carries a figure
#: and a row of dots instead of three stacked numbers.
CALENDAR_DAY = "k-cal-day"
#: Today, found without reading a single number.
CALENDAR_DAY_TODAY = "k-cal-day--today"
#: The day whose sheet is open — the page says where you are, warm not loud.
CALENDAR_DAY_SELECTED = "k-cal-day--selected"
#: A cell belonging to the month either side. Paper, not a day.
CALENDAR_DAY_BLANK = "k-cal-day--blank"
#: The day number on a working day. Weekends take plain ``MUTED`` and today
#: takes ``INK``, so the three read as three levels without a second tint.
CALENDAR_DAY_NUM = "k-cal-num"
#: One dot per thing happening that day, coloured by which way the money goes.
CALENDAR_DOT = "k-cal-dot"
CALENDAR_DOT_IN = "k-cal-dot--in"
CALENDAR_DOT_OUT = "k-cal-dot--out"
#: Neither in nor out: a transfer between your own accounts, or a projected
#: subscription charge that is not a planned transaction you can post.
CALENDAR_DOT_FLAT = "k-cal-dot--flat"

# ── Balance-sheet bar (artboard 3b) ───────────────────────────────────────────
#: One bar, three segments: held, owned, owed. The shape of the sheet, which a
#: net figure cannot show — 10 000 owned outright and 200 000 against 190 000
#: owed are the same number and not the same position.
SPLIT_BAR = "k-split"

# ── Loading (artboard 3a) ─────────────────────────────────────────────────────
#: A page that answers on load shows the shape of the answer while it works.
#: Sunken sand rather than Quasar's grey, so the wait looks like this app.
SKELETON = "k-skeleton"

# Filled accent surface (banners, section headers, step markers) and the
# text colour that sits on it — apricot in light, ink on apricot in dark.
ACCENT_SURFACE = "k-accent-surface"
#: A tinted badge behind an icon — the accent at reading strength, not at
#: full. The forecast KPIs use it in place of the `bg-blue-500/10
#: text-blue-600` triplet they carried; the dashboard's `kpi_card` still
#: builds its own from an `icon_color` argument.
ACCENT_SOFT = "k-accent-soft"
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
  --k-surface-warm-strong:#EFE3D6;
  --k-ink:#1C1A15;
  --k-ink-2:#4A443A;
  --k-muted:#6B6353;
  --k-muted-strong:#6E6656;
  --k-disabled:#B5AB96;
  --k-hairline:#EDE7DA;
  --k-border:#E2DBCC;
  --k-border-strong:#C9BFA8;
  --k-accent:#B4591F;
  --k-accent-soft:#F4E3D5;
  --k-accent-text:#9A4E1F;
  --k-accent-light:#DE7B45;
  --k-income:#36684D;
  --k-expense:#A44631;
  --k-warning:#8A5A12;
  --k-neutral-bar:#8E8676;

  --k-row-hover:#FAF4E9;
  --k-plan-now:#F0E5D4;
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
  --k-surface-warm-strong:var(--k-surface-sunken);
  --k-ink:#F0EBDF;
  --k-ink-2:#CFC7B6;
  --k-muted:#A8A08D;
  --k-muted-strong:#A19781;
  --k-disabled:#6E6656;
  --k-hairline:#2A2822;
  --k-border:#322F27;
  --k-border-strong:#453F34;
  --k-accent:#E8935B;
  --k-accent-soft:#3A2E24;
  --k-accent-text:#E8935B;
  --k-accent-light:#E8935B;
  --k-income:#6FAF87;
  --k-expense:#DE8672;
  --k-warning:#E3B457;

  --k-row-hover:#262420;
  --k-plan-now:#332F26;
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
/* 767.98px, not 768px: the tab bar and the server-side layout choice both
   put a 768px-wide window (an iPad in portrait) on the desktop side, and a
   desktop grid with phone padding is neither. */
@media (max-width:767.98px){.k-dash-page{padding:20px 16px 28px;gap:28px}}
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
.k-row-hover:hover{background:var(--k-row-hover)}
.k-hairline-row{border:1px solid var(--k-hairline)}
.k-hairline-bottom{border-bottom:1px solid var(--k-hairline)}
.k-accent-text{color:var(--k-accent-text)}
.k-accent-rule{border-left:3px solid var(--k-accent)}
/* Budget plan grid: no card, no shadow — hairlines, and the paper is the
   table. The header and the totals band are the only strong rules. */
.k-plan-grid{background:transparent}
.k-plan-head{
  border-bottom:1px solid var(--k-border-strong);
  color:var(--k-muted)
}
.k-plan-row{border-bottom:1px solid var(--k-hairline)}
.k-plan-row:hover{background:var(--k-row-hover)}
.k-plan-rule{border-bottom:1px solid var(--k-hairline)}
/* An editable month outlines itself on hover: a fill would fight the
   current-month tint it has to work on top of. */
.k-plan-cell:hover{outline:1px solid var(--k-border-strong);outline-offset:-1px}
/* Import wizard: a hairline with six nodes on it. The connecting rule runs
   behind the nodes, which sit on the page ground so it does not show through. */
.k-steps{position:relative}
.k-steps::before{
  content:"";
  position:absolute;
  left:8%;
  right:8%;
  top:11px;
  height:1px;
  background:var(--k-hairline)
}
.k-step{
  position:relative;
  width:22px;
  height:22px;
  border-radius:999px;
  border:1px solid var(--k-border-strong);
  background:var(--k-ground);
  color:var(--k-muted);
  font-size:11px;
  font-weight:600;
  display:flex;
  align-items:center;
  justify-content:center
}
.k-step--done{background:var(--k-ink);border-color:var(--k-ink);color:var(--k-surface)}
.k-step--now{
  background:var(--k-accent);
  border-color:var(--k-accent);
  color:var(--k-on-accent)
}
.k-step-label{font-size:11px;color:var(--k-muted);text-align:center;line-height:1.2}
.k-step-label--now{color:var(--k-ink);font-weight:600}
.k-auto-badge{
  align-self:flex-start;
  font-size:10px;
  font-weight:600;
  letter-spacing:.04em;
  text-transform:uppercase;
  color:var(--k-income);
  border:1px solid var(--k-income);
  border-radius:999px;
  padding:0 6px;
  line-height:15px
}
.k-error-slot{
  min-height:20px;line-height:20px;font-size:13px;
  color:var(--k-expense)
}

/* Auth (artboard 3f) — the one ink surface in the app. Its own text colours
   rather than the tokens, which are all defined against paper. */
/* The panel's own breakpoint. `hidden md:flex` leaves which rule wins to
   utility ordering, and on this page `hidden` won at every width. */
.k-auth-panel{display:none;background:var(--k-ink);color:var(--k-surface)}
@media (min-width:768px){
  .k-auth-panel{display:flex;flex-direction:column}
}
.k-auth-figure{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:30px;line-height:1.1;font-weight:400;color:var(--k-surface)
}
.k-auth-label{
  font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:var(--k-surface);opacity:.6
}

/* Payment calendar (artboard 3c) — the grid is 31 small cells, so every
   pixel of border and padding is charged 31 times. */
.k-cal-day{
  border:1px solid var(--k-hairline);
  border-radius:10px;
  background:var(--k-surface);
  cursor:pointer;
  transition:background-color .12s ease,border-color .12s ease
}
.k-cal-day:hover{background:var(--k-row-hover)}
.k-cal-day--today{border:2px solid var(--k-ink)}
.k-cal-day--selected{background:var(--k-surface-warm)}
.k-cal-day--selected:hover{background:var(--k-surface-warm-strong)}
.k-cal-day--blank{
  border:1px dashed var(--k-hairline);
  border-radius:10px;
  background:transparent
}
.k-cal-num{color:var(--k-muted-strong)}
.k-cal-dot{width:6px;height:6px;border-radius:999px;flex:none}
.k-cal-dot--in{background:var(--k-income)}
.k-cal-dot--out{background:var(--k-expense)}
.k-cal-dot--flat{background:var(--k-border-strong)}

/* Balance-sheet bar (artboard 3b) — segments meet with no gap, so their
   widths are the only thing saying how big each side is. */
.k-split{
  display:flex;align-items:stretch;gap:0;
  height:10px;border-radius:999px;overflow:hidden;
  background:var(--k-surface-sunken)
}
.k-split-seg{height:100%}
.k-split-dot{width:8px;height:8px;border-radius:999px;flex:none}
.k-split--ink{background:var(--k-ink)}
.k-split--neutral{background:var(--k-border-strong)}
.k-split--owed{background:var(--k-expense)}
/* Safe-to-spend (artboard 1f): what is promised, what is gone, what is left. */
.k-split--spent{background:var(--k-neutral-bar)}
.k-split--free{background:var(--k-accent-light)}

/* Top bar (artboard 1e) — five sections and a search where a 24-item drawer
   used to be. Below the breakpoint the tab bar and the drawer take over.
   `.k-topnav-search` carries the rule too: the button is a sibling of the
   row, not a child of it, so hiding the row leaves the phone with a wide
   "Jump to…" pill *and* the `.k-phone-search` icon opening the same dialog. */
.k-topnav,.q-btn.k-topnav-search{display:none}
@media (min-width:768px){
  .k-topnav{display:flex}
  .q-btn.k-topnav-search{display:inline-flex}
}
/* `.q-btn.k-topnav-item`, two classes: NiceGUI gives every button
   `color=primary`, and a single-class rule loses to Quasar's `.text-primary`
   — the same trick `.q-skeleton.k-skeleton` uses, and for the same reason. */
.q-btn.k-topnav-item{
  border-radius:8px;
  color:var(--k-muted-strong);
  font-weight:500;
  letter-spacing:0;
  min-height:34px;
  padding:0 10px
}
.q-btn.k-topnav-item:hover{background:var(--k-surface-warm)}
.q-btn.k-topnav-item.k-topnav-item--active{
  color:var(--k-accent-text);
  background:var(--k-surface-warm)
}
.k-topnav-menu{
  background:var(--k-surface);
  border:1px solid var(--k-border);
  border-radius:12px;
  box-shadow:var(--k-card-shadow)
}
.q-btn.k-topnav-search{
  border:1px solid var(--k-border);
  border-radius:999px;
  color:var(--k-muted);
  min-height:34px;
  padding:0 14px
}
.q-btn.k-topnav-search:hover{background:var(--k-surface-warm)}
.k-drawer-controls,.k-phone-search{display:flex}
@media (min-width:768px){
  .k-drawer-controls,.k-phone-search{display:none}
}
.k-palette{
  background:var(--k-surface);
  border:1px solid var(--k-border);
  border-radius:14px;
  padding:14px
}
.k-palette-row{
  border-radius:8px;
  color:var(--k-ink);
  padding:9px 10px
}
.k-palette-row:hover{background:var(--k-row-hover)}

/* Phone dashboard (artboard 1f) — the bar is the navigation below `md`, and
   the drawer is what "More" opens. Its own breakpoint, for the same reason
   `.k-auth-panel` has one. */
/* `display:none`, not a zero height: the page column is a flex container with
   a gap, and a zero-height child still takes a gap's worth of space at the
   foot of every desktop page. */
.k-tabbar-spacer{display:none}
.k-tabbar{
  display:none;
  position:fixed;left:0;right:0;bottom:0;z-index:2100;
  background:var(--k-surface);
  border-top:1px solid var(--k-border);
  padding-bottom:env(safe-area-inset-bottom)
}
@media (max-width:767.98px){
  .k-tabbar{display:flex;align-items:stretch;justify-content:space-around}
  .k-tabbar-spacer{display:block;height:calc(64px + env(safe-area-inset-bottom))}
}
.k-tabbar-item{
  flex:1 1 0;min-width:0;min-height:44px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
  padding:8px 4px;cursor:pointer;
  color:var(--k-muted);
  font-size:10px;letter-spacing:.04em;
  background:none;border:none
}
.k-tabbar-item--active{color:var(--k-accent-text)}
.k-tabbar-add{
  min-width:44px;min-height:44px;
  align-self:center;
  border-radius:999px;
  background:var(--k-accent);color:var(--k-on-accent);
  display:flex;align-items:center;justify-content:center;
  border:none;cursor:pointer
}

.k-band-title{
  font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:var(--k-muted)
}
.k-watch-label{font-size:11px;color:var(--k-muted)}
.k-watch-figure{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:19px;font-weight:500;line-height:1.2;color:var(--k-ink)
}

/* Loading (artboard 3a) — a page that answers on load shows the shape of the
   answer while it works. `.q-skeleton.k-skeleton` rather than `!important`:
   two classes outrank Quasar's own one, whichever order the sheets land in. */
.q-skeleton.k-skeleton{
  background:var(--k-surface-sunken);
  border:1px solid var(--k-hairline)
}
.q-skeleton.k-skeleton::after{background:var(--k-surface);opacity:.35}

.k-warning-strip{
  background:var(--k-surface-warm);
  border-left:2px solid var(--k-warning);
  color:var(--k-ink)
}
.k-warning-strip .q-icon{color:var(--k-warning)}
.k-plan-total{border-top:1px solid var(--k-border-strong)}
.k-plan-month-now{background:var(--k-plan-now)}
.k-cat-row{border-bottom-color:var(--k-hairline)}
.k-cat-row:hover{background:var(--k-row-hover)}
.k-subcat-label{color:var(--k-ink-2)}
.k-selection-bar{background:var(--k-surface-warm-strong);color:var(--k-ink)}
.k-clear-all{color:var(--k-accent-text)}
.k-clear-all:hover{text-decoration:underline}
/* Grouping toggle below the ledger: one segmented pill, not three buttons. */
.k-group-toggle{background:var(--k-surface-sunken);border-radius:999px;padding:2px}
.k-group-toggle .q-btn{border-radius:999px;font-size:11.5px;min-height:24px;padding:0 10px}
/* Ledger rows: the category reads as a pill, the group separator as a band. */
.k-cat-pill{
  display:inline-block;
  padding:3px 9px;
  border-radius:999px;
  background:var(--k-surface-sunken);
  color:var(--k-ink-2);
  font-size:11.5px
}
.k-sep-row{
  background:var(--k-surface-warm);
  color:var(--k-ink-2);
  font-size:11px;
  font-weight:500;
  letter-spacing:.04em;
  border-bottom:1px solid var(--k-hairline)
}

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
.k-slot{
  display:inline-flex;align-items:center;gap:.25rem;
  padding:1px 4px;margin:0 1px;border-radius:5px;
  color:var(--k-accent-text);
  border-bottom:1px dashed var(--k-chip-dash);
  cursor:pointer;
  transition:background-color .12s ease
}
.k-slot:hover{background:var(--k-surface-sunken);border-bottom-color:transparent}
body.k-dragging .k-slot--drop{
  background:var(--k-surface-warm);
  border:1px dashed var(--k-accent);
  border-bottom-color:var(--k-accent);
  border-radius:5px
}
.k-filter-chip--empty{
  background:transparent;
  border:1px dashed var(--k-chip-dash);
  color:var(--k-muted)
}

/* ── Banners & chips ──────────────────────────────────────────────── */
.k-accent-surface{background:var(--k-accent);color:var(--k-on-accent)}
.k-accent-soft{background:var(--k-accent-soft);color:var(--k-accent)}
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
