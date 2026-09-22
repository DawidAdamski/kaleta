# SPDX-License-Identifier: AGPL-3.0-or-later
"""The commitments the payment calendar, the upcoming widget and the forecast read.

Monthly series start in the current month so all three have occurrences inside
the next 60 days on a fresh install; occurrences already past are skipped when
the window is generated. Two rows are deliberately already late — the overdue
strip and the Overdue card exist for exactly that state, and a seed in which
nothing is ever late leaves both untestable.
"""

from __future__ import annotations

import calendar
import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.seeders.base import Seeder, month_offset, rng, row_count, salary
from kaleta.seeders.catalog import BASE_BUDGETS
from kaleta.seeders.lookups import accounts_by_kind, categories_by_name, subscription_child

#: The five monthly subscriptions that mirror the curated subscription payees.
_SUBSCRIPTIONS = (
    ("Netflix", Decimal("22.00"), 3),
    ("Spotify", Decimal("23.00"), 7),
    ("YouTube Premium", Decimal("35.00"), 14),
    ("iCloud", Decimal("8.00"), 18),
    ("ChatGPT Plus", Decimal("99.00"), 27),
)


class PlannedTransactionsSeeder(Seeder):
    key = "planned"
    depends_on = ("taxonomy", "accounts")
    icon = "event_repeat"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, PlannedTransaction)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        accounts = await accounts_by_kind(session)
        categories = await categories_by_name(session)
        monthly = await subscription_child(session, "Miesięczne")
        yearly = await subscription_child(session, "Roczne")
        checking = accounts["checking"]
        cash = accounts["cash"]
        credit = accounts["credit"]

        today = datetime.date.today()

        def this_month_on(day: int) -> datetime.date:
            return datetime.date(today.year, today.month, day)

        # month_offset counts backwards, so -1 is next month.
        next_month_year, next_month = month_offset(today, -1)
        next_quarter_month = (today.month - 1) // 3 * 3 + 4
        next_quarter = (
            datetime.date(today.year + 1, 1, 1)
            if next_quarter_month > 12
            else datetime.date(today.year, next_quarter_month, 1)
        )
        media = categories["Media (prąd, gaz, woda)"]

        rows = [
            PlannedTransaction(
                name="Czynsz",
                amount=BASE_BUDGETS["Mieszkanie & Czynsz"],
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=categories["Mieszkanie & Czynsz"].id,
                description="Czynsz za mieszkanie — płatny na początku miesiąca",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(next_month_year, next_month, 1),
            ),
            PlannedTransaction(
                name="Media (prąd, gaz, woda)",
                amount=Decimal("280.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=media.id,
                description="Zbiorczy rachunek za media",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=this_month_on(12),
            ),
            PlannedTransaction(
                name="Internet",
                amount=Decimal("79.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=media.id,
                description="Abonament światłowodowy",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=this_month_on(8),
            ),
            PlannedTransaction(
                name="Telefon",
                amount=Decimal("49.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=monthly.id,
                description="Abonament komórkowy",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=this_month_on(22),
            ),
            PlannedTransaction(
                name="Wynagrodzenie",
                amount=salary(0, rng(salt=2)),
                type=TransactionType.INCOME,
                account_id=checking.id,
                category_id=categories["Wynagrodzenie"].id,
                description="Pensja — przelew pierwszego dnia miesiąca",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=this_month_on(1),
            ),
            PlannedTransaction(
                name="Ubezpieczenie",
                amount=Decimal("420.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=categories["Inne wydatki"].id,
                description="Składka kwartalna — ubezpieczenie mieszkania",
                frequency=RecurrenceFrequency.QUARTERLY,
                start_date=next_quarter,
            ),
            PlannedTransaction(
                name="Domena",
                amount=Decimal("60.00"),
                type=TransactionType.EXPENSE,
                account_id=credit.id,
                category_id=yearly.id,
                description="Odnowienie domeny — raz w roku",
                frequency=RecurrenceFrequency.YEARLY,
                start_date=datetime.date(today.year + 1, 2, 1),
            ),
            PlannedTransaction(
                name="Wizyta u lekarza",
                amount=Decimal("180.00"),
                type=TransactionType.EXPENSE,
                account_id=cash.id,
                category_id=categories["Zdrowie & Apteka"].id,
                description="Umówiona wizyta — jednorazowo",
                frequency=RecurrenceFrequency.ONCE,
                start_date=today + datetime.timedelta(days=9),
            ),
        ]

        rows += [
            PlannedTransaction(
                name=name,
                amount=amount,
                type=TransactionType.EXPENSE,
                account_id=credit.id,
                category_id=monthly.id,
                description=f"Subskrypcja {name} — miesięcznie",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=this_month_on(day),
            )
            for name, amount, day in _SUBSCRIPTIONS
        ]

        prev_year, prev_month = month_offset(today, 1)
        prev_last_day = calendar.monthrange(prev_year, prev_month)[1]
        rows += [
            PlannedTransaction(
                name="Ubezpieczenie OC",
                amount=Decimal("642.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=categories["Transport"].id,
                description="Składka OC — termin minął",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(prev_year, prev_month, min(28, prev_last_day)),
            ),
            PlannedTransaction(
                name="Abonament telefon",
                amount=Decimal("69.00"),
                type=TransactionType.EXPENSE,
                account_id=checking.id,
                category_id=monthly.id,
                description="Doładowanie — termin minął",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(prev_year, prev_month, min(18, prev_last_day)),
            ),
        ]

        session.add_all(rows)
        return {"planned_transactions": len(rows)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(PlannedTransaction))
