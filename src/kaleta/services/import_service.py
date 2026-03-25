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

# ── mBank preprocessor ───────────────────────────────────────────────────────

@dataclass
class MBankFileMetadata:
    client_name: str
    account_type: str
    currency: str
    account_number: str          # raw, e.g. "55 1140 2004 0000 3302 7888 6836"
    account_number_digits: str   # digits only, e.g. "55114020040000330278886836"
    date_from: datetime.date | None
    date_to: datetime.date | None


class MBankPreprocessor:
    """Parses and normalises mBank CSV export files.

    mBank files start with ~20–30 lines of metadata before the actual data table.
    This class extracts that metadata and strips the header so the generic
    ``ImportService.parse_csv`` can handle the rest.
    """

    @staticmethod
    def _value_after_key(lines: list[str], key: str) -> str:
        """Return the first non-empty value that follows a line starting with *key*."""
        for i, line in enumerate(lines):
            if line.strip().startswith(key):
                for j in range(i + 1, min(i + 5, len(lines))):
                    val = lines[j].strip().rstrip(";").strip()
                    if val:
                        return val
        return ""

    @staticmethod
    def extract_metadata(content: str) -> MBankFileMetadata:
        lines = content.splitlines()
        get = lambda key: MBankPreprocessor._value_after_key(lines, key)  # noqa: E731

        account_number_raw = get("#Numer rachunku")
        digits = re.sub(r"\D", "", account_number_raw)

        date_from: datetime.date | None = None
        date_to: datetime.date | None = None
        period_raw = get("#Za okres:")
        if period_raw:
            parts = [p.strip() for p in period_raw.split(";") if p.strip()]
            try:
                if len(parts) >= 2:
                    date_from = datetime.date.fromisoformat(parts[0])
                    date_to = datetime.date.fromisoformat(parts[1])
                elif len(parts) == 1:
                    date_from = datetime.date.fromisoformat(parts[0])
            except ValueError:
                pass

        return MBankFileMetadata(
            client_name=get("#Klient"),
            account_type=get("#Rodzaj rachunku"),
            currency=get("#Waluta"),
            account_number=account_number_raw,
            account_number_digits=digits,
            date_from=date_from,
            date_to=date_to,
        )

    @staticmethod
    def extract_data_section(content: str) -> str | None:
        """Return the data CSV (header + rows) stripped of the mBank metadata block."""
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "#Data" in line and "#Kwota" in line:
                clean_header = ";".join(
                    col.lstrip("#").strip() for col in line.split(";")
                )
                data_lines = [clean_header]
                for body_line in lines[i + 1:]:
                    stripped = body_line.strip()
                    if not stripped or stripped.startswith("Niniejszy dokument"):
                        break
                    data_lines.append(stripped)
                return "\n".join(data_lines)
        return None

    @staticmethod
    def is_mbank_file(content: str) -> bool:
        """Quick heuristic — check if the file looks like an mBank export."""
        return "#Numer rachunku" in content or "#Rodzaj rachunku" in content



def _build_mbank_description(raw: dict[str, str]) -> str:
    """Build a human-readable description from mBank CSV row fields.

    Priority:
    1. ``Nadawca/Odbiorca — Tytuł``  (transfer with a known counterparty)
    2. ``Nadawca/Odbiorca``          (counterparty only, no title)
    3. ``Tytuł``                     (card purchase — payee name is in the title)
    4. ``Opis operacji``             (fallback — generic operation type only)
    """
    def _clean(val: str) -> str:
        text = re.sub(r"\s{2,}", " ", val).strip()
        # mBank appends " DATA TRANSAKCJI: YYYY-MM-DD" to card-purchase titles;
        # the date is already stored separately so we strip it here.
        return re.sub(r"\s+DATA TRANSAKCJI:\s*\d{4}-\d{2}-\d{2}$", "", text).strip()

    opis  = _clean(raw.get("Opis operacji",   ""))
    tytul = _clean(raw.get("Tytuł",           ""))
    payee = _clean(raw.get("Nadawca/Odbiorca",""))

    if payee and tytul:
        return f"{payee} — {tytul}"
    if payee:
        return payee
    if tytul:
        return tytul
    return opis

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
                result.rows.append(
                    ParsedRow(date=date, amount=amount, description=description, raw=dict(row))
                )

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
        """Convert ParsedRows to TransactionCreate schemas (generic CSV)."""
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

    async def to_transaction_creates_with_payees(
        self,
        rows: list[ParsedRow],
        account_id: int,
        default_expense_category_id: int | None = None,
        default_income_category_id: int | None = None,
        known_account_digits: set[str] | None = None,
    ) -> list[TransactionCreate]:
        """mBank-aware: resolves payees and detects transfers to registered accounts.

        A transaction is marked as TRANSFER only when the counterparty account
        number (``Numer rachunku`` column) matches one of the user's own accounts
        (identified by their stored ``external_account_number`` digits).

        Does NOT commit — the caller owns the transaction boundary.
        """
        from kaleta.services.payee_service import PayeeService

        payee_svc = PayeeService(self.session)
        known = known_account_digits or set()
        creates: list[TransactionCreate] = []

        for row in rows:
            description = _build_mbank_description(row.raw)
            payee_raw = row.raw.get("Nadawca/Odbiorca", "").strip()
            payee_id: int | None = None
            if payee_raw:
                payee = await payee_svc.find_or_create(payee_raw)
                payee_id = payee.id

            # Transfer only when the counterparty account is one of ours
            counterparty_raw = row.raw.get("Numer rachunku", "").strip()
            counterparty_digits = re.sub(r"\D", "", counterparty_raw)
            if counterparty_digits and counterparty_digits in known:
                creates.append(TransactionCreate(
                    account_id=account_id,
                    category_id=None,
                    payee_id=payee_id,
                    amount=abs(row.amount),
                    type=TransactionType.TRANSFER,
                    date=row.date,
                    description=description,
                    is_internal_transfer=True,
                ))
            else:
                tx_type = TransactionType.INCOME if row.amount >= 0 else TransactionType.EXPENSE
                cat_id = (
                    default_income_category_id if tx_type == TransactionType.INCOME
                    else default_expense_category_id
                )
                creates.append(TransactionCreate(
                    account_id=account_id,
                    category_id=cat_id,
                    payee_id=payee_id,
                    amount=abs(row.amount),
                    type=tx_type,
                    date=row.date,
                    description=description,
                ))
        return creates

    # ── Duplicate detection ───────────────────────────────────────────────────

    async def find_duplicate(
        self,
        account_id: int,
        date: datetime.date,
        amount: Decimal,
        description: str,
    ) -> bool:
        """Return True if a transaction with the same (account, date, amount, description) exists."""  # noqa: E501
        stmt = (
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.date == date,
                Transaction.amount == amount,
                Transaction.description == description,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def filter_duplicates(
        self, creates: list[TransactionCreate]
    ) -> tuple[list[TransactionCreate], int]:
        """Remove creates that already exist in the database.

        Returns ``(unique_creates, skipped_count)``.
        """
        unique: list[TransactionCreate] = []
        skipped = 0
        for create in creates:
            is_dupe = await self.find_duplicate(
                account_id=create.account_id,
                date=create.date,
                amount=create.amount,
                description=create.description,
            )
            if is_dupe:
                skipped += 1
            else:
                unique.append(create)
        return unique, skipped

    # ── Internal Transfer Detection ───────────────────────────────────────────

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
