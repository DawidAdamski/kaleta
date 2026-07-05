# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

# Semantic colour tokens for transaction amounts.
# Income/expense use green/red; never text-primary (teal brand accent).
AMOUNT_INCOME = "text-green-7"
AMOUNT_EXPENSE = "text-red-7"
AMOUNT_NEUTRAL = "text-slate-500"

# Shared surface tokens — flat panels, 12 px radius (mockup-aligned).
_SURFACE = "k-surface w-full rounded-xl border border-slate-200/70 bg-white/80"
_CARD_PAD = "p-5"

PAGE_SHELL = "bg-slate-50"
PAGE_CONTAINER = "w-full mx-auto p-6 md:p-8 gap-6"

HEADER = "bg-white/90 text-slate-900 border-b border-slate-200/70"
DRAWER = "bg-white/95 border-r border-slate-200/70 pt-3"

NAV_GROUP = (
    "k-nav-group text-[11px] text-slate-500 uppercase tracking-[0.14em] font-semibold flex-1"
)
NAV_GROUP_ROW = (
    "k-nav-row items-center h-9 px-3 mx-2 rounded-xl cursor-pointer "
    "select-none hover:bg-slate-100 transition-colors"
)
NAV_ITEM = (
    "k-nav-item h-11 rounded-xl mx-2 mb-1 cursor-pointer transition-colors "
    "hover:bg-slate-100 border-l-4 border-transparent pl-2"
)
NAV_ITEM_ACTIVE = "k-nav-item--active"

PAGE_TITLE = "text-3xl font-semibold tracking-tight text-primary"
SECTION_CARD = f"{_SURFACE} {_CARD_PAD}"
TOOLBAR_CARD = f"{_SURFACE} p-3"
SECTION_TITLE = "k-muted text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500"
SECTION_HEADING = "text-lg font-semibold text-primary"
DIALOG_TITLE = "text-lg font-bold text-primary"
BODY_MUTED = "k-muted text-sm text-slate-500"

KPI_VALUE = "text-3xl font-semibold tracking-tight"
KPI_TREND_POSITIVE = "text-teal-600"
KPI_TREND_NEGATIVE = "text-red-600"
KPI_TREND_NEUTRAL = "text-slate-400"

TABLE_CARD = SECTION_CARD
TABLE_SURFACE = (
    "w-full [&_.q-table]:bg-transparent [&_.q-table__top]:px-0 "
    "[&_.q-table_th]:text-slate-500 [&_.q-table_th]:font-semibold "
    "[&_.q-table_th]:uppercase [&_.q-table_th]:tracking-[0.08em] "
    "[&_.q-table_th]:text-[11px] [&_.q-table_td]:text-sm "
    "[&_.q-table_tbody_tr:hover]:bg-slate-50"
)

# Inter font + Quasar brand (teal primary). Light mode uses teal-600 for contrast.
BASE_CSS = """
@font-face{
  font-family:'Inter';
  font-style:normal;
  font-weight:100 900;
  font-display:swap;
  src:url('/static/fonts/inter-var.woff2') format('woff2')
}
:root{
  --q-primary:#0d9488;
  --q-secondary:#64748b;
  --q-accent:#14b8a6;
  --q-positive:#16a34a;
  --q-negative:#dc2626;
  --q-info:#0d9488;
  --q-warning:#d97706
}
body,.q-body--layout{
  font-family:'Inter',ui-sans-serif,system-ui,sans-serif;
  font-feature-settings:'cv02','cv03','cv04','cv11'
}
"""

