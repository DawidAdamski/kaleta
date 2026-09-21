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
#: The same role a step warmer: the artboards use it wherever muted type sits
#: *inside* a figure — a hero's decimals, an eyebrow, an axis label.
MUTED_STRONG = "k-muted-strong"

# Shared surface tokens — paper on ground, 1px shadow instead of a border.
_SURFACE = "k-surface w-full rounded-xl"
_CARD_PAD = "p-5"

PAGE_SHELL = "k-ground"
# The working screens' content column. Every artboard from `2a` on draws the
# same 32/36/40 padding; the column gap is the one value that moves between
# them, so it has modifiers rather than nine containers.
PAGE_CONTAINER = "k-page w-full mx-auto"
#: Artboards `2b`, `3a` and `3e` set the column gap at 22 rather than 20.
PAGE_GAP_22 = "k-page--gap-22"
#: Artboard `2d`: two tall cards side by side, 24 apart.
PAGE_GAP_24 = "k-page--gap-24"
#: Artboard `3d`, which breathes like the dashboard but two pixels tighter.
PAGE_GAP_26 = "k-page--gap-26"
#: Artboard `3e`: no page padding at all, and the page lies on its side so a
#: rail can hug the drawer.
PAGE_FLUSH = "k-page--flush"
#: Artboard `2c`, whose twelve month columns need the four pixels a side.
PAGE_TIGHT = "k-page--tight"
#: Artboards `3b` and `3d` breathe like the dashboard — 36/40/44 and a wider
#: gap, because both are pages you read rather than pages you work in.
PAGE_ROOMY = "k-page--roomy"
# The dashboard breathes wider than the working screens: 36/40/44 page
# padding and a 44px band gap (handoff geometry table, artboard 1c).
DASH_PAGE_CONTAINER = "k-dash-page w-full mx-auto"

HEADER = "k-header"
DRAWER = "k-drawer"

NAV_GROUP = "k-nav-group flex-1"
NAV_GROUP_ROW = "k-nav-row w-full items-center cursor-pointer select-none transition-colors"
#: ``self-stretch``: the drawer is a flex column that does not stretch its
#: children, so without it every entry shrink-wrapped its label and the
#: active one was a 122px pill in a 236px drawer. The artboard's is 212 —
#: the drawer less the 12px margin each side.
NAV_ITEM = "k-nav-item rounded-lg mx-3 px-3 self-stretch cursor-pointer transition-colors"
#: The two pinned entries, which the artboard sets 3px apart and a pixel
#: taller than the group items below them.
NAV_ITEM_PINNED = "k-nav-item--pinned"
NAV_ITEM_ACTIVE = "k-nav-item--active"

PAGE_TITLE = "k-page-title text-[32px] font-light tracking-tight"
#: A progress track. ``PACE_BAR_MONTH`` is the month card's 8px one and
#: ``PACE_BAR_ROW`` the 6px one under a list row (artboard `1c`).
PACE_BAR = "k-pace"
PACE_BAR_MONTH = "k-pace k-pace--month"
PACE_BAR_ROW = "k-pace k-pace--row"
SECTION_CARD = f"{_SURFACE} {_CARD_PAD}"
#: The artboards draw two card paddings, not one: 20px where the card holds
#: a grid or a chart that wants the room, and 22px 24px where it holds type
#: (`2d`'s two mapping cards, `3a`'s two foot cards, `3b`'s physical assets,
#: `3c`'s day sheet, `3e`'s sentence). This is the second — as its own class
#: rather than a `p-` utility, so nothing has to out-specify Tailwind.
SECTION_CARD_WIDE = f"{_SURFACE} k-card-wide"
#: And the third, on the one card a screen is really about: `3a`'s chart,
#: `3b`'s chart, `3d`'s mentor note, `3e`'s result.
SECTION_CARD_FEATURE = f"{_SURFACE} k-card-feature"
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
#: One cell's contents rather than the cell: a category pill, and a date set
#: in mono a size down (artboard `1c`'s last card).
CELL_CHIP = "k-cell-chip"
CELL_DATE = "k-cell-date"

# Dashboard chrome (handoff geometry table): 14px radius and 26/28px padding,
# against 12px / 22-24px on the working screens.
DASH_CARD = f"{_SURFACE} k-dash-card"
CARD_TITLE = "k-card-title"
#: The same title a size down — the two balance-sheet cards on `3b`, where
#: the figure beside it is what the card is for.
CARD_TITLE_SM = "k-card-title k-card-title--sm"
CARD_SUBTITLE = "k-card-subtitle"
#: The same label a size down — a tile's caption, a footer stat's name.
#: Artboard `1c` sets these at 11px against the card subtitle's 12.
CARD_CAPTION = "k-card-caption"
#: The safe-to-spend hero's per-day sentence, and the three labels under its
#: split bar (artboard `1f`).
HERO_RATE = "k-hero-rate"
HERO_LEGEND = "k-hero-legend"
#: A chart key drawn beside a card's title rather than inside the chart: a
#: 9px square for a bar series, a 16x2 rule for a line one (artboard `1c`).
LEGEND_DOT = "k-legend-dot"
LEGEND_LINE = "k-legend-line"

# Ledger toolbar (artboard 2a): a filter is a pill that shows its value, and a
# dashed one when it has none to show.
#: The ledger itself: one paper card holding the header rule, the rows and the
#: pagination bar, which artboard `2a` seals in at the foot rather than
#: leaving loose on the ground.
LEDGER_CARD = "k-ledger-card"
LEDGER_FOOT = "k-ledger-foot"
#: A small select drawn on sunken sand — the page-size picker at the foot of
#: the ledger, which is a number and not a field.
SELECT_SUNKEN = "k-select-sunken"
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
#: The hairline between the count and what you can do with it (artboard `2a`).
SELECTION_DIVIDER = "k-selection-divider"
#: One action on that bar: an icon and a word, at the bar's own weight.
SELECTION_ACTION = "k-selection-action"
#: The one that cannot be undone, in the expense colour.
SELECTION_ACTION_DANGER = "k-selection-action k-selection-action--danger"
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

# ── Budget realization (artboard 2b) ─────────────────────────────────────────
#: One paper card holding the whole table: a header rule, a row per category,
#: a Total row. Five of six columns are figures, so only the name is elastic.
REALIZATION_GRID = "k-realization"
REALIZATION_HEAD = "k-realization-row k-realization-head"
REALIZATION_ROW = "k-realization-row k-realization-body"
#: The month added up, under a rule a shade stronger than the row hairlines.
REALIZATION_TOTAL = "k-realization-row k-realization-total"
#: A parent's name over the rows it owns — a heading, not a row of figures.
REALIZATION_GROUP = "k-realization-group"
#: The line under a pace bar, and a row's parent name: both are asides.
REALIZATION_NOTE = "k-realization-note"
#: A figure with an eyebrow over it and nothing else — the four cards that
#: open `2b`, and the four that open `3a` and `3c`.
STAT_CARD = "k-stat-card"
STAT_CARD_FIGURE = "k-stat-figure"
#: The same card in warm sand rather than paper: one of four that is not a
#: figure to read but a thing to do something about (`3c`'s overdue count).
STAT_CARD_WARM = "k-stat-card k-stat-card--warm"

# ── Budget plan toolbar (artboard 2c) ────────────────────────────────────────
#: One year, as a pill you can switch on. Mono, because it is a figure.
YEAR_CHIP = "k-year-chip"
YEAR_CHIP_ON = "k-year-chip k-year-chip--on"
#: An ink button that is not on a title row: square corners, not round. The
#: title row's pill is the page's one action; this is a control inside it.
BUTTON_INK = "k-btn-ink"
#: Its quiet counterpart: a hairline outline and no fill, for the choice
#: beside it that is not the one being offered.
BUTTON_OUTLINE = "k-btn-outline"
#: A word that acts — "Edit", "Import more". Accent type, no box at all.
LINK_ACTION = "k-link-action"
#: The same ink, full width and a size up — the one button on a login page.
BUTTON_INK_WIDE = "k-btn-ink k-btn-ink--wide"

