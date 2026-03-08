"""CSV import and internal transfer detection service."""

from __future__ import annotations

import csv
import datetime
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.transaction import TransactionCreate

# ── Date format auto-detection ───────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d",   # ISO: 2024-03-15
    "%d.%m.%Y",   # PL / EU: 15.03.2024
    "%d/%m/%Y",   # 15/03/2024
    "%m/%d/%Y",   # US: 03/15/2024
    "%d-%m-%Y",   # 15-03-2024
    "%Y%m%d",     # compact: 20240315
]


def _parse_date(value: str) -> datetime.date:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


def _parse_amount(value: str) -> Decimal:
    """Parse amount string, handling Polish/EU number formats."""
    cleaned = value.strip().replace("\xa0", "").replace(" ", "")
    # Remove currency symbols
    cleaned = re.sub(r"[A-Z]{3}$", "", cleaned).strip()
    # Handle PL format: 1 234,56 → 1234.56
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        # e.g. 1.234,56 → 1234.56
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse amount: {value!r}") from exc


# ── Column name aliases ──────────────────────────────────────────────────────

_DATE_ALIASES    = {"date", "data", "data transakcji", "data operacji", "transaction date"}
_AMOUNT_ALIASES  = {"amount", "kwota", "wartość", "value", "transaction amount", "kwota operacji"}
_DESC_ALIASES    = {"description", "opis", "tytuł", "title", "tytul", "opis operacji", "details"}
_DEBIT_ALIASES   = {"debit", "wydatki", "obciążenie", "wypłata"}
_CREDIT_ALIASES  = {"credit", "przychody", "uznanie", "wpłata"}


def _norm(name: str) -> str:
    return name.strip().lower()


def _detect_column(headers: list[str], aliases: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if _norm(h) in aliases:
            return i
    return None


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ParsedRow:
    date: datetime.date
    amount: Decimal          # positive = income, negative = expense
    description: str
    raw: dict[str, str]


@dataclass
class ImportResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0


# ── CSV parser ───────────────────────────────────────────────────────────────

class ImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def parse_csv(self, content: str, *, delimiter: str = "") -> ImportResult:
        """Parse CSV content into ParsedRow objects.

        Supports:
        - Single amount column (negative = expense)
        - Separate debit / credit columns
        - Auto-detects delimiter (comma, semicolon, tab)
        """
        result = ImportResult()

        # Auto-detect delimiter
        if not delimiter:
            sample = content[:2048]
            counts = {d: sample.count(d) for d in (",", ";", "\t")}
            delimiter = max(counts, key=lambda d: counts[d])

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        if not reader.fieldnames:
            result.errors.append("CSV has no headers.")
            return result

        headers = list(reader.fieldnames)
        date_col   = _detect_column(headers, _DATE_ALIASES)
        amount_col = _detect_column(headers, _AMOUNT_ALIASES)
        desc_col   = _detect_column(headers, _DESC_ALIASES)
        debit_col  = _detect_column(headers, _DEBIT_ALIASES)
        credit_col = _detect_column(headers, _CREDIT_ALIASES)

        if date_col is None:
            result.errors.append(f"Cannot find a date column. Headers: {headers}")
            return result
        if amount_col is None and (debit_col is None and credit_col is None):
            result.errors.append(f"Cannot find an amount/debit/credit column. Headers: {headers}")
            return result

        date_key   = headers[date_col]
        amount_key = headers[amount_col] if amount_col is not None else None
        desc_key   = headers[desc_col]   if desc_col  is not None else None
        debit_key  = headers[debit_col]  if debit_col  is not None else None
        credit_key = headers[credit_col] if credit_col is not None else None

        for line_no, row in enumerate(reader, start=2):
            try:
                date = _parse_date(row.get(date_key, ""))

                if amount_key:
                    raw_amount = row.get(amount_key, "").strip()
                    if not raw_amount:
                        result.skipped += 1
                        continue
                    amount = _parse_amount(raw_amount)
                else:
                    # Separate debit/credit columns
                    raw_debit  = row.get(debit_key  or "", "").strip() if debit_key  else ""
                    raw_credit = row.get(credit_key or "", "").strip() if credit_key else ""
                    debit  = _parse_amount(raw_debit)  if raw_debit  else Decimal("0")
                    credit = _parse_amount(raw_credit) if raw_credit else Decimal("0")
                    amount = credit - debit  # positive = income

                description = row.get(desc_key, "").strip() if desc_key else ""
                result.rows.append(ParsedRow(date=date, amount=amount, description=description, raw=dict(row)))

            except (ValueError, KeyError) as exc:
                result.errors.append(f"Row {line_no}: {exc}")

        return result

    def to_transaction_creates(
        self,
        rows: list[ParsedRow],
        account_id: int,
        default_expense_category_id: int | None = None,
        default_income_category_id: int | None = None,
    ) -> list[TransactionCreate]:
        """Convert ParsedRows to TransactionCreate schemas."""
        creates: list[TransactionCreate] = []
        for row in rows:
            tx_type = TransactionType.INCOME if row.amount >= 0 else TransactionType.EXPENSE
            cat_id = (
                default_income_category_id if tx_type == TransactionType.INCOME
                else default_expense_category_id
            )
            creates.append(TransactionCreate(
                account_id=account_id,
                category_id=cat_id,
                amount=abs(row.amount),
                type=tx_type,
                date=row.date,
                description=row.description,
            ))
        return creates

    # ── Internal Transfer Detection ──────────────────────────────────────────

    async def detect_and_link_transfers(
        self,
        *,
        max_days_apart: int = 3,
        amount_tolerance: Decimal = Decimal("0.01"),
    ) -> int:
        """Scan unlinked TRANSFER transactions and pair outflow/inflow legs.

        Matching criteria:
        - Same amount (within tolerance)
        - Dates within max_days_apart
        - Different accounts
        - Both legs not yet linked

        Returns the number of pairs linked.
        """
        stmt = (
            select(Transaction)
            .where(
                Transaction.is_internal_transfer == True,  # noqa: E712
                Transaction.linked_transaction_id == None,  # noqa: E711
            )
            .order_by(Transaction.date, Transaction.id)
        )
        result = await self.session.execute(stmt)
        candidates = list(result.scalars().all())

        # Separate into outflows (expense-side) and inflows (income-side)
        # For transfers we don't have income/expense type — match by amount & date across accounts
        linked_ids: set[int] = set()
        pairs = 0

        for i, tx_a in enumerate(candidates):
            if tx_a.id in linked_ids:
                continue
            for tx_b in candidates[i + 1:]:
                if tx_b.id in linked_ids:
                    continue
                if tx_a.account_id == tx_b.account_id:
                    continue
                if abs(tx_a.amount - tx_b.amount) > amount_tolerance:
                    continue
                date_diff = abs((tx_a.date - tx_b.date).days)
                if date_diff > max_days_apart:
                    continue
                # Match found — link both legs
                tx_a.linked_transaction_id = tx_b.id
                tx_b.linked_transaction_id = tx_a.id
                linked_ids.add(tx_a.id)
                linked_ids.add(tx_b.id)
                pairs += 1
                break

        if pairs:
            await self.session.commit()

        return pairs
