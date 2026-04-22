from __future__ import annotations

# Semantic colour tokens for transaction amounts.
# text-green-7 / text-red-7 already have dark-mode overrides in DARK_CSS.
AMOUNT_INCOME = "text-green-7"
AMOUNT_EXPENSE = "text-red-7"
AMOUNT_NEUTRAL = "text-grey-7"


def amount_class(tx_type: str) -> str:
    """Return the colour class for an amount cell given its transaction type.

    Accepts the raw string value from `TransactionType` ("income", "expense",
    "transfer") so it can be used both in Python and in Vue slot templates.
    """
    if tx_type == "income":
        return AMOUNT_INCOME
    if tx_type == "expense":
        return AMOUNT_EXPENSE
    return AMOUNT_NEUTRAL


PAGE_SHELL = "bg-slate-50"
PAGE_CONTAINER = "w-full mx-auto p-6 md:p-8 gap-6"

HEADER = "bg-white/90 text-slate-900 border-b border-slate-200/70"
DRAWER = "bg-white/95 border-r border-slate-200/70 pt-3"

NAV_GROUP = (
    "k-nav-group text-[11px] text-slate-500 uppercase "
    "tracking-[0.14em] font-semibold flex-1"
)
NAV_GROUP_ROW = (
    "k-nav-row items-center h-9 px-3 mx-2 rounded-xl cursor-pointer "
    "select-none hover:bg-slate-100 transition-colors"
)
NAV_ITEM = (
    "k-nav-item h-11 rounded-xl mx-2 mb-1 cursor-pointer transition-colors hover:bg-slate-100"
)

PAGE_TITLE = "text-3xl font-semibold tracking-tight text-primary"
SECTION_CARD = (
    "k-surface w-full rounded-2xl border border-slate-200/70 bg-white/80 p-5 shadow-sm"
)
TOOLBAR_CARD = (
    "k-surface w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 shadow-sm"
)
SECTION_TITLE = "k-muted text-sm font-semibold uppercase tracking-[0.14em] text-slate-500"
SECTION_HEADING = "text-lg font-semibold text-primary"
DIALOG_TITLE = "text-lg font-bold text-primary"
BODY_MUTED = "k-muted text-sm text-slate-500"

TABLE_CARD = SECTION_CARD
TABLE_SURFACE = (
    "w-full [&_.q-table]:bg-transparent [&_.q-table__top]:px-0 "
    "[&_.q-table_th]:text-slate-500 [&_.q-table_th]:font-semibold "
    "[&_.q-table_th]:uppercase [&_.q-table_th]:tracking-[0.08em] "
    "[&_.q-table_th]:text-[11px] [&_.q-table_td]:text-sm "
    "[&_.q-table_tbody_tr:hover]:bg-slate-50"
)