#: A page's tab row: quiet type on a rule, the tab you are on underlined in
#: ink. Artboard `2b` puts the screen's own controls on the same line.
TABS = "k-tabs"
TAB_ROW = "k-tab-row"

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
#: A step the reader has walked back to. The work is elsewhere — that node
#: keeps the accent — so this one is ringed rather than filled.
STEP_NODE_READING = "k-step--reading"
STEP_LABEL = "k-step-label"
STEP_LABEL_NOW = "k-step-label k-step-label--now"
#: One of the three file formats, as a pill you can switch between.
FORMAT_CHIP = "k-format-chip"
FORMAT_CHIP_ON = "k-format-chip--on"
#: Quasar's uploader, whose header is a solid brand bar by default — the
#: loudest thing on a page whose whole job is the step you are on.
UPLOADER = "k-uploader"
#: A disclosure for what is not a step: a line you open, not a card.
DISCLOSURE = "k-disclosure"
#: "auto" — this column came from detection, not from the user.
AUTO_BADGE = "k-auto-badge"
#: One mapping row: what the importer wants on the left, the column it will
#: read it from on the right (artboard `2d`).
FIELD_ROW = "k-field-row"
FIELD_LABEL = "k-field-label"
#: The picker itself, drawn as a filled field rather than an underline — and
#: in mono, because what it holds is a column out of the file.
FIELD_SELECT = "k-field-select"
#: A picker with nothing in it yet: paper rather than sunken sand, so the
#: mapped rows are the ones that carry weight. A modifier on its own — it is
#: added and removed at runtime, and a removal naming the base class too
#: would take the field's whole shape away with it.
FIELD_SELECT_UNSET = "k-field-select--unset"
#: A hairline across a card, where one card holds two kinds of question.
CARD_RULE = "k-card-rule"
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
#: The same slot with nothing to say: it keeps its height and drops its tint.
ERROR_SLOT_EMPTY = "k-error-slot--empty"
#: A count on that panel: large, mono, and paper-coloured.
AUTH_PANEL_FIGURE = "k-auth-figure"
#: Its label underneath, dimmed against the ink rather than muted on paper.
AUTH_PANEL_LABEL = "k-auth-label"
#: The hairline above those counts, on ink rather than on paper.
AUTH_PANEL_RULE = "k-auth-rule"
#: "Welcome back" — the one line on the page set as a title.
AUTH_TITLE = "k-auth-title"
AUTH_SUBTITLE = "k-auth-subtitle"
#: The eyebrow over a field, which is where artboard `3f` puts a field's
#: name: above it, not floating inside it.
AUTH_FIELD_LABEL = "k-auth-field-label"
#: The field itself: paper in a hairline box, and the box goes ink when the
#: cursor is in it.
AUTH_FIELD = "k-auth-field"
#: The version and licence, at the foot of the form column.
AUTH_FOOT = "k-auth-foot"

# ── Header (artboards 1c / 2a) ────────────────────────────────────────────────
#: "Kaleta" in the header, first thing on the line.
WORDMARK = "k-wordmark"
#: The hairline between the wordmark and the name of the page you are on.
HEADER_DIVIDER = "k-header-divider"
#: That name — quiet type, the header's only statement about where you are
#: now that the drawer marks it too.
HEADER_PAGE = "k-header-page"
#: "Jump to…" — a search field's clothes on a button that opens the palette.
#: Its own breakpoint rather than `hidden md:inline-flex`, for the reason
#: `.k-auth-panel` and `.k-tabbar` have one.
HEADER_SEARCH = "k-header-search"
#: An icon-only header control: the dark toggle, at the artboard's weight
#: rather than Quasar's primary.
HEADER_ICON = "k-header-icon"
#: The account button, drawn as the artboard's 28px initials disc.
AVATAR = "k-avatar"
#: 236px ⇄ 64px. Not on any artboard — the drawer is drawn expanded on the
#: dashboard and mini on the working screens, and one preference is what
#: gets you from one to the other.
MINI_TOGGLE = "k-mini-toggle"

#: The hamburger, and the header's search icon: phone-side controls that a
#: docked drawer and a search pill make redundant.
DRAWER_CONTROLS = "k-drawer-controls"
PHONE_SEARCH = "k-phone-search"

#: The command palette dialog, and one row in it.
PALETTE_CARD = "k-palette"
PALETTE_ROW = "k-palette-row"

#: A button on a page's title row, drawn as artboards `1c` / `2a` draw them:
#: a paper pill with a hairline border, not a flat text button.
TITLE_ACTION = "k-title-action"
#: The one action a screen is for, at the end of the same row: the artboards
#: draw it filled with ink, not with the accent — the accent is reserved for
#: the thing that needs attention, and a "New transaction" button never is.
TITLE_ACTION_PRIMARY = "k-title-action k-title-action--ink"
#: A keyboard hint drawn inside that pill (artboard `2a`'s ⌥N).
KBD_HINT = "k-kbd"
#: The line above a page title: what is on this screen, said in figures.
#: Carries `data-page-eyebrow`, which is how the fidelity shoot finds a page.
PAGE_EYEBROW = "k-eyebrow k-page-eyebrow"
#: Two or three choices where only one can hold: the chosen one on ink, the
#: rest quiet on sunken sand. Artboards `2a` (Group by), `2b` (Flat / By
#: parent), `3a` (horizon and model) and `3e` (chart shape) all draw it.
SEGMENT = "k-segment"
#: A select drawn as a pill rather than a field — the month and year pickers
#: on `2b`, the account picker on `3a`, the "copy into" month on `2c`.
SELECT_PILL = "k-select-pill"
#: The same pill with 8px corners (artboards `2b`, `2c`).
SELECT_PILL_SQUARE = "k-select-pill k-select-pill--square"

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
#: The three letters in the corner of today's cell. Its own class and not
#: the page eyebrow: `3c` draws it a half-pixel smaller and half as tracked
#: as an eyebrow, in the accent rather than in muted, because it marks one
#: cell in a grid of thirty-one rather than heading a section.
CALENDAR_TODAY_MARK = "k-cal-today"
#: One dot per thing happening that day, coloured by which way the money goes.
CALENDAR_DOT = "k-cal-dot"
CALENDAR_DOT_IN = "k-cal-dot--in"
CALENDAR_DOT_OUT = "k-cal-dot--out"
#: Neither in nor out: a transfer between your own accounts, or a projected
#: subscription charge that is not a planned transaction you can post.
CALENDAR_DOT_FLAT = "k-cal-dot--flat"
#: The four figures over the month. Artboard `3c` sets them a size down from
#: `2b`'s — four cards over a grid, not four cards over a table.
STAT_CARD_SM = "k-stat-card--sm"
STAT_FIGURE_SM = "k-stat-figure--sm"
#: Everything already late, on one warm line above the month. It used to hang
#: off the day-1 cell, where it was invisible from any other month.
OVERDUE_STRIP = "k-overdue-strip"
#: Type on a warm card, which takes the banner's burnt ink rather than the
#: page's — the muted grey the paper cards use disappears against sand.
WARM_ACCENT = "k-warm-accent"

# ── Forecast (artboard 3a) ────────────────────────────────────────────────────
#: One key in the chart's legend: a swatch and a word, on the card's title
#: line rather than inside the frame, where it costs the chart no height.
CHART_KEY = "k-chart-key"
#: The four swatch shapes the forecast chart draws with.
CHART_KEY_LINE = "k-chart-key--line"
CHART_KEY_DASH = "k-chart-key--dash"
CHART_KEY_BAND = "k-chart-key--band"
CHART_KEY_DOT = "k-chart-key--dot"
#: The two tables under the chart: a header rule over rows of figures, set as
#: a grid so the columns line up without a table's chrome.
FORECAST_HEAD = "k-forecast-head"
FORECAST_ROW = "k-forecast-row"
#: One late item's words on that strip, and the figure beside them.
OVERDUE_TEXT = "k-overdue-text"
OVERDUE_AMOUNT = "k-overdue-amount"
#: The hairline between two of them.
OVERDUE_RULE = "k-overdue-rule"
#: The day sheet beside the grid, rather than a drawer over it: the artboard
#: reads the month and the day you picked out of it at the same time.
DAY_PANEL = "k-day-panel"
#: One occurrence inside that sheet — a hairline box, not a table row.
DAY_ITEM = "k-day-item"
#: The rule over the sheet's own two buttons.
DAY_PANEL_FOOT = "k-day-panel-foot"
#: A quiet button on sunken sand, beside an ink one (the sheet's foot).
BUTTON_SUNKEN = "k-btn-sunken"

