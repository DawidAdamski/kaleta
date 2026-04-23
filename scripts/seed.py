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
from kaleta.models.category import Category, CategoryType
from kaleta.models.institution import Institution, InstitutionType
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionType

fake = Faker("pl_PL")
random.seed(42)

YEARS = 6
MONTHS = YEARS * 12  # 72 months

EXPENSE_CATEGORIES = [
    "Żywność", "Restauracje & Kawiarnie", "Transport", "Paliwo",
    "Mieszkanie & Czynsz", "Media (prąd, gaz, woda)", "Zdrowie & Apteka",
    "Rozrywka", "Odzież & Obuwie", "Elektronika", "Sport & Fitness",
    "Edukacja", "Subskrypcje", "Wakacje & Podróże", "Inne wydatki",
]
INCOME_CATEGORIES = ["Wynagrodzenie", "Freelance", "Zwroty", "Inne przychody"]

# Categories that get a monthly budget entry
BUDGETED_CATEGORIES = [
    "Żywność", "Mieszkanie & Czynsz", "Transport", "Media (prąd, gaz, woda)",
    "Zdrowie & Apteka", "Rozrywka", "Subskrypcje", "Odzież & Obuwie",
]

# Base monthly budget amounts (today's values; older months scale down for inflation)
BASE_BUDGETS: dict[str, Decimal] = {
    "Żywność":               Decimal("1400.00"),
    "Mieszkanie & Czynsz":   Decimal("2400.00"),
    "Transport":             Decimal("350.00"),
    "Media (prąd, gaz, woda)": Decimal("280.00"),
    "Zdrowie & Apteka":      Decimal("200.00"),
    "Rozrywka":              Decimal("300.00"),
    "Subskrypcje":           Decimal("120.00"),
    "Odzież & Obuwie":       Decimal("250.00"),
}

