# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Polish names, amounts and shapes the example data is built from.

Kept in one module because more than one seeder needs the same list: the
budgets seeder budgets the categories the transactions seeder spends in, and
the subscriptions seeder names the merchants the ledger already pays. Two
copies of "Żywność" would be two features quietly disagreeing.

Curated strings rather than a generated locale: ``Faker`` is a dev dependency,
and the seeders ship in the app so the Settings button works on an install that
never saw the test extras.
"""

from __future__ import annotations

from decimal import Decimal

#: How far back the ledger goes.
YEARS = 6
MONTHS = YEARS * 12

EXPENSE_CATEGORIES = (
    "Żywność",
    "Restauracje & Kawiarnie",
    "Transport",
    "Paliwo",
    "Mieszkanie & Czynsz",
    "Media (prąd, gaz, woda)",
    "Zdrowie & Apteka",
    "Rozrywka",
    "Odzież & Obuwie",
    "Elektronika",
    "Sport & Fitness",
    "Edukacja",
    "Subskrypcje",
    "Wakacje & Podróże",
    "Inne wydatki",
)
INCOME_CATEGORIES = ("Wynagrodzenie", "Freelance", "Zwroty", "Inne przychody")

#: The subscriptions tree (ADR 028): one flagged root and its direct children.
SUBSCRIPTIONS_ROOT = "Subskrypcje"
SUBSCRIPTION_CHILDREN = ("Miesięczne", "Roczne", "Inne")

BUDGETED_CATEGORIES = (
    "Żywność",
    "Mieszkanie & Czynsz",
    "Transport",
    "Media (prąd, gaz, woda)",
    "Zdrowie & Apteka",
    "Rozrywka",
    "Subskrypcje",
    "Odzież & Obuwie",
)

#: Today's monthly amounts; older months scale down with inflation.
BASE_BUDGETS: dict[str, Decimal] = {
    "Żywność": Decimal("1400.00"),
    "Mieszkanie & Czynsz": Decimal("2400.00"),
    "Transport": Decimal("350.00"),
    "Media (prąd, gaz, woda)": Decimal("280.00"),
    "Zdrowie & Apteka": Decimal("200.00"),
    "Rozrywka": Decimal("300.00"),
    "Subskrypcje": Decimal("120.00"),
    "Odzież & Obuwie": Decimal("250.00"),
}

#: Spending multiplier per calendar month — January frugal, December not.
SEASONAL: dict[int, float] = {
    1: 0.75,
    2: 0.85,
    3: 0.90,
    4: 0.95,
    5: 1.00,
    6: 1.05,
    7: 1.25,
    8: 1.30,
    9: 1.05,
    10: 0.95,
    11: 1.10,
    12: 1.50,
}

#: Curated Polish merchants per expense category. An expense in a mapped
#: category draws from its pool; see PAYEE_ASSIGN_CHANCE for how often.
CATEGORY_PAYEES: dict[str, tuple[str, ...]] = {
    "Żywność": ("Biedronka", "Lidl", "Carrefour", "Żabka", "Auchan"),
    "Restauracje & Kawiarnie": ("Pasibus", "Costa Coffee", "Da Grasso", "Sphinx", "Starbucks"),
    "Transport": ("MPK Warszawa", "Uber", "Bolt"),
    "Paliwo": ("Orlen", "Shell", "BP"),
    "Mieszkanie & Czynsz": ("Wspólnota Mieszkaniowa",),
    "Media (prąd, gaz, woda)": ("PGNiG", "Tauron", "Veolia", "MPWiK"),
    "Zdrowie & Apteka": ("Apteka Gemini", "Apteka DOZ", "Medicover"),
    "Subskrypcje": ("Netflix", "Spotify", "YouTube Premium", "iCloud", "ChatGPT Plus"),
    "Elektronika": ("Allegro", "Amazon.pl", "Empik"),
    "Rozrywka": ("Empik", "Allegro"),
    "Odzież & Obuwie": ("Allegro", "Amazon.pl"),
}

#: Merchants for the categories without a curated pool. Small local firms, so
#: the demo also shows the long tail a real ledger has.
FALLBACK_PAYEES = (
    "Usługi Kowalski",
    "Zakład Stolarski Nowak",
    "Biuro Rachunkowe Wiśniewska",
    "Serwis Rowerowy Dwa Koła",
    "Pracownia Szkoleń Lewandowski",
)

#: Merchants billed online — their expenses also get the `Online` tag.
ONLINE_MERCHANTS = frozenset(
    {
        "Allegro",
        "Amazon.pl",
        "Empik",
        "Netflix",
        "Spotify",
        "YouTube Premium",
        "iCloud",
        "ChatGPT Plus",
    }
)

#: Categories whose expenses may be returned → occasional `Refundable` tag.
REFUNDABLE_CATEGORIES = frozenset({"Restauracje & Kawiarnie", "Elektronika"})

#: Share of expenses in a curated category that name their merchant; the rest
#: stay payee-less so the demo also shows the "unknown merchant" case.
PAYEE_ASSIGN_CHANCE = 0.70
#: Same, for categories served by the fallback merchants.
FALLBACK_PAYEE_CHANCE = 0.30
#: Share of refundable-category (or online) expenses flagged `Refundable`.
REFUNDABLE_CHANCE = 0.10

#: Colours from the sand palette, not Material's ramp: a tag chip is drawn as
#: an outline in its own colour, and a grey one reads as "no tag" beside a
#: category pill. Mirrors the b9d4e2c8a1f5 migration.
CANONICAL_TAGS = (
    ("Transfer", "swap_horiz", "#4A443A"),
    ("Card", "credit_card", "#6B6353"),
    ("Cash", "payments", "#8A5A12"),
    ("Online", "language", "#9A4E1F"),
    ("Subscription", "autorenew", "#36684D"),
    ("Refundable", "assignment_return", "#A44631"),
    ("Business", "work", "#2A5540"),
    ("Recurring", "event_repeat", "#8E4718"),
)

#: What an expense row is called when nothing more specific fits.
CATCH_PHRASES = (
    "Zakupy spożywcze",
    "Paliwo",
    "Kino / Netflix",
    "Apteka",
    "Restauracja",
    "Odzież",
    "Kosmetyki",
    "Elektronika",
    "Siłownia",
    "Książki",
    "Kawiarnia",
    "Bilety",
    "Parking",
    "Fryzjer",
    "Leki",
    "Zabawki",
    "Ogród",
    "Materiały biurowe",
    "Prezent",
    "Usługi",
)

#: Cities a summer holiday goes to.
HOLIDAY_DESTINATIONS = ("Gdańsk", "Zakopane", "Kołobrzeg", "Kraków", "Karpacz", "Sopot")

ACCOUNT_NAMES = {
    "checking": "PKO Konto Główne",
    "savings": "mBank Oszczędności",
    "cash": "Gotówka",
    "credit": "Karta Kredytowa Visa",
}