# ── Wizard (artboard 3d) ─────────────────────────────────────────────────────
#: A page section that is not a card: an eyebrow and a note over one rule,
#: with whatever it heads underneath on the ground.
SECTION_RULE = "k-section-rule"
SECTION_RULE_TITLE = "k-section-rule-title"
#: One of the four setup cards — a tick, a name, a count, a way back in.
SETUP_CARD = "k-setup-card"
SETUP_TICK = "k-setup-tick"
#: One routine, as a bare row in a two-column index.
ROUTINE_ROW = "k-routine-row"
#: A routine's one-line description inside that row.
ROUTINE_DESC = "k-routine-desc"
#: The suggestion at the head of the page: an accent rule down its left edge
#: and a lightbulb, because it is the one thing that knows this ledger.
MENTOR_EYEBROW = "k-mentor-eyebrow"

# ── Report builder (artboard 3e) ──────────────────────────────────────────────
#: The field rail: its own column against the drawer, not a card on the page.
REPORT_RAIL = "k-report-rail"
#: An eyebrow inside that rail — tighter tracking than a page eyebrow, because
#: it labels a list two words wide and not a screen.
RAIL_EYEBROW = "k-rail-eyebrow"
#: One draggable field. The chosen one is the only paper in the rail.
RAIL_ROW = "k-rail-row"
RAIL_ROW_ON = "k-rail-row--on"
#: A saved report: a name you click, with no surface of its own.
RAIL_SAVED = "k-rail-saved"
#: One of the five chart-type squares. The chosen one goes ink.
CHART_PICK = "k-chart-pick"
CHART_PICK_ON = "k-chart-pick--on"
#: The rule between the sentence and the controls that qualify it.
SENTENCE_FOOT = "k-sentence-foot"
#: One row of the bar result: name, track, value, share.
REPORT_BAR_ROW = "k-report-bar-row"
REPORT_BAR_TRACK = "k-report-bar-track"
REPORT_BAR_FILL = "k-report-bar-fill"
#: The total beside the result card's title, which is `CARD_TITLE`.
RESULT_TOTAL = "k-result-total"

#: How many steps the bar ramp has. Artboard `3e` shades ten bars with six
#: greens, darkest first — a ranking you can read without a legend.
BAR_RAMP_STEPS = 6


def bar_ramp(rank: int, total: int) -> str:
    """The fill colour for the bar at ``rank`` out of ``total``, darkest first.

    A CSS variable rather than a hex, so the ramp follows the theme: on ink
    the same six steps run the other way and still read as one series.
    """
    step = 1 if total <= 1 else min(BAR_RAMP_STEPS, 1 + rank * BAR_RAMP_STEPS // total)
    return f"var(--k-ramp-{step})"


# ── Net worth (artboard 3b) ──────────────────────────────────────────────────
#: The hero figure, which on this one screen is 60px and sits on the ground
#: rather than on paper: it is the page's subject, not a card's.
NET_WORTH_FIGURE = "k-nw-figure"
NET_WORTH_DECIMALS = "k-nw-decimals"
#: One of the two deltas beside it — a label and a figure, no pill.
DELTA_LABEL = "k-delta-label"
DELTA_FIGURE = "k-delta-figure"
#: The physical-assets list: name, kind, value, and the pencil that edits it.
ASSET_ROW = "k-asset-row"
#: The line that adds one, under a rule of its own.
ASSET_ADD = "k-asset-add"
#: A balance-sheet table: four columns under a header rule, on a card that is
#: already titled, so the columns are an eyebrow and not a heading.
SHEET_HEAD = "k-sheet-head"
SHEET_ROW = "k-sheet-row"
#: An aside inside a card — the personal-loans note under the liabilities.
CARD_NOTE = "k-card-note"

# ── Balance-sheet bar (artboard 3b) ───────────────────────────────────────────
#: One bar, three segments: held, owned, owed. The shape of the sheet, which a
#: net figure cannot show — 10 000 owned outright and 200 000 against 190 000
#: owed are the same number and not the same position.
SPLIT_BAR = "k-split"
#: The safe-to-spend hero's own weight (artboard `1f`): 9px on a 5px radius.
SPLIT_BAR_HERO = "k-split k-split--hero"

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
#: One step in from the ink: a figure that is not the row's subject.
INK_2 = "k-ink-2"

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
  /* Two warm sands, because the artboards draw two: `2a` tints the selection
     bar #EFE3D6, while `2d`'s unparseable-rows note and `3c`'s Overdue card
     and strip are a step lighter. */
  --k-surface-notice:#F4E9DC;
  --k-ink:#1C1A15;
  --k-ink-2:#4A443A;
  --k-muted:#6B6353;
  --k-muted-strong:#6E6656;
  --k-disabled:#B5AB96;
  --k-hairline:#EDE7DA;
  /* A divider that is meant to be read — a band's rule on the phone, the
     separators in the mini drawer. A step down from a card's hairline and a
     step up from the border a control is drawn with; eleven artboards use
     it. */
  --k-band:#EFCDB2;
  --k-warm-ink:#4A2A0F;
  --k-warm-rule:#DDCBB4;
  --k-ramp-1:#36684D;
  --k-ramp-2:#4A8064;
  --k-ramp-3:#5E9377;
  --k-ramp-4:#77A78C;
  --k-ramp-5:#8FB8A1;
  --k-ramp-6:#A8C8B6;
  --k-rule:#DCD4C2;
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
  /* What is owned outright, beside what is held: the income colour with the
     ground mixed into it, so the two read as one side of the sheet. */
  --k-asset-soft:#8FA893;

  --k-row-hover:#FAF4E9;
  --k-plan-now:#F0E5D4;
  --k-chip-dash:#CFC5AE;
  --k-field-border:#D6C6B2;
  --k-card-shadow:0 1px 2px rgba(28,26,21,.05);
  --k-on-accent:#FCFAF6;
  /* The pill on the accent banner: paper with deep accent ink in light,
     ink with paper on it in dark. Neither pair is any other token's. */
  --k-banner-btn-ink:#8E4718;
  /* A failed login, as artboard `3f` draws it: a warm pink strip with its
     own ink. Neither is any other token's — the expense colour is for
     figures, and this is a sentence about the page. */
  --k-error-soft:#F6E2DC;
  --k-error-ink:#8A3826;
  /* On the ink panel: a rule that reads on ink, and the caption colour under
     a figure there. The paper tokens are all defined against paper. */
  --k-ink-rule:#3A362C;
  --k-on-ink-muted:#B0A692
}
.body--dark{
  --q-primary:#E8935B;
  --q-info:#E8935B;

  --k-ground:#171613;
  --k-surface:#201F1A;
  --k-surface-sunken:#2A2822;
  --k-surface-warm:#262420;
  --k-surface-warm-strong:var(--k-surface-sunken);
  --k-surface-notice:#332B22;
  --k-ink:#F0EBDF;
  --k-ink-2:#CFC7B6;
  --k-muted:#A8A08D;
  --k-muted-strong:#A19781;
  --k-disabled:#6E6656;
  --k-hairline:#2A2822;
  --k-band:rgba(232,147,91,.22);
  --k-warm-ink:#EBD9C4;
  --k-warm-rule:#4A4237;
  --k-ramp-1:#4E8567;
  --k-ramp-2:#5E9377;
  --k-ramp-3:#6EA184;
  --k-ramp-4:#7EAF92;
  --k-ramp-5:#8EBD9F;
  --k-ramp-6:#9ECBAD;
  --k-rule:#3D392F;
  --k-border:#322F27;
  --k-border-strong:#453F34;
  --k-accent:#E8935B;
  --k-accent-soft:#3A2E24;
  --k-accent-text:#E8935B;
  --k-accent-light:#E8935B;
  --k-income:#6FAF87;
  --k-expense:#DE8672;
  --k-warning:#E3B457;
  --k-asset-soft:#5E7C67;

  --k-row-hover:#262420;
  --k-plan-now:#332F26;
  --k-chip-dash:#453F34;
  --k-field-border:#4A4437;
  --k-card-shadow:none;
  --k-on-accent:#241C13;
  --k-banner-btn-ink:#F0EBDF;
  --k-error-soft:#3A2622;
  --k-error-ink:#DE8672;
  --k-ink-rule:#3A362C;
  --k-on-ink-muted:#B0A692
}
body,.q-body--layout{
  font-family:'Libre Franklin',ui-sans-serif,system-ui,sans-serif
}
/* Every artboard draws its icons outlined; Quasar's default `material-icons`
   is the filled face, and a filled 19px glyph beside 13px type is a blob.
   NiceGUI already self-hosts all four Google styles, so this is a family
   swap and not another font to fetch — one rule rather than an `o_` prefix
   on several hundred `ui.icon` calls, which would also leave whichever were
   missed filled. */