# Dark-mode overrides via Quasar `.body--dark` on <body>.
DARK_CSS = """
.body--dark{
  --q-primary:#14b8a6;
  --q-info:#14b8a6
}
/* Palette: deep navy body, elevated flat surfaces. */
body.body--dark{background-color:rgb(10,14,23);color-scheme:dark}
.body--dark .q-header{
  background:rgb(10,14,23);
  color:rgb(241,245,249);
  border-bottom-color:rgb(30,36,48)
}
.body--dark .q-header .text-slate-500{color:rgb(148,163,184)}
.body--dark .q-drawer,
.body--dark .q-drawer__content{
  background:rgb(10,14,23);
  border-right-color:rgb(30,36,48)
}
.body--dark .q-card--dark,
.body--dark .q-card.q-dark{
  background:rgb(21,25,34);
  color:rgb(241,245,249);
  border-color:rgb(36,42,54)
}
.body--dark .q-table--dark,
.body--dark .q-table--dark .q-table__top,
.body--dark .q-table--dark .q-table__bottom,
.body--dark .q-table--dark thead,
.body--dark .q-table--dark tbody,
.body--dark .q-table--dark tr{background-color:transparent}
.body--dark .k-nav-group{color:rgb(100,116,139)}
.body--dark .k-nav-row:hover{background:rgba(21,25,34,.8)}
.body--dark .k-nav-item:hover{background:rgba(21,25,34,.8)}
.body--dark .k-nav-item--active{
  background:rgba(20,184,166,.1);
  border-left-color:rgb(20,184,166)
}
.body--dark .k-nav-item--active .q-item__label{color:rgb(226,232,240)}
.body--dark .k-nav-item--active .q-icon{color:rgb(94,234,212)!important}
.body--dark .k-nav-item:not(.k-nav-item--active) .q-icon{color:rgb(100,116,139)!important}
.k-nav-item--active{
  background:rgba(13,148,136,.08);
  border-left-color:rgb(13,148,136)
}
.k-nav-item--active .q-item__label{color:rgb(15,23,42);font-weight:600}
.k-nav-item--active .q-icon{color:rgb(13,148,136)!important}
.k-nav-item:not(.k-nav-item--active) .q-icon{color:rgb(100,116,139)!important}
.body--dark .k-surface{
  background:rgb(21,25,34);
  border-color:rgb(36,42,54)
}
.body--dark .k-muted{color:rgb(148,163,184)}
.body--dark .text-slate-500{color:rgb(148,163,184)}
.body--dark .q-table--dark td{color:rgb(226,232,240)}
.body--dark .q-table--dark .q-table th{color:rgb(148,163,184)}
.body--dark .q-table--dark .q-table tbody tr:hover{background:rgba(21,25,34,.6)}
.body--dark .k-cat-row{border-bottom-color:rgb(36,42,54)}
.body--dark .k-cat-row:hover{background:rgba(21,25,34,.5)}
.body--dark .k-subcat-label{color:rgb(226,232,240)}
.body--dark .k-info-banner{background:rgba(13,148,136,.15)}
.body--dark .k-selection-bar{background:rgba(13,148,136,.2);color:rgb(241,245,249)}
.body--dark .kpi-trend-positive{color:rgb(94,234,212)}
.body--dark .kpi-trend-negative{color:rgb(252,165,165)}
.body--dark .nicegui-expansion-content .border-b{border-bottom-color:rgb(30,36,48)}
.body--dark .q-toggle__track{background:rgba(148,163,184,.35)}

@layer quasar_importants {
  .body--dark .bg-slate-50{background:rgba(21,25,34,.7) !important}
  .body--dark .bg-slate-100{background:rgb(21,25,34) !important}
  .body--dark .bg-slate-200{background:rgb(21,25,34) !important}
  .body--dark .bg-slate-600{background:rgb(71,85,105) !important}
  .body--dark .bg-slate-700{background:rgb(36,42,54) !important}
  .body--dark .bg-slate-100 .text-slate-600,
  .body--dark .bg-slate-100.text-slate-600,
  .body--dark .bg-slate-50 .text-slate-600,
  .body--dark .bg-slate-50.text-slate-600,
  .body--dark .text-slate-600{color:rgb(148,163,184) !important}
  .body--dark .text-slate-500{color:rgb(148,163,184) !important}
  .body--dark .text-slate-400{color:rgb(100,116,139) !important}
  .body--dark .border-slate-300{border-color:rgb(36,42,54) !important}
  .body--dark .bg-green-1{background:rgba(34,197,94,.12) !important}
  .body--dark .bg-green-2{background:rgba(34,197,94,.18) !important}
  .body--dark .bg-blue-1{background:rgba(20,184,166,.12) !important}
  .body--dark .bg-blue-2{background:rgba(20,184,166,.18) !important}
  .body--dark .bg-red-1{background:rgba(239,68,68,.15) !important}
  .body--dark .bg-orange-1{background:rgba(249,115,22,.15) !important}
  .body--dark .bg-amber-1{background:rgba(245,158,11,.15) !important}
  .body--dark .bg-yellow-1{background:rgba(234,179,8,.15) !important}
  .body--dark .bg-teal-1{background:rgba(20,184,166,.15) !important}
  .body--dark .bg-purple-1{background:rgba(168,85,247,.15) !important}
  .body--dark .bg-pink-1{background:rgba(236,72,153,.15) !important}
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
  .body--dark .text-teal-600{color:rgb(94,234,212) !important}
}
.body--dark .bg-slate-100{border-color:rgb(36,42,54)}
.body--dark .hover\\:bg-slate-50:hover{background:rgba(21,25,34,.7) !important}
.body--dark .hover\\:bg-slate-100:hover{background:rgb(21,25,34) !important}
.body--dark .hover\\:bg-slate-700:hover{background:rgb(36,42,54) !important}

.body--dark .q-menu{
  background:rgb(10,14,23);
  color:rgb(226,232,240);
  border:1px solid rgb(30,36,48)
}
.body--dark .q-menu .q-item{color:rgb(226,232,240)}
.body--dark .q-menu .q-item__label--caption,
.body--dark .q-menu .q-item__label--header{color:rgb(148,163,184)}
.body--dark .q-menu .q-item:hover,
.body--dark .q-menu .q-item--active,
.body--dark .q-menu .q-item.q-manual-focusable--focused{
  background:rgba(21,25,34,.8)
}
.body--dark .q-menu .q-separator{background:rgb(30,36,48)}
.body--dark .q-tooltip{
  background:rgb(21,25,34);
  color:rgb(226,232,240)
}
.body--dark .q-date,
.body--dark .q-time{background:rgb(10,14,23);color:rgb(226,232,240)}
.body--dark .q-date__header,
.body--dark .q-time__header{background:rgb(21,25,34);color:rgb(241,245,249)}
.body--dark .q-date__calendar-item--fill,
.body--dark .q-date__calendar-item--out{color:rgb(100,116,139)}
.body--dark .q-date__calendar-item > div,
.body--dark .q-date__calendar-weekdays > div{color:rgb(226,232,240)}
.body--dark .q-date__navigation .q-btn,
.body--dark .q-date__view .q-btn{color:rgb(226,232,240)}
.body--dark .q-dialog__inner > .q-card{
  background:rgb(10,14,23);
  color:rgb(226,232,240);
  border:1px solid rgb(30,36,48)
}
.body--dark .q-dialog .text-slate-500,
.body--dark .q-dialog .text-slate-600{color:rgb(148,163,184)}
.body--dark .q-dialog .q-separator{background:rgb(30,36,48)}
.body--dark .q-field--outlined .q-field__control{color:rgb(226,232,240)}
.body--dark .q-field--outlined .q-field__control:before{border-color:rgb(36,42,54)}
.body--dark .q-field--outlined:hover .q-field__control:before{border-color:rgb(100,116,139)}
.body--dark .q-field__native,
.body--dark .q-field__input,
.body--dark .q-field__prefix,
.body--dark .q-field__suffix{color:rgb(226,232,240)}
.body--dark .q-field__label{color:rgb(148,163,184)}
.body--dark .q-field--filled .q-field__control{background:rgba(21,25,34,.5)}
.body--dark .q-placeholder::placeholder{color:rgb(100,116,139)}
.body--dark .q-chip{background:rgb(21,25,34);color:rgb(226,232,240)}
.body--dark .q-separator{background:rgb(30,36,48)}
.body--dark hr.q-separator--horizontal{background:rgb(30,36,48)}
.body--dark .q-table__bottom,
.body--dark .q-table__top{
  color:rgb(148,163,184);
  border-color:rgb(30,36,48)
}
.body--dark .q-pagination .q-btn{color:rgb(226,232,240)}
.body--dark .nicegui-echart text{fill:rgb(148,163,184)}
.body--dark .q-expansion-item__toggle-icon,
.body--dark .q-expansion-item .q-item__label{color:rgb(226,232,240)}
.body--dark .q-notification{background:rgb(21,25,34);color:rgb(226,232,240)}
.body--dark .q-uploader--dark,
.body--dark .q-uploader{
  background:rgb(21,25,34);
  color:rgb(226,232,240);
  border-color:rgb(36,42,54)
}
.body--dark .q-uploader__header{background:rgb(10,14,23);color:rgb(226,232,240)}
.body--dark .q-uploader__subtitle,
.body--dark .q-uploader__title{color:rgb(226,232,240)}
.body--dark .q-uploader__list{background:rgb(21,25,34)}
.body--dark ::-webkit-scrollbar{width:10px;height:10px}
.body--dark ::-webkit-scrollbar-track{background:rgb(10,14,23)}
.body--dark ::-webkit-scrollbar-thumb{
  background:rgb(36,42,54);
  border-radius:4px;
  border:2px solid rgb(10,14,23)
}
.body--dark ::-webkit-scrollbar-thumb:hover{background:rgb(71,85,105)}
.body--dark ::-webkit-scrollbar-corner{background:rgb(10,14,23)}
.body--dark *{scrollbar-color:rgb(36,42,54) rgb(10,14,23);scrollbar-width:thin}
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
.q-drawer--mini .k-nav-item--active{border-left-color:transparent}
"""


def theme_css() -> str:
    """Full theme stylesheet: Inter font, brand colours, dark overrides."""
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
