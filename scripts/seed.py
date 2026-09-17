# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed the database with 6 years of realistic fake data using Faker.

Run:
    uv run python scripts/seed.py
"""

import asyncio
import datetime
import random
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from faker import Faker

from kaleta.db.base import Base, engine
from kaleta.db.session import AsyncSessionFactory
from kaleta.models.account import Account, AccountType
from kaleta.models.asset import Asset, AssetType
from kaleta.models.budget import Budget
from kaleta.models.categorisation_rule import CategorisationRule, RuleMatchMode
from kaleta.models.category import Category, CategoryType
from kaleta.models.institution import Institution, InstitutionType
from kaleta.models.payee import Payee
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionType

fake = Faker("pl_PL")
random.seed(42)

YEARS = 6
MONTHS = YEARS * 12  # 72 months

EXPENSE_CATEGORIES = [
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
]
INCOME_CATEGORIES = ["Wynagrodzenie", "Freelance", "Zwroty", "Inne przychody"]

# Categories that get a monthly budget entry
BUDGETED_CATEGORIES = [
    "Żywność",
    "Mieszkanie & Czynsz",
    "Transport",
    "Media (prąd, gaz, woda)",
    "Zdrowie & Apteka",
    "Rozrywka",
    "Subskrypcje",
    "Odzież & Obuwie",
]

# Base monthly budget amounts (today's values; older months scale down for inflation)
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

# Seasonal spending multipliers per month (1-12)
SEASONAL: dict[int, float] = {
    1: 0.75,  # post-holiday savings
    2: 0.85,
    3: 0.90,
    4: 0.95,
    5: 1.00,
    6: 1.05,
    7: 1.25,  # summer vacation
    8: 1.30,  # summer vacation peak
    9: 1.05,  # back to school
    10: 0.95,
    11: 1.10,  # pre-Christmas shopping
    12: 1.50,  # Christmas
}


# ── Payees ───────────────────────────────────────────────────────────────────
# Curated Polish merchants per expense category. An expense in a mapped
# category draws from its pool; see PAYEE_ASSIGN_CHANCE for how often.
CATEGORY_PAYEES: dict[str, list[str]] = {
    "Żywność": ["Biedronka", "Lidl", "Carrefour", "Żabka", "Auchan"],
    "Restauracje & Kawiarnie": ["Pasibus", "Costa Coffee", "Da Grasso", "Sphinx", "Starbucks"],
    "Transport": ["MPK Warszawa", "Uber", "Bolt"],
    "Paliwo": ["Orlen", "Shell", "BP"],
    "Mieszkanie & Czynsz": ["Wspólnota Mieszkaniowa"],
    "Media (prąd, gaz, woda)": ["PGNiG", "Tauron", "Veolia", "MPWiK"],
    "Zdrowie & Apteka": ["Apteka Gemini", "Apteka DOZ", "Medicover"],
    "Subskrypcje": ["Netflix", "Spotify", "YouTube Premium", "iCloud", "ChatGPT Plus"],
    "Elektronika": ["Allegro", "Amazon.pl", "Empik"],
    "Rozrywka": ["Empik", "Allegro"],
    "Odzież & Obuwie": ["Allegro", "Amazon.pl"],
}

# Merchants billed online — their expenses also get the `Online` tag.
ONLINE_MERCHANTS = {
    "Allegro",
    "Amazon.pl",
    "Empik",
    "Netflix",
    "Spotify",
    "YouTube Premium",
    "iCloud",
    "ChatGPT Plus",
}

# Categories whose expenses may be returned → occasional `Refundable` tag.
REFUNDABLE_CATEGORIES = {"Restauracje & Kawiarnie", "Elektronika"}

# How many generated merchants back the categories without a curated pool.
FALLBACK_PAYEE_COUNT = 5
# Share of expenses in a curated category that name their merchant; the rest
# stay payee-less so the demo also shows the "unknown merchant" case.
PAYEE_ASSIGN_CHANCE = 0.70
# Same, for categories served by the generated fallback merchants.
FALLBACK_PAYEE_CHANCE = 0.30
# Share of refundable-category (or online) expenses flagged `Refundable`.
REFUNDABLE_CHANCE = 0.10


def month_offset(today: datetime.date, n: int) -> tuple[int, int]:
    """Return (year, month) for n months before today."""
    total = today.year * 12 + today.month - 1 - n
    return total // 12, total % 12 + 1


def inflation_factor(months_back: int, annual_rate: float = 0.045) -> float:
    """Prices were lower in the past: factor < 1 for older months."""
    years_back = months_back / 12
    return 1 / ((1 + annual_rate) ** years_back)


def salary_for_month(months_back: int) -> Decimal:
    """Salary grows ~5% per year; older months had lower pay."""
    base = 9000.0 * inflation_factor(months_back, annual_rate=0.05)
    jitter = random.uniform(0.95, 1.05)
    return Decimal(str(round(base * jitter, 2)))


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionFactory() as session:
        # ── Institutions ──────────────────────────────────────────────────────
        institutions = [
            Institution(
                name="PKO Bank Polski",
                type=InstitutionType.BANK,
                color="#003087",
                website="https://www.pkobp.pl",
                description="Największy bank w Polsce",
            ),
            Institution(
                name="mBank",
                type=InstitutionType.FINTECH,
                color="#e2001a",
                website="https://www.mbank.pl",
                description="Nowoczesny bank internetowy",
            ),
            Institution(
                name="Revolut",
                type=InstitutionType.FINTECH,
                color="#191c1f",
                website="https://www.revolut.com",
                description="Aplikacja finansowa — karty i wymiana walut",
            ),
        ]
        session.add_all(institutions)
        await session.flush()
        pko, mbank, revolut = institutions

        # ── Accounts ──────────────────────────────────────────────────────────
        accounts = [
            Account(
                name="PKO Konto Główne",
                type=AccountType.CHECKING,
                balance=Decimal("0.00"),
                institution_id=pko.id,
            ),
            Account(
                name="mBank Oszczędności",
                type=AccountType.SAVINGS,
                balance=Decimal("0.00"),
                institution_id=mbank.id,
            ),
            Account(
                name="Gotówka",
                type=AccountType.CASH,
                balance=Decimal("0.00"),
            ),
            Account(
                name="Karta Kredytowa Visa",
                type=AccountType.CREDIT,
                balance=Decimal("0.00"),
                institution_id=revolut.id,
            ),
        ]
        session.add_all(accounts)
        await session.flush()
        checking, savings, cash, credit = accounts

        # ── Canonical tags (mirrors b9d4e2c8a1f5 migration) ──────────────────
        canonical_tags = [
            Tag(name="Transfer", icon="swap_horiz"),
            Tag(name="Card", icon="credit_card"),
            Tag(name="Cash", icon="payments"),
            Tag(name="Online", icon="language"),
            Tag(name="Subscription", icon="autorenew"),
            Tag(name="Refundable", icon="assignment_return"),
            Tag(name="Business", icon="work"),
            Tag(name="Recurring", icon="event_repeat"),
        ]
        session.add_all(canonical_tags)
        await session.flush()
        tag_by_name = {t.name: t for t in canonical_tags}

        # ── Payees ───────────────────────────────────────────────────────────
        curated_names = sorted({n for pool in CATEGORY_PAYEES.values() for n in pool})
        # Payee.name is unique — keep drawing until the generated names are
        # distinct from each other and from the curated ones.
        fallback_names: list[str] = []
        while len(fallback_names) < FALLBACK_PAYEE_COUNT:
            name = fake.company()
            if name not in curated_names and name not in fallback_names:
                fallback_names.append(name)
        payees = [Payee(name=n) for n in curated_names + fallback_names]
        session.add_all(payees)
        await session.flush()
        payee_by_name = {p.name: p for p in payees}
        fallback_payees = [payee_by_name[n] for n in fallback_names]
        cat_to_payees = {
            cat_name: [payee_by_name[n] for n in names]
            for cat_name, names in CATEGORY_PAYEES.items()
        }

        # ── Categories ────────────────────────────────────────────────────────
        expense_cats = [Category(name=n, type=CategoryType.EXPENSE) for n in EXPENSE_CATEGORIES]
        income_cats = [Category(name=n, type=CategoryType.INCOME) for n in INCOME_CATEGORIES]
        # Subscriptions tree (root + three starter children). The root is
        # flagged so the Subscriptions panel recognises its descendants as
        # tracked charges.
        subscriptions_root = Category(
            name="Subskrypcje",
            type=CategoryType.EXPENSE,
            is_subscriptions_root=True,
        )
        session.add_all(expense_cats + income_cats + [subscriptions_root])
        await session.flush()
        subscription_children = [
            Category(name="Miesięczne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
            Category(name="Roczne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
            Category(name="Inne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
        ]
        session.add_all(subscription_children)
        await session.flush()

        cat_by_name = {c.name: c for c in expense_cats + income_cats}
        salary_cat = cat_by_name["Wynagrodzenie"]
        freelance_cat = cat_by_name["Freelance"]
        zwroty_cat = cat_by_name["Zwroty"]
        rent_cat = cat_by_name["Mieszkanie & Czynsz"]
        food_cat = cat_by_name["Żywność"]

        # ── Demo categorisation rule (LIDL → Żywność) ─────────────────────────
        session.add(
            CategorisationRule(
                pattern="LIDL",
                match_mode=RuleMatchMode.CONTAINS,
                category_id=food_cat.id,
                is_active=True,
                priority=0,
            )
        )
        await session.flush()

        # ── Transactions ──────────────────────────────────────────────────────
        today = datetime.date.today()
        all_tx: list[Transaction] = []
        balance_delta: dict[int, Decimal] = defaultdict(Decimal)
        # Summary counters — kept as we go, because reading `tx.tags` back off
        # a flushed row would need a lazy load the sync print cannot await.
        counts = {"payee": 0, "tagged": 0}

        # Both EXPENSE categories named "Subskrypcje" count as subscription
        # spend: the flat one (used by the budgets and the expense loop) and
        # the tree the Subscriptions panel reads.
        subscription_cat_ids = {
            subscriptions_root.id,
            cat_by_name["Subskrypcje"].id,
            *(c.id for c in subscription_children),
        }

        def pick_payee(cat_name: str) -> Payee | None:
            """Merchant for an expense, or None — not every row names one."""
            pool = cat_to_payees.get(cat_name)
            if pool is not None:
                return random.choice(pool) if random.random() < PAYEE_ASSIGN_CHANCE else None
            return (
                random.choice(fallback_payees) if random.random() < FALLBACK_PAYEE_CHANCE else None
            )

        def expense_tags(account: Account, cat: Category, payee: Payee | None) -> list[Tag]:
            """How the expense was paid, plus what kind of spend it is."""
            is_online = payee is not None and payee.name in ONLINE_MERCHANTS
            tags = [tag_by_name["Cash" if account.type == AccountType.CASH else "Card"]]
            if is_online:
                tags.append(tag_by_name["Online"])
            if cat.id in subscription_cat_ids:
                tags.append(tag_by_name["Subscription"])
                tags.append(tag_by_name["Recurring"])
            if (
                cat.name in REFUNDABLE_CATEGORIES or is_online
            ) and random.random() < REFUNDABLE_CHANCE:
                tags.append(tag_by_name["Refundable"])
            return tags

        def add_tx(
            tx: Transaction, *, payee: Payee | None = None, tags: list[Tag] | None = None
        ) -> None:
            if payee is not None:
                tx.payee_id = payee.id
            # In the session before the tags are linked: the tags are already
            # persistent, and appending to a detached row's collection would
            # drop the association silently.
            session.add(tx)
            if payee is not None:
                counts["payee"] += 1
            if tags:
                tx.tags.extend(tags)
                counts["tagged"] += 1
            all_tx.append(tx)
            if tx.type == TransactionType.INCOME:
                balance_delta[tx.account_id] += tx.amount
            elif tx.type == TransactionType.EXPENSE:
                balance_delta[tx.account_id] -= tx.amount

        def add_expense(tx: Transaction, account: Account, cat: Category) -> None:
            """Add an expense with its merchant and tag fan-out attached."""
            payee = pick_payee(cat.name)
            add_tx(tx, payee=payee, tags=expense_tags(account, cat, payee))

        all_budgets: list[Budget] = []

        for m in range(MONTHS):
            year, month = month_offset(today, m)
            seasonal = SEASONAL[month]
            inf = inflation_factor(m)

            # ── Salary ────────────────────────────────────────────────────────
            add_tx(
                Transaction(
                    account_id=checking.id,
                    category_id=salary_cat.id,
                    amount=salary_for_month(m),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, 1),
                    description=f"Wynagrodzenie {month:02d}/{year}",
                )
            )

            # ── Rent ──────────────────────────────────────────────────────────
            rent_amount = Decimal(str(round(float(BASE_BUDGETS["Mieszkanie & Czynsz"]) * inf, 2)))
            add_expense(
                Transaction(
                    account_id=checking.id,
                    category_id=rent_cat.id,
                    amount=rent_amount,
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, 5),
                    description="Czynsz za mieszkanie",
                ),
                checking,
                rent_cat,
            )

            # ── Random expenses (seasonal) ────────────────────────────────────
            n_expenses = random.randint(12, 22)
            for _ in range(n_expenses):
                cat = random.choice(expense_cats)
                base_amount = random.uniform(8, 600)
                amount = Decimal(str(round(base_amount * seasonal * inf, 2)))
                account = random.choice([checking, cash, credit])
                add_expense(
                    Transaction(
                        account_id=account.id,
                        category_id=cat.id,
                        amount=amount,
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, random.randint(1, 28)),
                        description=fake.catch_phrase(),
                    ),
                    account,
                    cat,
                )

            # ── Big annual purchases (vacation Jul/Aug, electronics Nov/Dec) ──
            if month in (7, 8) and random.random() < 0.6:
                vacation_cat = cat_by_name["Wakacje & Podróże"]
                add_expense(
                    Transaction(
                        account_id=checking.id,
                        category_id=vacation_cat.id,
                        amount=Decimal(str(round(random.uniform(1500, 5000) * inf, 2))),
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, random.randint(1, 20)),
                        description=fake.city() + " — wakacje",
                    ),
                    checking,
                    vacation_cat,
                )

            if month == 12 and random.random() < 0.5:
                electronics_cat = cat_by_name["Elektronika"]
                add_expense(
                    Transaction(
                        account_id=credit.id,
                        category_id=electronics_cat.id,
                        amount=Decimal(str(round(random.uniform(800, 3500) * inf, 2))),
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, random.randint(10, 23)),
                        description="Prezenty świąteczne / elektronika",
                    ),
                    credit,
                    electronics_cat,
                )

            # ── Occasional freelance ───────────────────────────────────────────
            if random.random() < 0.35:
                add_tx(
                    Transaction(
                        account_id=checking.id,
                        category_id=freelance_cat.id,
                        amount=Decimal(str(round(random.uniform(400, 4000) * inf, 2))),
                        type=TransactionType.INCOME,
                        date=datetime.date(year, month, random.randint(10, 25)),
                        description="Faktura freelance",
                    )
                )

            # ── Occasional refund ─────────────────────────────────────────────
            if random.random() < 0.15:
                add_tx(
                    Transaction(
                        account_id=checking.id,
                        category_id=zwroty_cat.id,
                        amount=Decimal(str(round(random.uniform(20, 300) * inf, 2))),
                        type=TransactionType.INCOME,
                        date=datetime.date(year, month, random.randint(1, 28)),
                        description="Zwrot / reklamacja",
                    )
                )

            # ── Internal transfer: checking → savings ─────────────────────────
            t_amount = Decimal(str(round(random.uniform(300, 1500) * inf, 2)))
            t_date = datetime.date(year, month, 15)
            t_out = Transaction(
                account_id=checking.id,
                category_id=None,
                amount=t_amount,
                type=TransactionType.TRANSFER,
                date=t_date,
                description=f"Przelew własny → oszczędności {month:02d}/{year}",
                is_internal_transfer=True,
            )
            t_in = Transaction(
                account_id=savings.id,
                category_id=None,
                amount=t_amount,
                type=TransactionType.TRANSFER,
                date=t_date,
                description=f"Przelew własny ← konto główne {month:02d}/{year}",
                is_internal_transfer=True,
            )
            t_out.tags.append(tag_by_name["Transfer"])
            t_in.tags.append(tag_by_name["Transfer"])
            session.add(t_out)
            session.add(t_in)
            await session.flush()
            t_out.linked_transaction_id = t_in.id
            t_in.linked_transaction_id = t_out.id
            balance_delta[checking.id] -= t_amount
            balance_delta[savings.id] += t_amount

            # ── Monthly budgets ───────────────────────────────────────────────
            for cat_name in BUDGETED_CATEGORIES:
                base = BASE_BUDGETS[cat_name]
                amount = Decimal(str(round(float(base) * inf, 2)))
                all_budgets.append(
                    Budget(
                        category_id=cat_by_name[cat_name].id,
                        amount=amount,
                        month=month,
                        year=year,
                    )
                )

        session.add_all(all_budgets)

        # Apply computed balances to accounts
        for account in accounts:
            account.balance = balance_delta[account.id]

        # ── Physical assets ───────────────────────────────────────────────────
        physical_assets = [
            Asset(
                name="Mieszkanie (Warszawa)",
                type=AssetType.REAL_ESTATE,
                value=Decimal("620000.00"),
                description="Mieszkanie 52m² na Mokotowie, zakupione w 2021",
                purchase_date=datetime.date(2021, 6, 15),
                purchase_price=Decimal("480000.00"),
            ),
            Asset(
                name="Toyota Corolla 2020",
                type=AssetType.VEHICLE,
                value=Decimal("68000.00"),
                description="Toyota Corolla Hybrid 1.8, rok 2020, przebieg 55k km",
                purchase_date=datetime.date(2020, 3, 10),
                purchase_price=Decimal("95000.00"),
            ),
            Asset(
                name="Zegarek Seiko",
                type=AssetType.VALUABLES,
                value=Decimal("4500.00"),
                description="Seiko Prospex, edycja limitowana",
            ),
        ]
        session.add_all(physical_assets)

        n_payees = len(payees)

        await session.commit()

    transfer_pairs = MONTHS * 2
    total_tx = len(all_tx) + transfer_pairs
    # Both transfer legs carry the Transfer tag.
    tagged_tx = counts["tagged"] + transfer_pairs
    with_payee = counts["payee"]
    print(
        f"[OK] Seeded {len(institutions)} institutions, "
        f"{len(accounts)} accounts, "
        f"{len(EXPENSE_CATEGORIES + INCOME_CATEGORIES)} categories, "
        f"{n_payees} payees, "
        f"~{total_tx} transactions "
        f"({with_payee} with a payee, {tagged_tx} tagged), "
        f"{len(all_budgets)} budget entries ({YEARS} years), "
        f"{len(physical_assets)} physical assets."
    )


if __name__ == "__main__":
    asyncio.run(seed())