.q-icon.material-icons{font-family:'Material Icons Outlined'}
body{background-color:var(--k-ground);color:var(--k-ink)}
.k-ground{background-color:var(--k-ground)}

/* ── Surfaces & shell ─────────────────────────────────────────────── */
.k-surface{background:var(--k-surface);box-shadow:var(--k-card-shadow)}
.k-card-wide{padding:22px 24px}
.k-card-feature{padding:24px 26px}
.k-header{
  background:var(--k-surface);
  color:var(--k-ink);
  border-bottom:1px solid var(--k-border)
}
/* Quasar paints its own white on these; make them read the tokens so a
   plain ui.card() is paper on ground without every view opting in. */
.q-card{background:var(--k-surface);color:var(--k-ink)}
.q-tab-panels,.q-tab-panel{background-color:transparent}
/* `.k-drawer` lands on Quasar's `.q-drawer__content`, which is the element
   that fills the aside — so the ground and the hairline go here, and so does
   the artboard's 22/24 padding, which has to out-specify NiceGUI's own
   `.nicegui-drawer{padding:1rem}`. */
.q-drawer__content.k-drawer{
  background:var(--k-ground);
  border-right:1px solid var(--k-border);
  padding:22px 0 24px
}
/* NiceGUI pads `.nicegui-content` with 1rem and gaps it; the dashboard sets
   its own 36/40/44 and 28 from artboard `1c`, and two paddings is neither. */
.nicegui-content:has(> .k-dash-page){padding:0;gap:0}

/* ── Navigation — a quiet index, no per-item boxes ────────────────── */
/* The group eyebrows are the artboard's own spacing: 20px above the word,
   6px under it, and no box of their own. The chevron they carry is not on
   the artboard — collapsing a group is behaviour a still picture cannot
   draw — so the hover moves the ink rather than painting a band. */
.k-nav-group{
  font-size:10px;
  font-weight:600;
  letter-spacing:.18em;
  text-transform:uppercase;
  color:var(--k-muted-strong)
}
.k-nav-row{padding:20px 24px 6px}
.k-nav-row:hover .k-nav-group{color:var(--k-ink)}
/* 44px is the phone's tap target, where the drawer is an overlay behind
   "More"; the docked desktop drawer is the artboard's 19px icon in 8px of
   padding, and 16 entries at 44px do not fit a 900px window. */
/* `flex:none`: the two pinned entries are direct children of the drawer's
   flex column, and sixteen entries overflow an 840px one. Without it they
   are the rows that shrink — to 16px, the moment the desktop rule takes the
   minimum height away and leaves the padding to set it. */
.k-nav-item{color:var(--k-ink-2);min-height:44px;flex:none}
.k-nav-item--pinned{margin-bottom:3px}
/* On a desktop the padding is what sets the row height, as artboard `1c`
   writes it: 7px inside a group, 8px for the two pinned entries above them.
   The 44px floor is the phone's tap target and stays below the breakpoint. */
@media (min-width:768px){
  .k-nav-item{min-height:0;padding-top:7px;padding-bottom:7px}
  .k-nav-item--pinned{padding-top:8px;padding-bottom:8px}
}
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
/* The artboard lifts this one row a hundredth harder than a card
   (`rgba(28,26,21,.06)` against the `--k-card-shadow` token's .05), so it
   carries the value rather than the token. Dark drops it, as every paper
   surface does there. */
.k-nav-item--active{background:var(--k-surface);box-shadow:0 1px 2px rgba(28,26,21,.06)}
.body--dark .k-nav-item--active{box-shadow:none}
.k-nav-item--active .q-item__label{color:var(--k-ink);font-weight:600}
.k-nav-item--active .q-icon{color:var(--k-accent-text)!important}
.k-app-version{color:var(--k-muted);padding:24px 24px 0;font-size:11px}

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
/* One step in from the ink, for a figure that is not the row's subject. */
.k-ink-2{color:var(--k-ink-2)}
.k-muted-strong{color:var(--k-muted-strong)}
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
/* Hairlines, not Quasar's grey: the header rule is a shade stronger than
   the row rules, which is how artboard `1c` separates the two. */
.k-table .q-table th{border-bottom:1px solid var(--k-border)}
.k-table .q-table td{border-bottom:1px solid var(--k-hairline)}
.k-table .q-table tbody tr:last-child td{border-bottom:none}
.k-table .q-table tbody tr:hover{background:var(--k-row-hover)}
/* ── Budget realization (artboard 2b) ─────────────────────────────── */
.k-realization{
  background:var(--k-surface);
  box-shadow:var(--k-card-shadow);
  border-radius:12px;
  padding:6px 0;
  width:100%
}
.k-realization-row{
  display:grid;
  grid-template-columns:1.7fr 118px 118px 118px 78px 200px;
  align-items:center;
  padding:13px 22px;
  font-size:13.5px;
  color:var(--k-ink);
  border-bottom:1px solid var(--k-hairline)
}
.k-realization-head{
  padding:12px 22px;
  font-size:10px;
  font-weight:600;
  letter-spacing:.14em;
  text-transform:uppercase;
  color:var(--k-muted-strong);
  border-bottom:1px solid var(--k-border)
}
/* The Total sits under the stronger rule, so it reads as a summary and not
   as one more category. */
.k-realization-total{
  padding:14px 22px;
  font-weight:600;
  border-bottom:none;
  border-top:1px solid var(--k-border)
}
.k-realization-group{padding:14px 22px 4px}
.k-realization-note{font-size:10.5px;color:var(--k-muted)}
/* One figure under an eyebrow (artboards `2b`, `3a`, `3c`). No icon, no
   trend line: four of these across a page are the page's opening sentence,
   and anything else in them is a second one. */
.k-stat-card{
  background:var(--k-surface);
  box-shadow:var(--k-card-shadow);
  border-radius:12px;
  padding:20px 22px;
  flex:1;
  min-width:0
}
.k-stat-card--warm{background:var(--k-surface-notice);box-shadow:none}
.k-stat-card--sm{padding:18px 20px}
.k-stat-figure{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:28px;
  font-weight:500;
  line-height:1.15;
  color:var(--k-ink);
  margin-top:6px
}
.k-stat-figure--sm{font-size:24px;margin-top:5px}
/* A page's tabs: a rule across the row, the tab you are on underlined in ink
   rather than sitting in a grey box. Quasar's indicator is turned off in the
   props; this draws the artboard's 2px one on the tab itself. */
.k-tab-row{border-bottom:1px solid var(--k-rule)}
.k-tabs{min-height:0}
.k-tabs .q-tab{
  min-height:0;
  padding:0 2px 12px;
  margin-right:26px;
  font-size:13.5px;
  font-weight:400;
  color:var(--k-muted)
}
.k-tabs .q-tab__content{min-width:0;padding:0;gap:8px;flex-direction:row}
.k-tabs .q-tab__icon{font-size:18px;margin:0}
.k-tabs .q-tab__label{font-size:13.5px;line-height:1}
.k-tabs .q-tab--active{color:var(--k-ink);font-weight:600}
.k-tabs .q-tab--active:after{
  content:"";
  position:absolute;
  left:0;right:0;bottom:-1px;
  height:2px;
  background:var(--k-ink)
}
.k-tabs .q-focus-helper,.k-tabs .q-tab__indicator{display:none}
/* A category, as a pill — the ledger's own chip, borrowed by the dashboard's
   last card. Hairline is the fill artboards `1c` and `2a` both draw it in:
   a shade under the page, so the pill reads as a label and not a button. */
.k-cell-chip{
  background:var(--k-hairline);
  border-radius:999px;
  color:var(--k-ink-2);
  font-size:11.5px;
  padding:3px 9px
}
/* A date in a dense table: mono, muted, and a size down from the row. */
.k-cell-date{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;
  color:var(--k-muted)
}
/* The working screens' page column (artboards `2a`-`3e`). NiceGUI's own
   `.nicegui-content` padding is zeroed the same way the dashboard zeroes it,
   or the two stack and every column starts 16px in from where it should. */
.k-page{padding:32px 36px 40px;gap:20px}
.k-page--gap-22{gap:22px}
.k-page--gap-24{gap:24px}
.k-page--tight{padding-left:32px;padding-right:32px}
.k-page--roomy{padding:36px 40px 44px;gap:28px}
.k-page--roomy.k-page--gap-26{gap:26px}
/* Artboard `3e`: the field rail is a column against the drawer, not a card
   on the page, so the page itself carries no padding and lies on its side. */