# All dark-mode overrides in one place.
# Uses Quasar's .body--dark class (added to <body> when dark mode is on).
# Specificity rules:
#   body.body--dark           = 0-1-1  beats bg-slate-50 (0-1-0) ✓
#   .body--dark .q-X          = 0-2-0  beats Tailwind bg/color (0-1-0) ✓
#   .body--dark .k-X:hover    = 0-2-1  beats Tailwind hover: (0-1-1) ✓
#   .body--dark .q-table--dark .q-table th/td  = 0-3-1 beats TABLE_SURFACE (0-2-1) ✓
DARK_CSS = """
/* Unified palette: body = slate-900, surfaces = slate-800 (elevation above body). */
body.body--dark{background-color:rgb(15,23,42);color-scheme:dark}
.body--dark .q-header{
  background:rgb(15,23,42);
  color:rgb(241,245,249);
  border-bottom-color:rgb(30,41,59)
}
.body--dark .q-header .text-slate-500{color:rgb(148,163,184)}
.body--dark .q-drawer,
.body--dark .q-drawer__content{
  background:rgb(15,23,42);
  border-right-color:rgb(30,41,59)
}
/* All Quasar dark cards (plain ui.card without k-surface) → palette slate-800. */
.body--dark .q-card--dark,
.body--dark .q-card.q-dark{
  background:rgb(30,41,59);
  color:rgb(241,245,249);
  border-color:rgb(51,65,85)
}
/* Quasar dark tables default to #1d1d1d — force transparent so parent shows. */
.body--dark .q-table--dark,
.body--dark .q-table--dark .q-table__top,
.body--dark .q-table--dark .q-table__bottom,
.body--dark .q-table--dark thead,
.body--dark .q-table--dark tbody,
.body--dark .q-table--dark tr{background-color:transparent}
.body--dark .k-nav-group{color:rgb(148,163,184)}
.body--dark .k-nav-row:hover,
.body--dark .k-nav-item:hover{background:rgb(30,41,59)}
.body--dark .k-surface{
  background:rgb(30,41,59);
  border-color:rgb(51,65,85)
}
.body--dark .k-muted{color:rgb(148,163,184)}
.body--dark .q-table--dark td{color:rgb(226,232,240)}
.body--dark .q-table--dark .q-table th{color:rgb(148,163,184)}
.body--dark .q-table--dark .q-table tbody tr:hover{background:rgba(30,41,59,.6)}
.body--dark .k-cat-row{border-bottom-color:rgb(51,65,85)}
.body--dark .k-cat-row:hover{background:rgba(30,41,59,.5)}
.body--dark .k-subcat-label{color:rgb(226,232,240)}
.body--dark .k-info-banner{background:rgba(30,58,138,.3)}
.body--dark .k-selection-bar{background:rgba(30,58,138,.4);color:rgb(241,245,249)}

/* ── Tailwind .border-b dividers inside expansion panels (accounts, net-worth) ── */
/* Quasar dark does not reset Tailwind's border-color so rows get white borders.  */
.body--dark .nicegui-expansion-content .border-b{border-bottom-color:rgb(30,41,59)}

/* ── q-toggle (Switch) off-state track — inherits currentcolor ── */
/* Quasar rule has no !important; our unlayered rule wins.         */
.body--dark .q-toggle__track{background:rgba(148,163,184,.35)}

/* ── Quasar .bg-grey-* overrides (KBD badges, table group separators) ── */
/* Quasar's quasar.important.prod.css imports into @layer quasar_importants  */
/* with !important. Per CSS cascade: layered !important > unlayered !important. */
/* We must declare inside the same layer to win — and match the `background`  */
/* shorthand Quasar uses (not `background-color` longhand).                   */
@layer quasar_importants {
  .body--dark .bg-grey-1{background:rgba(30,41,59,.7) !important}
  .body--dark .bg-grey-2{background:rgb(30,41,59) !important}
  .body--dark .bg-grey-3{background:rgb(30,41,59) !important}
  .body--dark .bg-grey-4{background:rgb(51,65,85) !important}
  .body--dark .bg-grey-5{background:rgb(51,65,85) !important}
  .body--dark .bg-grey-6{background:rgb(71,85,105) !important}
  .body--dark .bg-grey-7{background:rgb(71,85,105) !important}
  .body--dark .bg-grey-8{background:rgb(100,116,139) !important}
  .body--dark .bg-grey-9{background:rgb(100,116,139) !important}
  .body--dark .bg-grey-2.text-grey-7,
  .body--dark .bg-grey-2 .text-grey-7,
  .body--dark .bg-grey-1 .text-grey-7,
  .body--dark .bg-grey-1.text-grey-7,
  .body--dark .text-grey-7{color:rgb(148,163,184) !important}
  .body--dark .text-grey-6{color:rgb(148,163,184) !important}
  .body--dark .text-grey-5{color:rgb(100,116,139) !important}
  .body--dark .border-grey-4{border-color:rgb(51,65,85) !important}

  /* Tinted pale backgrounds (wizard done rows, info banners, hover highlights)  */
  /* Quasar's bg-*-1 / bg-*-2 are near-white tints — make them translucent dark.  */
  .body--dark .bg-green-1{background:rgba(34,197,94,.12) !important}
  .body--dark .bg-green-2{background:rgba(34,197,94,.18) !important}
  .body--dark .bg-blue-1{background:rgba(59,130,246,.15) !important}
  .body--dark .bg-blue-2{background:rgba(59,130,246,.22) !important}
  .body--dark .bg-red-1{background:rgba(239,68,68,.15) !important}
  .body--dark .bg-orange-1{background:rgba(249,115,22,.15) !important}
  .body--dark .bg-amber-1{background:rgba(245,158,11,.15) !important}
  .body--dark .bg-yellow-1{background:rgba(234,179,8,.15) !important}
  .body--dark .bg-teal-1{background:rgba(20,184,166,.15) !important}
  .body--dark .bg-purple-1{background:rgba(168,85,247,.15) !important}
  .body--dark .bg-pink-1{background:rgba(236,72,153,.15) !important}

  /* Dark-tint text (*-7, *-8, *-9 on light bg) — boost for readability on dark. */
  .body--dark .text-green-8,
  .body--dark .text-green-9{color:rgb(134,239,172) !important}
  .body--dark .text-green-7{color:rgb(110,231,183) !important}
  .body--dark .text-amber-7,
  .body--dark .text-amber-8,
  .body--dark .text-amber-9{color:rgb(252,211,77) !important}
  .body--dark .text-red-7,
  .body--dark .text-red-8,
  .body--dark .text-red-9{color:rgb(252,165,165) !important}
  .body--dark .text-blue-7,
  .body--dark .text-blue-8,
  .body--dark .text-blue-9{color:rgb(147,197,253) !important}
  .body--dark .text-orange-7,
  .body--dark .text-orange-8,
  .body--dark .text-orange-9{color:rgb(253,186,116) !important}
}
.body--dark .bg-grey-2{border-color:rgb(51,65,85)}

/* ── Quasar menus, tooltips, date/time pickers (dropdowns & popovers) ── */
.body--dark .q-menu{
  background:rgb(15,23,42);
  color:rgb(226,232,240);
  border:1px solid rgb(30,41,59)
}
.body--dark .q-menu .q-item{color:rgb(226,232,240)}
.body--dark .q-menu .q-item__label--caption,
.body--dark .q-menu .q-item__label--header{color:rgb(148,163,184)}
.body--dark .q-menu .q-item:hover,
.body--dark .q-menu .q-item--active,
.body--dark .q-menu .q-item.q-manual-focusable--focused{
  background:rgba(30,41,59,.8)
}
.body--dark .q-menu .q-separator{background:rgb(30,41,59)}
.body--dark .q-tooltip{
  background:rgb(30,41,59);
  color:rgb(226,232,240)
}

/* ── Quasar date picker / time picker popup ── */
.body--dark .q-date,
.body--dark .q-time{background:rgb(15,23,42);color:rgb(226,232,240)}
.body--dark .q-date__header,
.body--dark .q-time__header{background:rgb(30,41,59);color:rgb(241,245,249)}
.body--dark .q-date__calendar-item--fill,
.body--dark .q-date__calendar-item--out{color:rgb(100,116,139)}
.body--dark .q-date__calendar-item > div,
.body--dark .q-date__calendar-weekdays > div{color:rgb(226,232,240)}
.body--dark .q-date__navigation .q-btn,
.body--dark .q-date__view .q-btn{color:rgb(226,232,240)}

/* ── Quasar dialog card ── */
.body--dark .q-dialog__inner > .q-card{
  background:rgb(15,23,42);
  color:rgb(226,232,240);
  border:1px solid rgb(30,41,59)
}
.body--dark .q-dialog .text-slate-500,
.body--dark .q-dialog .text-slate-600{color:rgb(148,163,184)}
.body--dark .q-dialog .q-separator{background:rgb(30,41,59)}

/* ── Quasar inputs / textareas / selects ── */
.body--dark .q-field--outlined .q-field__control{color:rgb(226,232,240)}
.body--dark .q-field--outlined .q-field__control:before{
  border-color:rgb(51,65,85)
}
.body--dark .q-field--outlined:hover .q-field__control:before{
  border-color:rgb(100,116,139)
}
.body--dark .q-field__native,
.body--dark .q-field__input,
.body--dark .q-field__prefix,
.body--dark .q-field__suffix{color:rgb(226,232,240)}
.body--dark .q-field__label{color:rgb(148,163,184)}
.body--dark .q-field--filled .q-field__control{background:rgba(30,41,59,.5)}
.body--dark .q-placeholder::placeholder{color:rgb(100,116,139)}

/* ── Quasar chips / badges / separators ── */
.body--dark .q-chip{background:rgb(30,41,59);color:rgb(226,232,240)}
.body--dark .q-separator{background:rgb(30,41,59)}
.body--dark hr.q-separator--horizontal{background:rgb(30,41,59)}

/* ── Pagination footer / table bottom ── */
.body--dark .q-table__bottom,
.body--dark .q-table__top{
  color:rgb(148,163,184);
  border-color:rgb(30,41,59)
}
.body--dark .q-pagination .q-btn{color:rgb(226,232,240)}

/* ── ECharts legend / axis labels inherit text color from parent ── */
.body--dark .nicegui-echart text{fill:rgb(226,232,240)}

/* ── Expansion panel headers inside k-surface ── */
.body--dark .q-expansion-item__toggle-icon,
.body--dark .q-expansion-item .q-item__label{color:rgb(226,232,240)}

/* ── Notification / banner ── */
.body--dark .q-notification{background:rgb(30,41,59);color:rgb(226,232,240)}

/* ── File uploader (last #1d1d1d holdout on /import) ── */
.body--dark .q-uploader--dark,
.body--dark .q-uploader{
  background:rgb(30,41,59);
  color:rgb(226,232,240);
  border-color:rgb(51,65,85)
}
.body--dark .q-uploader__header{background:rgb(15,23,42);color:rgb(226,232,240)}
.body--dark .q-uploader__subtitle,
.body--dark .q-uploader__title{color:rgb(226,232,240)}
.body--dark .q-uploader__list{background:rgb(30,41,59)}

/* ── Themed scrollbars (WebKit + Firefox) ── */
.body--dark ::-webkit-scrollbar{width:10px;height:10px}
.body--dark ::-webkit-scrollbar-track{background:rgb(15,23,42)}
.body--dark ::-webkit-scrollbar-thumb{
  background:rgb(51,65,85);
  border-radius:4px;
  border:2px solid rgb(15,23,42)
}
.body--dark ::-webkit-scrollbar-thumb:hover{background:rgb(71,85,105)}
.body--dark ::-webkit-scrollbar-corner{background:rgb(15,23,42)}
.body--dark *{scrollbar-color:rgb(51,65,85) rgb(15,23,42);scrollbar-width:thin}

/* ── Left drawer: never show a horizontal scrollbar when narrow ── */
.q-drawer__content{overflow-x:hidden}

/* ── Mini-drawer (icon-only) collapse mode ──                                */
/* Quasar adds `.q-drawer--mini` to the drawer when the `mini` prop is set.  */
/* Drawer is 57 px wide — items must fit inside without horizontal clipping.  */
.q-drawer--mini .k-nav-row,
.q-drawer--mini .k-app-version{display:none !important}
/* The drawer's inner .q-drawer__content has 16 px horizontal padding from    */
/* NiceGUI; zero it out so items can use the full 57 px rail and center.      */
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


def kpi_card_classes() -> str:
    return (
        "k-surface flex-1 min-w-52 rounded-2xl border border-slate-200/70 "
        "bg-white/80 p-5 shadow-sm"
    )


def icon_badge_classes(color: str) -> str:
    return f"h-11 w-11 rounded-2xl bg-{color}-500/10 text-{color}-600"