# Seasonal spending multipliers per month (1-12)
SEASONAL: dict[int, float] = {
    1: 0.75,   # post-holiday savings
    2: 0.85,
    3: 0.90,
    4: 0.95,
    5: 1.00,
    6: 1.05,
    7: 1.25,   # summer vacation
    8: 1.30,   # summer vacation peak
    9: 1.05,   # back to school
    10: 0.95,
    11: 1.10,  # pre-Christmas shopping
    12: 1.50,  # Christmas
}


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
            Account(name="PKO Konto Główne",     type=AccountType.CHECKING, balance=Decimal("0.00"), institution_id=pko.id),
            Account(name="mBank Oszczędności",   type=AccountType.SAVINGS,  balance=Decimal("0.00"), institution_id=mbank.id),
            Account(name="Gotówka",              type=AccountType.CASH,     balance=Decimal("0.00")),
            Account(name="Karta Kredytowa Visa", type=AccountType.CREDIT,   balance=Decimal("0.00"), institution_id=revolut.id),
        ]
        session.add_all(accounts)
        await session.flush()
        checking, savings, cash, credit = accounts

        # ── Canonical tags (mirrors b9d4e2c8a1f5 migration) ──────────────────
        session.add_all([
            Tag(name="Transfer",     icon="swap_horiz"),
            Tag(name="Card",         icon="credit_card"),
            Tag(name="Cash",         icon="payments"),
            Tag(name="Online",       icon="language"),
            Tag(name="Subscription", icon="autorenew"),
            Tag(name="Refundable",   icon="assignment_return"),
            Tag(name="Business",     icon="work"),
            Tag(name="Recurring",    icon="event_repeat"),
        ])
        await session.flush()

        # ── Categories ────────────────────────────────────────────────────────
        expense_cats = [Category(name=n, type=CategoryType.EXPENSE) for n in EXPENSE_CATEGORIES]
        income_cats  = [Category(name=n, type=CategoryType.INCOME)  for n in INCOME_CATEGORIES]
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
        session.add_all([
            Category(name="Miesięczne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
            Category(name="Roczne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
            Category(name="Inne", type=CategoryType.EXPENSE, parent_id=subscriptions_root.id),
        ])
        await session.flush()

        cat_by_name = {c.name: c for c in expense_cats + income_cats}
        salary_cat   = cat_by_name["Wynagrodzenie"]
        freelance_cat = cat_by_name["Freelance"]
        zwroty_cat   = cat_by_name["Zwroty"]
        rent_cat     = cat_by_name["Mieszkanie & Czynsz"]

        # ── Transactions ──────────────────────────────────────────────────────
        today = datetime.date.today()
        all_tx: list[Transaction] = []
        balance_delta: dict[int, Decimal] = defaultdict(Decimal)

        def add_tx(tx: Transaction) -> None:
            all_tx.append(tx)
            if tx.type == TransactionType.INCOME:
                balance_delta[tx.account_id] += tx.amount
            elif tx.type == TransactionType.EXPENSE:
                balance_delta[tx.account_id] -= tx.amount

        all_budgets: list[Budget] = []

        for m in range(MONTHS):
            year, month = month_offset(today, m)
            seasonal = SEASONAL[month]
            inf = inflation_factor(m)

            # ── Salary ────────────────────────────────────────────────────────
            add_tx(Transaction(
                account_id=checking.id, category_id=salary_cat.id,
                amount=salary_for_month(m), type=TransactionType.INCOME,
                date=datetime.date(year, month, 1),
                description=f"Wynagrodzenie {month:02d}/{year}",
            ))

            # ── Rent ──────────────────────────────────────────────────────────
            rent_amount = Decimal(str(round(float(BASE_BUDGETS["Mieszkanie & Czynsz"]) * inf, 2)))
            add_tx(Transaction(
                account_id=checking.id, category_id=rent_cat.id,
                amount=rent_amount, type=TransactionType.EXPENSE,
                date=datetime.date(year, month, 5),
                description="Czynsz za mieszkanie",
            ))

            # ── Random expenses (seasonal) ────────────────────────────────────
            n_expenses = random.randint(12, 22)
            for _ in range(n_expenses):
                cat = random.choice(expense_cats)
                base_amount = random.uniform(8, 600)
                amount = Decimal(str(round(base_amount * seasonal * inf, 2)))
                account = random.choice([checking, cash, credit])
                add_tx(Transaction(
                    account_id=account.id, category_id=cat.id,
                    amount=amount, type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, random.randint(1, 28)),
                    description=fake.catch_phrase(),
                ))

            # ── Big annual purchases (vacation Jul/Aug, electronics Nov/Dec) ──
            if month in (7, 8) and random.random() < 0.6:
                vacation_cat = cat_by_name["Wakacje & Podróże"]
                add_tx(Transaction(
                    account_id=checking.id, category_id=vacation_cat.id,
                    amount=Decimal(str(round(random.uniform(1500, 5000) * inf, 2))),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, random.randint(1, 20)),
                    description=fake.city() + " — wakacje",
                ))

            if month == 12 and random.random() < 0.5:
                electronics_cat = cat_by_name["Elektronika"]
                add_tx(Transaction(
                    account_id=credit.id, category_id=electronics_cat.id,
                    amount=Decimal(str(round(random.uniform(800, 3500) * inf, 2))),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, random.randint(10, 23)),
                    description="Prezenty świąteczne / elektronika",
                ))

            # ── Occasional freelance ───────────────────────────────────────────
            if random.random() < 0.35:
                add_tx(Transaction(
                    account_id=checking.id, category_id=freelance_cat.id,
                    amount=Decimal(str(round(random.uniform(400, 4000) * inf, 2))),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, random.randint(10, 25)),
                    description="Faktura freelance",
                ))

            # ── Occasional refund ─────────────────────────────────────────────
            if random.random() < 0.15:
                add_tx(Transaction(
                    account_id=checking.id, category_id=zwroty_cat.id,
                    amount=Decimal(str(round(random.uniform(20, 300) * inf, 2))),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, random.randint(1, 28)),
                    description="Zwrot / reklamacja",
                ))

            # ── Internal transfer: checking → savings ─────────────────────────
            t_amount = Decimal(str(round(random.uniform(300, 1500) * inf, 2)))
            t_date   = datetime.date(year, month, 15)
            t_out = Transaction(
                account_id=checking.id, category_id=None,
                amount=t_amount, type=TransactionType.TRANSFER,
                date=t_date, description=f"Przelew własny → oszczędności {month:02d}/{year}",
                is_internal_transfer=True,
            )
            t_in = Transaction(
                account_id=savings.id, category_id=None,
                amount=t_amount, type=TransactionType.TRANSFER,
                date=t_date, description=f"Przelew własny ← konto główne {month:02d}/{year}",
                is_internal_transfer=True,
            )
            session.add(t_out)
            session.add(t_in)
            await session.flush()
            t_out.linked_transaction_id = t_in.id
            t_in.linked_transaction_id  = t_out.id
            balance_delta[checking.id] -= t_amount
            balance_delta[savings.id]  += t_amount

            # ── Monthly budgets ───────────────────────────────────────────────
            for cat_name in BUDGETED_CATEGORIES:
                base = BASE_BUDGETS[cat_name]
                amount = Decimal(str(round(float(base) * inf, 2)))
                all_budgets.append(Budget(
                    category_id=cat_by_name[cat_name].id,
                    amount=amount,
                    month=month,
                    year=year,
                ))

        session.add_all(all_tx)
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

        await session.commit()

    transfer_pairs = MONTHS * 2
    total_tx = len(all_tx) + transfer_pairs
    print(
        f"[OK] Seeded {len(institutions)} institutions, "
        f"{len(accounts)} accounts, "
        f"{len(EXPENSE_CATEGORIES + INCOME_CATEGORIES)} categories, "
        f"~{total_tx} transactions, "
        f"{len(all_budgets)} budget entries ({YEARS} years), "
        f"{len(physical_assets)} physical assets."
    )


if __name__ == "__main__":
    asyncio.run(seed())