.k-page--flush{padding:0;gap:0;flex-direction:row;align-items:stretch}
@media (max-width:767.98px){.k-page,.k-page--roomy{padding:20px 20px 28px;gap:20px}}
.nicegui-content:has(> .k-page){padding:0;gap:0}
/* 6px under the eyebrow, which is the artboards' own measure between it and
   the title it labels. */
.k-page-eyebrow{margin-bottom:6px}
.k-dash-page{padding:36px 40px 44px;gap:28px}
/* 767.98px, not 768px: the tab bar and the server-side layout choice both
   put a 768px-wide window (an iPad in portrait) on the desktop side, and a
   desktop grid with phone padding is neither. */
@media (max-width:767.98px){.k-dash-page{padding:20px 20px 28px;gap:28px}}
.k-dash-card{border-radius:14px;padding:26px 28px}
/* 16/18 below the breakpoint, where artboard `1f` tightens the same card for
   a 390px page. */
@media (max-width:767.98px){.k-dash-card{padding:16px 18px}}
.k-account-chip{background:var(--k-surface-sunken)}
/* Hairline above a card's slow figures (month card footer, artboard 1c). */
.k-card-footer{border-top:1px solid var(--k-hairline)}
.k-card-title{
  font-size:17px;
  font-weight:500;
  color:var(--k-ink);
  line-height:1.3
}
.k-card-title--sm{font-size:16px}
.k-card-subtitle{font-size:12px;color:var(--k-muted);line-height:1.4}
.k-card-caption{font-size:11px;color:var(--k-muted);line-height:1.4}
/* The hero's two supporting lines (artboard `1f`): the sentence under the
   figure, set in ink-2 with room to breathe, and the three segment labels
   spread across the bar in muted 11px. */
.k-hero-rate{font-size:13px;line-height:1.55;color:var(--k-ink-2)}
.k-hero-legend{font-size:11px;color:var(--k-muted)}
.k-legend-dot{width:9px;height:9px;border-radius:2px;flex:none}
.k-legend-line{width:16px;height:2px;flex:none}
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
  color:var(--k-muted-strong)
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
/* Walked back to: the work is on another node, so this one is ringed and
   not filled — two filled discs would be two claims about where you are. */
.k-step--reading{
  border-color:var(--k-accent);
  color:var(--k-accent-text);
  box-shadow:0 0 0 3px var(--k-accent-soft)
}
.q-btn.k-format-chip{
  border:1px solid var(--k-border);
  border-radius:999px;
  color:var(--k-muted-strong);
  min-height:38px;
  padding:0 16px
}
.q-btn.k-format-chip:hover{background:var(--k-surface-warm)}
.q-btn.k-format-chip.k-format-chip--on{
  border-color:var(--k-accent);
  background:var(--k-accent-soft);
  color:var(--k-accent-text)
}
.k-disclosure > .q-expansion-item__container > .q-item{
  background:transparent;
  border-radius:10px;
  color:var(--k-ink-2);
  min-height:44px
}
.k-disclosure > .q-expansion-item__container > .q-item:hover{background:var(--k-surface-warm)}
/* The drop zone is a zone, not a banner: Quasar paints its header with the
   brand colour, which on this page shouted over the step itself. */
.k-uploader .q-uploader__header{
  background:var(--k-surface-warm);
  color:var(--k-muted-strong)
}
.k-uploader{
  border:1px dashed var(--k-border-strong);
  border-radius:12px;
  box-shadow:none;
  background:var(--k-surface)
}
.k-uploader .q-uploader__list{background:var(--k-surface)}
.k-step-label{font-size:11px;color:var(--k-muted);text-align:center;line-height:1.2}
.k-step-label--now{color:var(--k-ink);font-weight:600}
/* Artboard `2d` writes it as quiet type inside the box, not as a badge on
   its rim: `align-self:flex-start` in Quasar's append slot pushed the pill
   up onto the field's own border, where it read as a stray chip. */
.k-auto-badge{
  align-self:center;
  font-size:9.5px;
  font-weight:600;
  letter-spacing:.06em;
  text-transform:uppercase;
  color:var(--k-muted-strong);
  padding:0 2px;
  line-height:15px
}
/* The line kept for a failed login. It is a strip, not a sentence: artboard
   `3f` draws a tinted box with an icon, and an empty one still holds its
   place so the button never moves out from under a second attempt. */
.k-error-slot{
  display:flex;align-items:center;gap:9px;
  min-height:42px;padding:11px 13px;border-radius:8px;
  font-size:12.5px;line-height:1.3;
  color:var(--k-error-ink);
  background:var(--k-error-soft)
}
.k-error-slot .q-icon{font-size:17px;color:var(--k-error-ink)}
/* Nothing to say: the strip keeps its height and shows none of its clothes. */
.k-error-slot--empty{background:transparent}
.k-error-slot--empty .q-icon{display:none}

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
  font-size:22px;line-height:1.1;font-weight:400;color:var(--k-ground)
}
/* Lowercase, and quiet: on ink the label is a caption under a figure, not a
   heading over one, so it takes neither caps nor letter-spacing. */
.k-auth-label{font-size:11px;color:var(--k-on-ink-muted)}
.k-auth-rule{border-top:1px solid var(--k-ink-rule);padding-top:22px;margin-top:26px}
.k-auth-title{
  font-size:30px;font-weight:300;line-height:1.2;
  letter-spacing:-.02em;color:var(--k-ink)
}
.k-auth-subtitle{font-size:13.5px;line-height:1.6;color:var(--k-ink-2);max-width:340px}
.k-auth-field-label{
  font-size:10px;font-weight:600;letter-spacing:.16em;
  text-transform:uppercase;color:var(--k-muted-strong);margin-bottom:7px
}
.k-auth-field .q-field__control{
  background:var(--k-surface);
  border:1px solid var(--k-field-border);
  border-radius:9px;
  min-height:48px;
  padding:0 14px
}
.k-auth-field .q-field__control:before,
.k-auth-field .q-field__control:after{display:none}
.k-auth-field .q-field__native{font-size:14px;color:var(--k-ink);padding:0}
/* A masked password is a row of marks, not words: mono and spaced, as
   artboard `3f` sets it, so the count of what you typed is readable. */
.k-auth-field input[type="password"]{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  letter-spacing:.12em
}
.k-auth-field .q-field__marginal,.k-auth-field .q-field__append{
  height:48px;color:var(--k-muted);font-size:19px
}
/* The field the cursor is in takes an ink outline rather than the accent
   ring Quasar draws: the accent on this page is the wordmark alone. */
.k-auth-field .q-field--focused .q-field__control,
.k-auth-field.q-field--focused .q-field__control{
  border:1.5px solid var(--k-ink);
  padding:0 13.5px
}
.k-auth-foot{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:11.5px;color:var(--k-muted)
}

/* Payment calendar (artboard 3c) — the grid is 31 small cells, so every
   pixel of border and padding is charged 31 times. */
.k-cal-today{
  font-weight:600;
  font-size:8.5px;
  letter-spacing:.1em;
  text-transform:uppercase;
  color:var(--k-accent-text)
}
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
.k-overdue-strip{
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;
  padding:12px 18px;
  background:var(--k-surface-notice);
  border-radius:10px
}
.k-overdue-strip .q-icon{color:var(--k-banner-btn-ink)}
.k-warm-accent{color:var(--k-banner-btn-ink)}

/* ── Forecast (artboard 3a) ───────────────────────────────────────── */
.k-chart-key{
  display:flex;align-items:center;gap:6px;
  font-size:11.5px;color:var(--k-muted)
}
.k-chart-key::before{content:"";display:block;width:16px;flex:none}
.k-chart-key--line::before{height:2px;background:var(--k-ink)}
.k-chart-key--dash::before{height:0;border-top:2px dashed var(--k-accent)}
.k-chart-key--band::before{width:12px;height:9px;background:var(--k-band)}
.k-chart-key--dot::before{height:0;border-top:1.5px dotted var(--k-muted)}
.k-forecast-head{
  display:grid;align-items:center;
  font-size:10px;font-weight:600;letter-spacing:.14em;
  text-transform:uppercase;color:var(--k-muted-strong);
  padding-bottom:9px;
  border-bottom:1px solid var(--k-border)
}
.k-forecast-row{
  display:grid;align-items:center;
  font-size:12.5px;
  padding:9px 0;
  border-bottom:1px solid var(--k-hairline)
}
.k-forecast-row:last-child{border-bottom:0}
.k-forecast-head > *,.k-forecast-row > *{min-width:0;overflow:hidden;text-overflow:ellipsis}
/* `minmax(0, …)`, not a bare `fr`: an auto-sized track takes its minimum
   from its content, so a long category name widened its own row's columns
   and every figure in the card landed at a different x. */
