"""DataService — clear all data and/or seed with realistic example data.

Used by the Settings page for the "Populate with example data" and
"Clear all data" developer/demo actions.
"""
from __future__ import annotations

import datetime
import random
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account, AccountType
from kaleta.models.asset import Asset, AssetType
from kaleta.models.audit_log import AuditLog
from kaleta.models.budget import Budget
from kaleta.models.category import Category, CategoryType
from kaleta.models.currency_rate import CurrencyRate
from kaleta.models.institution import Institution, InstitutionType
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.report import SavedReport
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionSplit, TransactionType

# ── seed constants (same data as scripts/seed.py) ─────────────────────────────

_YEARS = 6
_MONTHS = _YEARS * 12

_EXPENSE_CATEGORIES = [
    "Żywność", "Restauracje & Kawiarnie", "Transport", "Paliwo",
    "Mieszkanie & Czynsz", "Media (prąd, gaz, woda)", "Zdrowie & Apteka",
    "Rozrywka", "Odzież & Obuwie", "Elektronika", "Sport & Fitness",
    "Edukacja", "Subskrypcje", "Wakacje & Podróże", "Inne wydatki",
]
_INCOME_CATEGORIES = ["Wynagrodzenie", "Freelance", "Zwroty", "Inne przychody"]
_BUDGETED_CATEGORIES = [
    "Żywność", "Mieszkanie & Czynsz", "Transport", "Media (prąd, gaz, woda)",
    "Zdrowie & Apteka", "Rozrywka", "Subskrypcje", "Odzież & Obuwie",
]
_BASE_BUDGETS: dict[str, Decimal] = {
    "Żywność":                  Decimal("1400.00"),
    "Mieszkanie & Czynsz":      Decimal("2400.00"),
    "Transport":                Decimal("350.00"),
    "Media (prąd, gaz, woda)":  Decimal("280.00"),
    "Zdrowie & Apteka":         Decimal("200.00"),
    "Rozrywka":                 Decimal("300.00"),
    "Subskrypcje":              Decimal("120.00"),
    "Odzież & Obuwie":          Decimal("250.00"),
}
_SEASONAL: dict[int, float] = {
    1: 0.75, 2: 0.85, 3: 0.90, 4: 0.95, 5: 1.00, 6: 1.05,
    7: 1.25, 8: 1.30, 9: 1.05, 10: 0.95, 11: 1.10, 12: 1.50,
}
_CATCH_PHRASES = [
    "Zakupy spożywcze", "Paliwo", "Kino / Netflix", "Apteka", "Restauracja",
    "Odzież", "Kosmetyki", "Elektronika", "Siłownia", "Książki",
    "Kawiarnia", "Bilety", "Parking", "Fryzjer", "Leki",
    "Zabawki", "Ogród", "Materiały biurowe", "Prezent", "Usługi",
]


def _month_offset(today: datetime.date, n: int) -> tuple[int, int]:
    total = today.year * 12 + today.month - 1 - n
    return total // 12, total % 12 + 1


def _inflation(months_back: int, annual: float = 0.045) -> float:
    return 1.0 / ((1 + annual) ** (months_back / 12))


def _salary(months_back: int) -> Decimal:
    base = 9000.0 * _inflation(months_back, annual=0.05)
    return Decimal(str(round(base * random.uniform(0.95, 1.05), 2)))


# ── service ───────────────────────────────────────────────────────────────────


class DataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clear_all(self) -> None:
        """Delete every row from every table, preserving the schema."""
        s = self.session
        # Disable FK checks for SQLite so we don't need a precise order
        await s.execute(text("PRAGMA foreign_keys = OFF"))
        for model in (
            TransactionSplit,
            Transaction,
            Budget,
            PlannedTransaction,
            CurrencyRate,
            AuditLog,
            Asset,
            SavedReport,
            Tag,
            Account,
            Category,
            Institution,
            Payee,
        ):
            await s.execute(delete(model))
        # Clear the many-to-many join table
        await s.execute(text("DELETE FROM transaction_tags"))
        await s.execute(text("PRAGMA foreign_keys = ON"))
        await s.commit()

    async def seed(self) -> dict[str, int]:
        """Clear all data then insert 6 years of realistic Polish-language demo data."""
        rng = random.Random(42)
        await self.clear_all()
        s = self.session

        # ── institutions ──────────────────────────────────────────────────────
        institutions = [
            Institution(
                name="PKO Bank Polski", type=InstitutionType.BANK,
                color="#003087", website="https://www.pkobp.pl",
                description="Największy bank w Polsce",
            ),
            Institution(
                name="mBank", type=InstitutionType.FINTECH,
                color="#e2001a", website="https://www.mbank.pl",
                description="Nowoczesny bank internetowy",
            ),
            Institution(
                name="Revolut", type=InstitutionType.FINTECH,
                color="#191c1f", website="https://www.revolut.com",
                description="Aplikacja finansowa — karty i wymiana walut",
            ),
        ]
        s.add_all(institutions)
        await s.flush()
        pko, mbank, revolut = institutions

        # ── accounts ──────────────────────────────────────────────────────────
        accounts = [
            Account(name="PKO Konto Główne",     type=AccountType.CHECKING,
                    balance=Decimal("0.00"), institution_id=pko.id),
            Account(name="mBank Oszczędności",   type=AccountType.SAVINGS,
                    balance=Decimal("0.00"), institution_id=mbank.id),
            Account(name="Gotówka",              type=AccountType.CASH,
                    balance=Decimal("0.00")),
            Account(name="Karta Kredytowa Visa", type=AccountType.CREDIT,
                    balance=Decimal("0.00"), institution_id=revolut.id),
        ]
        s.add_all(accounts)
        await s.flush()
        checking, savings, cash, credit = accounts

        # ── categories ────────────────────────────────────────────────────────
        expense_cats = [Category(name=n, type=CategoryType.EXPENSE) for n in _EXPENSE_CATEGORIES]
        income_cats  = [Category(name=n, type=CategoryType.INCOME)  for n in _INCOME_CATEGORIES]
        s.add_all(expense_cats + income_cats)
        await s.flush()

        by_name      = {c.name: c for c in expense_cats + income_cats}
        salary_cat   = by_name["Wynagrodzenie"]
        freelance_cat = by_name["Freelance"]
        zwroty_cat   = by_name["Zwroty"]
        rent_cat     = by_name["Mieszkanie & Czynsz"]
        vacation_cat = by_name["Wakacje & Podróże"]
        electronics_cat = by_name["Elektronika"]

        # ── transactions + budgets ────────────────────────────────────────────
        today = datetime.date.today()
        all_tx: list[Transaction] = []
        all_budgets: list[Budget] = []
        balance_delta: dict[int, Decimal] = defaultdict(Decimal)

        def add_tx(tx: Transaction) -> None:
            all_tx.append(tx)
            if tx.type == TransactionType.INCOME:
                balance_delta[tx.account_id] += tx.amount
            elif tx.type == TransactionType.EXPENSE:
                balance_delta[tx.account_id] -= tx.amount

        for m in range(_MONTHS):
            year, month = _month_offset(today, m)
            seasonal = _SEASONAL[month]
            inf = _inflation(m)

            add_tx(Transaction(
                account_id=checking.id, category_id=salary_cat.id,
                amount=_salary(m), type=TransactionType.INCOME,
                date=datetime.date(year, month, 1),
                description=f"Wynagrodzenie {month:02d}/{year}",
            ))

            rent_amount = Decimal(str(round(
                float(_BASE_BUDGETS["Mieszkanie & Czynsz"]) * inf, 2
            )))
            add_tx(Transaction(
                account_id=checking.id, category_id=rent_cat.id,
                amount=rent_amount, type=TransactionType.EXPENSE,
                date=datetime.date(year, month, 5),
                description="Czynsz za mieszkanie",
            ))

            for _ in range(rng.randint(12, 22)):
                cat = rng.choice(expense_cats)
                amount = Decimal(str(round(
                    rng.uniform(8, 600) * seasonal * inf, 2
                )))
                add_tx(Transaction(
                    account_id=rng.choice([checking, cash, credit]).id,
                    category_id=cat.id,
                    amount=amount, type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, rng.randint(1, 28)),
                    description=rng.choice(_CATCH_PHRASES),
                ))

            if month in (7, 8) and rng.random() < 0.6:
                add_tx(Transaction(
                    account_id=checking.id, category_id=vacation_cat.id,
                    amount=Decimal(str(round(rng.uniform(1500, 5000) * inf, 2))),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, rng.randint(1, 20)),
                    description="Wyjazd wakacyjny",
                ))

            if month == 12 and rng.random() < 0.5:
                add_tx(Transaction(
                    account_id=credit.id, category_id=electronics_cat.id,
                    amount=Decimal(str(round(rng.uniform(800, 3500) * inf, 2))),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, rng.randint(10, 23)),
                    description="Prezenty świąteczne / elektronika",
                ))

            if rng.random() < 0.35:
                add_tx(Transaction(
                    account_id=checking.id, category_id=freelance_cat.id,
                    amount=Decimal(str(round(rng.uniform(400, 4000) * inf, 2))),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, rng.randint(10, 25)),
                    description="Faktura freelance",
                ))

            if rng.random() < 0.15:
                add_tx(Transaction(
                    account_id=checking.id, category_id=zwroty_cat.id,
                    amount=Decimal(str(round(rng.uniform(20, 300) * inf, 2))),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, rng.randint(1, 28)),
                    description="Zwrot / reklamacja",
                ))

            # internal transfer checking → savings
            t_amount = Decimal(str(round(rng.uniform(300, 1500) * inf, 2)))
            t_date = datetime.date(year, month, 15)
            t_out = Transaction(
                account_id=checking.id, category_id=None,
                amount=t_amount, type=TransactionType.TRANSFER, date=t_date,
                description=f"Przelew własny → oszczędności {month:02d}/{year}",
                is_internal_transfer=True,
            )
            t_in = Transaction(
                account_id=savings.id, category_id=None,
                amount=t_amount, type=TransactionType.TRANSFER, date=t_date,
                description=f"Przelew własny ← konto główne {month:02d}/{year}",
                is_internal_transfer=True,
            )
            s.add(t_out)
            s.add(t_in)
            await s.flush()
            t_out.linked_transaction_id = t_in.id
            t_in.linked_transaction_id = t_out.id
            balance_delta[checking.id] -= t_amount
            balance_delta[savings.id] += t_amount

            for cat_name in _BUDGETED_CATEGORIES:
                all_budgets.append(Budget(
                    category_id=by_name[cat_name].id,
                    amount=Decimal(str(round(float(_BASE_BUDGETS[cat_name]) * inf, 2))),
                    month=month, year=year,
                ))

        s.add_all(all_tx)
        s.add_all(all_budgets)

        for account in accounts:
            account.balance = balance_delta[account.id]

        # ── physical assets ───────────────────────────────────────────────────
        assets = [
            Asset(
                name="Mieszkanie (Warszawa)", type=AssetType.REAL_ESTATE,
                value=Decimal("620000.00"),
                description="Mieszkanie 52m² na Mokotowie, zakupione w 2021",
                purchase_date=datetime.date(2021, 6, 15),
                purchase_price=Decimal("480000.00"),
            ),
            Asset(
                name="Toyota Corolla 2020", type=AssetType.VEHICLE,
                value=Decimal("68000.00"),
                description="Toyota Corolla Hybrid 1.8, rok 2020",
                purchase_date=datetime.date(2020, 3, 10),
                purchase_price=Decimal("95000.00"),
            ),
            Asset(
                name="Zegarek Seiko", type=AssetType.VALUABLES,
                value=Decimal("4500.00"),
                description="Seiko Prospex, edycja limitowana",
            ),
        ]
        s.add_all(assets)

        await s.commit()

        # Clear audit log entries created during seed (they're noise)
        await s.execute(delete(AuditLog))
        await s.commit()

        return {
            "institutions": len(institutions),
            "accounts": len(accounts),
            "categories": len(expense_cats) + len(income_cats),
            "transactions": len(all_tx) + _MONTHS * 2,
            "budgets": len(all_budgets),
            "assets": len(assets),
        }