.k-cols-upcoming{
  grid-template-columns:88px minmax(0,1fr) minmax(0,1fr) minmax(0,1fr);gap:10px
}
.k-cols-planned{
  grid-template-columns:80px minmax(0,1fr) minmax(0,1fr) 118px;gap:10px
}
.k-overdue-text{font-size:12.5px;font-weight:500;color:var(--k-warm-ink)}
.k-overdue-amount{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:12.5px;font-weight:500;color:var(--k-expense)
}
.k-overdue-rule{width:1px;height:16px;background:var(--k-warm-rule);flex:none}
.k-day-panel{width:400px;flex:none}
.k-day-item{
  display:flex;align-items:center;gap:12px;
  border:1px solid var(--k-border);
  border-radius:9px;
  padding:12px 14px
}
.k-day-panel-foot{margin-top:22px;padding-top:18px;border-top:1px solid var(--k-hairline)}
.q-btn.k-btn-sunken{
  background:var(--k-surface-sunken);
  border-radius:8px;
  color:var(--k-ink-2);
  font-size:12.5px;font-weight:600;letter-spacing:0;
  min-height:38px
}

/* Balance-sheet bar (artboard 3b) — segments meet with no gap, so their
   widths are the only thing saying how big each side is. */
.k-split{
  display:flex;align-items:stretch;gap:0;
  height:12px;border-radius:6px;overflow:hidden;
  background:var(--k-border)
}
/* The safe-to-spend track, at the weight artboard `1f` draws it. */
.k-split--hero{height:9px;border-radius:5px}
.k-split-seg{height:100%}
/* A square, not a disc, and the size of a chart key — the legend under the
   bar is read as a key to it (artboard `3b`). */
.k-split-dot{width:9px;height:9px;border-radius:2px;flex:none}
/* What is held is the income colour, what is owned a muted green beside it,
   what is owed the expense colour: the bar is the sheet, and the sheet has
   two sides. */
/* `--ink` is the dashboard hero's committed share and is ink, as `1c`
   draws it. `3b`'s balance-sheet bar wanted a green and a soft green for
   its two kinds of asset, which is what `--asset` and `--asset-soft` are:
   two tones of their own rather than a repaint of a tone another screen
   is already using. */
.k-split--ink{background:var(--k-ink)}
.k-split--asset{background:var(--k-income)}
.k-split--asset-soft{background:var(--k-asset-soft)}
.k-split--owed{background:var(--k-expense)}
/* Safe-to-spend (artboard 1f): what is promised, what is gone, what is left. */
.k-split--spent{background:var(--k-neutral-bar)}
.k-split--free{background:var(--k-accent-light)}

/* ── Wizard (artboard 3d) ─────────────────────────────────────────── */
.k-section-rule{
  display:flex;align-items:baseline;gap:12px;
  padding-bottom:14px;
  border-bottom:1px solid var(--k-rule);
  width:100%
}
.k-section-rule-title{
  font-size:10px;font-weight:600;letter-spacing:.22em;
  text-transform:uppercase;color:var(--k-ink)
}
.k-setup-card{
  background:var(--k-surface);
  box-shadow:var(--k-card-shadow);
  border-radius:12px;
  padding:18px 20px
}
.k-setup-tick{
  display:inline-flex;align-items:center;justify-content:center;
  width:20px;height:20px;border-radius:999px;
  background:var(--k-income);color:var(--k-surface);flex:none
}
.k-setup-tick--todo{background:var(--k-border-strong)}
.k-setup-tick .q-icon{font-size:14px;color:var(--k-surface)}
.k-routine-row{
  display:flex;align-items:center;gap:14px;
  padding:15px 0;
  border-bottom:1px solid var(--k-hairline)
}
/* One line, and the whole sentence on the row's tooltip. Artboard `3d`
   reads the index at a glance: a two-line paragraph per row turns thirteen
   rows into a page you have to read rather than scan. */
.k-routine-desc{
  font-size:11.5px;color:var(--k-muted);margin-top:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%
}
.k-mentor-eyebrow{
  font-size:10px;font-weight:600;letter-spacing:.2em;
  text-transform:uppercase;color:var(--k-banner-btn-ink)
}

/* ── Report builder (artboard 3e) ─────────────────────────────────── */
.k-report-rail{
  width:214px;flex:none;align-self:stretch;
  background:var(--k-ground);
  border-right:1px solid var(--k-border);
  padding:26px 18px
}
.k-rail-eyebrow{
  font-size:10px;font-weight:600;letter-spacing:.16em;
  text-transform:uppercase;color:var(--k-muted-strong)
}
.k-rail-row{
  display:flex;align-items:center;gap:9px;width:100%;
  padding:7px 10px;border-radius:7px;
  font-size:12.5px;color:var(--k-ink-2);
  cursor:pointer;flex-wrap:nowrap
}
.k-rail-row:hover{background:var(--k-surface-warm)}
.k-rail-row--on{
  background:var(--k-surface);
  box-shadow:var(--k-card-shadow);
  font-weight:500;color:var(--k-ink)
}
.k-rail-saved{
  display:flex;align-items:center;gap:8px;
  font-size:12.5px;color:var(--k-ink-2);cursor:pointer
}
.k-chart-pick{
  display:flex;align-items:center;justify-content:center;
  width:34px;height:34px;min-height:34px;padding:0;
  border:1px solid var(--k-border-strong);border-radius:8px;
  background:transparent;color:var(--k-ink-2)
}
.k-chart-pick--on{
  background:var(--k-ink);border-color:var(--k-ink);color:var(--k-ground)
}
.k-sentence-foot{
  margin-top:18px;padding-top:16px;
  border-top:1px solid var(--k-hairline)
}
.k-report-bar-row{
  display:grid;grid-template-columns:196px 1fr 108px 62px;
  align-items:center;gap:14px
}
.k-report-bar-track{
  height:22px;border-radius:3px;background:var(--k-hairline);overflow:hidden
}
.k-report-bar-fill{display:block;height:100%;border-radius:3px}
.k-result-total{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:12.5px;color:var(--k-muted)
}

/* ── Net worth (artboard 3b) ──────────────────────────────────────── */
.k-nw-figure{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:60px;line-height:1;font-weight:400;letter-spacing:-.04em
}
.k-nw-decimals{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:22px;color:var(--k-muted-strong)
}
.k-delta-label{font-size:12px;color:var(--k-muted)}
.k-delta-figure{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;
  font-size:14px;font-weight:500
}
.k-asset-row{
  display:grid;
  grid-template-columns:1fr 96px 108px 56px;
  align-items:center;
  padding:9px 0;
  font-size:13px;
  color:var(--k-ink);
  border-bottom:1px solid var(--k-hairline)
}
.k-asset-add{
  border-top:1px solid var(--k-hairline);
  margin-top:14px;padding-top:14px
}
.q-btn.k-asset-add-btn{
  font-size:12.5px;font-weight:500;letter-spacing:0;
  color:var(--k-accent-text);padding:0;min-height:0
}
.q-btn.k-asset-add-btn .q-icon{font-size:16px;color:inherit}
.k-sheet-head,.k-sheet-row{
  display:grid;
  grid-template-columns:1fr 92px 1fr 132px;
  align-items:center
}
.k-sheet-head{
  padding-bottom:9px;
  border-bottom:1px solid var(--k-border);
  font-size:10px;font-weight:600;letter-spacing:.14em;
  text-transform:uppercase;color:var(--k-muted-strong)
}
.k-sheet-row{
  padding:9px 0;
  font-size:13px;color:var(--k-ink);
  border-bottom:1px solid var(--k-hairline)
}
.k-sheet-row:last-of-type{border-bottom:none}
.k-card-note{
  display:flex;align-items:flex-start;gap:9px;
  background:var(--k-surface-sunken);
  border-radius:8px;
  padding:11px 13px;
  font-size:12px;color:var(--k-ink-2)
}

/* Header (artboards 1c / 2a) — 60px of paper: the wordmark, a hairline, the
   page you are on, then the search pill, the dark toggle and the avatar.
   `.k-header-search` carries its own breakpoint: on a phone the pill would
   be a wide "Jump to…" field beside the `.k-phone-search` icon that opens
   the same dialog. */
.k-header{gap:20px}
.k-header-divider{
  width:1px;
  height:20px;
  flex:none;
  background:var(--k-border)
}
.k-header-page{font-size:13px;color:var(--k-muted)}
/* Artboard `1f`'s phone header is the wordmark, a search icon and the
   avatar. The divider and the page name are the wide window's; kept on a
   390px line they pushed the avatar onto a second row, which a header fixed
   at 60px shows by dropping it over the page. The page title is the next
   thing down the page anyway. */
@media (max-width:767.98px){
  .k-header-divider,.k-header-page{display:none}
}
/* `.q-btn.k-*`, two classes: NiceGUI gives every button `color=primary`, and
   a single-class rule loses to Quasar's `.text-primary` — the same trick
   `.q-skeleton.k-skeleton` uses, and for the same reason. */
.q-btn.k-header-search{
  /* The ground, not sunken sand: the two are one colour in light, and in
     dark `1d` fills the pill with the page behind the header, not with the
     lighter grey `--k-surface-sunken` carries. */
  background:var(--k-ground);
  border-radius:999px;
  color:var(--k-muted);
  font-size:12.5px;
  font-weight:400;
  letter-spacing:0;
  min-height:28px;
  padding:0 12px
}
.q-btn.k-header-search .q-icon{font-size:16px}
.q-btn.k-header-search:hover{background:var(--k-surface-sunken)}
.q-btn.k-header-icon{color:var(--k-muted)}
.q-btn.k-header-icon .q-icon{font-size:20px}
.q-btn.k-avatar{
  background:var(--k-accent-light);
  border-radius:999px;
  color:#241C13;
  font-size:11.5px;
  font-weight:600;
  letter-spacing:0;
  min-height:28px;
  min-width:28px;
  width:28px;
  height:28px;
  padding:0
}
.q-btn.k-header-search,.q-btn.k-mini-toggle{display:none}
@media (min-width:768px){
  .q-btn.k-header-search{display:inline-flex}
  .q-btn.k-mini-toggle{display:inline-flex}
}
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

/* A title-row action (artboards 1c / 2a): paper, hairline, fully round. */
.q-btn.k-title-action{
  background:var(--k-surface);
  border:1px solid var(--k-border);
  border-radius:999px;
  color:var(--k-ink-2);
  font-size:12.5px;
  font-weight:500;
  letter-spacing:0;
  min-height:36px;
  padding:0 14px
}
.q-btn.k-title-action .q-icon{color:var(--k-muted);font-size:17px}
.q-btn.k-title-action:hover{background:var(--k-surface-warm)}
/* The primary pill on the same row: ink, and paper type on it. Dark mode
   inverts — ink there is the page, so the pill takes the paper surface and
   the ink text, which is the same relationship the other way up. */
.q-btn.k-title-action--ink{
  background:var(--k-ink);
  border-color:var(--k-ink);
  color:var(--k-ground);
  font-weight:600
}
.q-btn.k-title-action--ink .q-icon{color:var(--k-ground)}
.q-btn.k-title-action--ink:hover{background:var(--k-ink-2)}
.body--dark .q-btn.k-title-action--ink{background:var(--k-ink);color:var(--k-ground)}
/* A key cap inside that pill: mono, a hairline box, and dimmed against the
   ink it sits on — it is a hint, not the button's label. */
.k-kbd{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:10.5px;
  line-height:1.3;
  color:var(--k-disabled);
  border:1px solid var(--k-ink-2);
  border-radius:4px;
  padding:1px 5px
}
/* A segmented control. Quasar paints the chosen option with `.bg-primary`
   and `.text-<toggle-text-color>`, both `!important` and both unbeatable by
   a rule of our own — so the brand variables those two classes read are
   redefined here instead, for this control only. The artboards fill the
   chosen option with ink, not with the accent: the accent means "look at
   this", and which of three groupings you picked never does. */
.k-segment{
  --q-primary:var(--k-ink);
  --q-info:var(--k-ground);
  background:var(--k-surface-sunken);
  border-radius:8px;
  padding:2px
}
.k-segment .q-btn{
  border-radius:6px;
  font-size:12px;
  font-weight:400;
  letter-spacing:0;
  min-height:26px;
  padding:0 12px;
  color:var(--k-ink-2)
}
.k-segment .q-btn.bg-primary{font-weight:500}
/* A select wearing a pill instead of a field: paper, a hairline, and the
   chevron in muted — the artboards never draw an underline on these. */
.k-select-pill .q-field__control{
  background:var(--k-surface);
  border:1px solid var(--k-border);
  border-radius:999px;
  min-height:32px;
  padding:0 12px
}
.k-select-pill .q-field__control:before,
.k-select-pill .q-field__control:after{display:none}
.k-select-pill .q-field__native{
  font-size:12.5px;
  color:var(--k-ink-2);
  min-height:32px;
  padding:0
}
.k-select-pill .q-field__append{color:var(--k-muted);padding-left:4px;font-size:15px}
.k-select-pill .q-field__marginal{height:32px}
/* A year, as a pill: mono at 12px, a dashed-hairline outline when it is off
   and filled with ink when it is on (artboard `2c`). */
.q-btn.k-year-chip{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;
  font-weight:400;
  letter-spacing:0;
  border:1px solid var(--k-chip-dash);
  border-radius:999px;
  color:var(--k-muted);
  min-height:28px;
  padding:0 13px
}
.q-btn.k-year-chip--on{
  background:var(--k-ink);
  border-color:var(--k-ink);
  color:var(--k-ground);
  font-weight:500
}
/* An ink button inside a page rather than on its title row: 8px corners, so
   it sits with the square controls beside it instead of with the title. */
.q-btn.k-btn-ink{
  background:var(--k-ink);
  color:var(--k-ground);
  border-radius:8px;
  font-size:12px;
  font-weight:600;
  letter-spacing:0;
  min-height:30px;
  padding:0 14px
}
.q-btn.k-btn-ink .q-icon{color:var(--k-ground);font-size:15px}
.q-btn.k-btn-ink:hover{background:var(--k-ink-2)}
.q-btn.k-btn-ink--wide{border-radius:9px;font-size:13.5px;padding:13px 0}
.q-btn.k-btn-outline{
  border:1px solid var(--k-chip-dash);
  border-radius:8px;
  font-size:12.5px;font-weight:500;letter-spacing:0;
  color:var(--k-ink-2);
  min-height:30px;padding:0 14px
}
.q-btn.k-link-action{
  font-size:12px;font-weight:500;letter-spacing:0;
  color:var(--k-accent-text);
  padding:0;min-height:0
}
/* The same control with corners: artboards `2b` and `2c` set their month and
   year pickers on an 8px radius, where `3a`'s account picker is fully round.
   A picker beside a table is squarer than one beside a chart. */
.k-select-pill--square .q-field__control{border-radius:8px}

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

/* A band heading, as artboard `1f` sets one: ink rather than muted, and a
   hairline under it. It is how the phone page is divided, so it is a rule
   and not a caption. */
.k-band-title{
  font-size:9.5px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;
  color:var(--k-ink);
  padding-bottom:10px;
  border-bottom:1px solid var(--k-rule);
  width:100%
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

/* Artboard `2d` draws it as the notice sand and nothing else: a coloured
   left edge on a strip that is already a different ground says the same
   thing twice. */
.k-warning-strip{
  background:var(--k-surface-notice);
  color:var(--k-ink)
}
.k-warning-strip .q-icon{color:var(--k-warning)}
/* ── Import mapping (artboard 2d) ─────────────────────────────────── */
.k-field-row{display:flex;align-items:center;gap:12px;width:100%}
.k-field-label{width:104px;flex:none;font-size:12.5px;color:var(--k-ink-2)}
.k-field-select .q-field__control{
  background:var(--k-surface-sunken);
  border:1px solid var(--k-field-border);
  border-radius:8px;
  min-height:36px;
  padding:0 12px
}
.k-field-select .q-field__control:before,
.k-field-select .q-field__control:after{display:none}
.k-field-select .q-field__native{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12.5px;
  color:var(--k-ink);
  min-height:36px;
  padding:0
}
.k-field-select .q-field__marginal,
.k-field-select .q-field__append{
  height:36px;
  color:var(--k-muted);
  font-size:16px;
  align-items:center;
  gap:8px
}
/* Nothing mapped yet: paper on a plain hairline, and the app's own face —
   "Not mapped" is a sentence, not a column name. */
.k-field-select--unset .q-field__control{
  background:var(--k-surface);
  border-color:var(--k-border)
}
.k-field-select--unset .q-field__native{
  font-family:'Libre Franklin',ui-sans-serif,system-ui,sans-serif;
  color:var(--k-muted)
}
.k-card-rule{height:1px;background:var(--k-hairline);margin:20px 0;width:100%}
/* The file on the left, the mapping on the right — the wider side is the one
   you are reading from (artboard `2d`). Under `md` they stack. */
.k-mapping-grid{
  /* The tick on "negative amounts are expenses" is ink on this card, not the
     accent: the accent is the step you are on, up on the step line. */
  --q-info:var(--k-ink);
  display:grid;
  grid-template-columns:1.25fr 1fr;
  gap:22px;
  align-items:start
}
.k-mapping-grid > *{padding:22px 24px}
@media (max-width:1023.98px){.k-mapping-grid{grid-template-columns:1fr}}
/* The sample is a box inside the card, not a table on the card's own paper:
   a hairline round it, a warm header row, and mono throughout. */
.k-sample-table{border:1px solid var(--k-border);border-radius:8px;overflow:hidden}
.k-sample-table .q-table th{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:9.5px;
  letter-spacing:.06em;
  background:var(--k-surface-warm);
  padding:8px 12px
}
.k-sample-table .q-table td{font-size:11.5px;padding:8px 12px}
.k-sample-table .q-table thead tr,.k-sample-table .q-table tbody td{height:auto}
.k-plan-total{border-top:1px solid var(--k-border-strong)}
/* Artboard `2c` rounds the month being edited rather than tinting a
   square column of cells edge to edge. */
.k-plan-month-now{background:var(--k-plan-now);border-radius:4px}
.k-cat-row{border-bottom-color:var(--k-hairline)}
.k-cat-row:hover{background:var(--k-row-hover)}
.k-subcat-label{color:var(--k-ink-2)}
.k-selection-bar{background:var(--k-surface-warm-strong);color:var(--k-ink)}
.k-selection-divider{width:1px;height:16px;background:var(--k-border-strong);flex:none}
.q-btn.k-selection-action{
  font-size:12.5px;
  font-weight:500;
  letter-spacing:0;
  color:var(--k-ink-2);
  padding:0 4px;
  min-height:24px
}
.q-btn.k-selection-action .q-icon{font-size:16px;color:inherit}
.q-btn.k-selection-action--danger{color:var(--k-expense)}
.k-clear-all{color:var(--k-accent-text)}
.k-clear-all:hover{text-decoration:underline}
/* The ledger card (artboard `2a`): 8px of paper above the header rule, the
   rows flush to the card's own 18px gutter, and the pagination bar inside
   the same box under a rule a shade stronger than the row hairlines. */
.k-ledger-card{
  background:var(--k-surface);
  box-shadow:var(--k-card-shadow);
  border-radius:12px;
  padding:8px 0 0;
  overflow:hidden;
  width:100%
}
.k-ledger-card .k-table{overflow-x:auto}
.k-ledger-card .q-table th{padding:8px 9px 12px}
.k-ledger-card .q-table td{padding:12px 9px}
.k-ledger-card .q-table th:first-child,
.k-ledger-card .q-table td:first-child{padding-left:18px}
/* A separator is a band, not a row: artboard `2a` gives it 7px where a row
   takes 12, so the week reads as a heading over the days under it. */
.k-ledger-card .q-table td.k-sep-row{padding:7px 18px}
/* Quasar's checkbox reserves 40px (24 even when dense) for a box the
   artboard draws at 15, which made the header rule 61px tall on a card whose
   rows are 43. */
/* `--q-info` is the ledger's ink here, which is what the row checkboxes are
   set to: Quasar's `.bg-*` / `.text-*` helpers cannot be out-specified, so
   the variable they read is redefined instead. Nothing else inside the card
   uses the info colour; the segment in the foot sets its own. */
.k-ledger-card{--q-info:var(--k-ink)}
/* Quasar holds every table cell on one line. The tags cell is the one
   that must not be: `2a` gives it a 130px track, and a row carrying
   four labels wraps them rather than widening the table until the
   row's own actions fall off the right edge. */
.k-ledger-card .k-tags-cell{white-space:normal}
.k-ledger-card .k-row-action{color:var(--k-muted)}
.k-ledger-card .k-row-action .q-icon{font-size:17px}
.k-ledger-card .q-checkbox__inner{width:18px;height:18px;font-size:18px}
.k-ledger-card .q-checkbox__bg{border-width:1.5px}
/* Quasar fixes every table row at 48px. The artboard's are the height of
   what is in them — 43 for a movement, 31 for a week band — which is the
   same rule the dashboard's month card had to be taught. */
.k-ledger-card .q-table thead tr,
.k-ledger-card .q-table tbody td{height:auto}
.k-ledger-card .q-table th:last-child,
.k-ledger-card .q-table td:last-child{padding-right:18px}
.k-ledger-foot{border-top:1px solid var(--k-border);padding:14px 18px}
/* The page chevrons are navigation, not an offer: ink-2 where they work and
   the disabled token where they do not, which is what artboard `2a` draws. */
.k-ledger-foot .q-btn{color:var(--k-ink-2)}
.k-ledger-foot .q-btn.disabled{color:var(--k-disabled)}
/* Tags are the one cell that holds a list. Quasar keeps every cell on one
   line, which pushed the row-action column off the card as soon as a
   transaction carried four of them. */
.k-ledger-card .q-table td[key="tags"]{white-space:normal}
.k-ledger-card .q-table td[key="tags"] .q-chip{margin:1px 4px 1px 0}
.k-select-sunken .q-field__control{
  background:var(--k-surface-sunken);
  border-radius:8px;
  min-height:28px;
  padding:0 10px
}
.k-select-sunken .q-field__control:before,
.k-select-sunken .q-field__control:after{display:none}
.k-select-sunken .q-field__native{
  font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;
  color:var(--k-ink);
  min-height:28px;
  padding:0
}
.k-select-sunken .q-field__marginal{height:28px;color:var(--k-muted)}
/* Ledger rows: the category reads as a pill, the group separator as a band. */
.k-cat-pill{
  display:inline-block;
  padding:3px 9px;
  border-radius:999px;
  background:var(--k-surface-sunken);
  color:var(--k-ink-2);
  font-size:11.5px;
  /* A long category name ends in an ellipsis rather than widening its
     column: `2a` draws the category track at a fixed 168px, and a table
     that lays itself out automatically gives the slack to whichever cell
     asks loudest — until the row's own actions are off the screen. */
  max-width:100%;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  vertical-align:middle
}
.k-sep-row{
  background:var(--k-surface-warm);
  color:var(--k-ink-2);
  font-size:11px;
  font-weight:500;
  letter-spacing:.04em;
  border-bottom:1px solid var(--k-hairline)
}
/* Upcoming planned rows: the same ledger, set back a step — a promise reads
   lighter and in italics, so it is never mistaken for a recorded figure. */
.k-planned-row{font-style:italic;color:var(--k-muted)}
.k-planned-row:hover{background:var(--k-row-hover)}
.k-planned-chip{border-color:var(--k-chip-dash);color:var(--k-muted);font-style:normal}
.k-upcoming-when{font-style:normal;font-size:10.5px;color:var(--k-muted);white-space:nowrap}

/* ── Shared utility classes (used by the per-screen restyle plans) ── */
.k-pace{
  position:relative;
  height:7px;
  border-radius:4px;
  background:var(--k-hairline)
}
/* Artboard `1c` draws two of these at two weights: 8px for the month card's
   savings pace, which is the card's argument, and 6px under a
   budget-variance row, which is a row's worth of the same. */
.k-pace--month{height:8px;border-radius:4px}
.k-pace--row{height:6px;border-radius:3px}
.k-pace__fill{position:absolute;top:0;bottom:0;left:0;border-radius:4px}
.k-pace__tick{
  position:absolute;
  top:-3px;
  width:2px;
  height:14px;
  background:var(--k-ink);
  opacity:.35
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
  display:inline-flex;align-items:center;gap:7px;
  padding:5px 12px;border-radius:8px;
  background:var(--k-surface-sunken);
  border:1px solid var(--k-field-border);
  font-weight:500;color:var(--k-ink);
  cursor:pointer;
  transition:border-color .12s ease,background-color .12s ease
}
.k-slot:hover{border-color:var(--k-accent)}
.k-slot .q-icon{color:var(--k-muted);font-size:15px}
body.k-dragging .k-slot--drop{
  background:var(--k-surface-warm);
  border:1px dashed var(--k-accent)
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
  background:var(--k-on-accent);
  color:var(--k-banner-btn-ink);
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
