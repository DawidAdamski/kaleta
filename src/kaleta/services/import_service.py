# SPDX-License-Identifier: AGPL-3.0-or-later
"""CSV import and internal transfer detection service."""

from __future__ import annotations

import contextlib
import csv
import datetime
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import ImportError_
from kaleta.models.import_run import ImportRun
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.import_profiles import (
    GENERIC_PROFILE,
    MBANK_PROFILE,
    WISE_PROFILE,
    detect_bank_profile,
    is_mbank_content,
    is_wise_content,
    is_wise_qif_content,
)
from kaleta.services.rule_service import RuleService

# ── File decoding ────────────────────────────────────────────────────────────


def auto_decode(raw: bytes) -> str:
    """Decode uploaded CSV bytes, trying common Polish/EU encodings first."""
    for enc in ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def digits_only(value: str) -> str:
    """Strip non-digit characters from an account number string."""
    return re.sub(r"\D", "", value)


def build_known_account_digits(external_numbers: Iterable[str | None]) -> set[str]:
    """Collect normalised account digits from stored external account numbers."""
    return {digits_only(num) for num in external_numbers if num}


def is_counterparty_transfer(row: ParsedRow, known_digits: set[str]) -> bool:
    """Return True when a row's counterparty matches a known own account."""
    counterparty = digits_only(counterparty_account_raw(row.raw))
    return bool(counterparty and counterparty in known_digits)


def classify_row_preview_type(row: ParsedRow, known_digits: set[str]) -> str:
    """Classify a parsed row for import preview (transfer / income / expense)."""
    if is_counterparty_transfer(row, known_digits):
        return "transfer"
    return "income" if row.amount >= 0 else "expense"


@dataclass
class RowTypeCounts:
    expense: int = 0
    income: int = 0
    transfer: int = 0


def count_row_types(rows: list[ParsedRow], known_digits: set[str]) -> RowTypeCounts:
    """Count preview row types for stats chips."""
    counts = RowTypeCounts()
    for row in rows:
        row_type = classify_row_preview_type(row, known_digits)
        if row_type == "transfer":
            counts.transfer += 1
        elif row_type == "income":
            counts.income += 1
        else:
            counts.expense += 1
    return counts


def build_preview_table_rows(
    rows: list[ParsedRow],
    known_digits: set[str],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Build ``ui.table`` row dicts for the import preview."""
    preview: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit]):
        row_type = classify_row_preview_type(row, known_digits)
        amount_text = f"{'+' if row.amount >= 0 else ''}{row.amount:,.2f}"
        preview.append(
            {
                "idx": i,
                "date": str(row.date),
                "amount": amount_text,
                "description": row.description[:70],
                "type": row_type,
            }
        )
    return preview


# ── Column mapping ────────────────────────────────────────────────────────────


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


@dataclass
class ColumnMapping:
    """Explicit CSV column indices and format options for the generic parser.

    Indices are 0-based header positions. ``None`` means unmapped.
    Empty format strings mean auto-detect. JSON-serialisable for the
    mapping-memory follow-up plan.
    """

    date: int | None = None
    amount: int | None = None
    description: int | None = None
    # Optional long-form note column; never auto-detected, so imports leave
    # ``Transaction.notes`` NULL unless the user points a column at it.
    notes: int | None = None
    payee: int | None = None
    counterparty_account: int | None = None
    debit: int | None = None
    credit: int | None = None
    date_format: str = ""
    decimal_separator: str = ""
    thousands_separator: str = ""
    amounts_negative_for_expenses: bool = True

    def is_complete(self) -> bool:
        """Required fields for a Ready import: date, description, amount mode."""
        has_amount = self.amount is not None or (self.debit is not None or self.credit is not None)
        return self.date is not None and self.description is not None and has_amount

    def validation_errors(self) -> list[str]:
        """Human-readable gaps that block import."""
        errors: list[str] = []
        if self.date is None:
            errors.append("Date column is required.")
        if self.description is None:
            errors.append("Description column is required.")
        if self.amount is None and self.debit is None and self.credit is None:
            errors.append("Amount column (or debit/credit columns) is required.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly keyed dict for ImportRule persistence."""
        return {
            "date": self.date,
            "amount": self.amount,
            "description": self.description,
            "notes": self.notes,
            "payee": self.payee,
            "counterparty_account": self.counterparty_account,
            "debit": self.debit,
            "credit": self.credit,
            "date_format": self.date_format,
            "decimal_separator": self.decimal_separator,
            "thousands_separator": self.thousands_separator,
            "amounts_negative_for_expenses": self.amounts_negative_for_expenses,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ColumnMapping:
        """Rebuild from a keyed dict (ImportRule.column_mapping)."""
        if not data:
            return cls()
        return cls(
            date=_optional_int(data.get("date")),
            amount=_optional_int(data.get("amount")),
            description=_optional_int(data.get("description")),
            notes=_optional_int(data.get("notes")),
            payee=_optional_int(data.get("payee")),
            counterparty_account=_optional_int(data.get("counterparty_account")),
            debit=_optional_int(data.get("debit")),
            credit=_optional_int(data.get("credit")),
            date_format=str(data.get("date_format") or ""),
            decimal_separator=str(data.get("decimal_separator") or ""),
            thousands_separator=str(data.get("thousands_separator") or ""),
            amounts_negative_for_expenses=bool(data.get("amounts_negative_for_expenses", True)),
        )


@dataclass
class CsvInspection:
    """Raw CSV structure for the mapping step UI."""

    delimiter: str
    headers: list[str]
    sample_rows: list[list[str]] = field(default_factory=list)
    detected_mapping: ColumnMapping = field(default_factory=ColumnMapping)


@dataclass
class ParseQueuedFileResult:
    profile: str
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: MBankFileMetadata | None = None
    ok: bool = False
    needs_mapping: bool = False
    error_key: str | None = None
    error_params: dict[str, Any] = field(default_factory=dict)
    inspection: CsvInspection | None = None
    column_mapping: ColumnMapping | None = None


@dataclass
class QueueSettingsSnapshot:
    file_id: str
    profile: str
    metadata: MBankFileMetadata | None = None
    target_account_id: int | None = None
    expense_cat_id: int | None = None
    income_cat_id: int | None = None
    skip_duplicates: bool = True
    column_mapping: ColumnMapping | None = None


def inherit_queue_settings(
    current: QueueSettingsSnapshot,
    queue: list[QueueSettingsSnapshot],
) -> bool:
    """Copy settings from a prior queued file when profiles or accounts match."""
    if (
        current.profile == MBANK_PROFILE
        and current.metadata
        and current.metadata.account_number_digits
    ):
        for prior in reversed(queue):
            if prior.file_id == current.file_id:
                continue
            if (
                prior.profile == MBANK_PROFILE
                and prior.metadata
                and prior.metadata.account_number_digits == current.metadata.account_number_digits
                and prior.target_account_id is not None
            ):
                current.target_account_id = prior.target_account_id
                current.expense_cat_id = prior.expense_cat_id
                current.income_cat_id = prior.income_cat_id
                current.skip_duplicates = prior.skip_duplicates
                return True

    if current.profile == WISE_PROFILE and current.metadata and current.metadata.currency:
        for prior in reversed(queue):
            if prior.file_id == current.file_id:
                continue
            if (
                prior.profile == WISE_PROFILE
                and prior.metadata
                and prior.metadata.currency == current.metadata.currency
                and prior.target_account_id is not None
            ):
                current.target_account_id = prior.target_account_id
                current.expense_cat_id = prior.expense_cat_id
                current.income_cat_id = prior.income_cat_id
                current.skip_duplicates = prior.skip_duplicates
                return True

    for prior in reversed(queue):
        if prior.file_id == current.file_id:
            continue
        if prior.profile == current.profile and (
            prior.expense_cat_id or prior.income_cat_id or prior.column_mapping is not None
        ):
            if current.expense_cat_id is None:
                current.expense_cat_id = prior.expense_cat_id
            if current.income_cat_id is None:
                current.income_cat_id = prior.income_cat_id
            current.skip_duplicates = prior.skip_duplicates
            if current.column_mapping is None and prior.column_mapping is not None:
                current.column_mapping = prior.column_mapping
            return True
    return False


@dataclass
class ImportReadinessCheck:
    target_account_id: int | None
    expense_cat_id: int | None
    income_cat_id: int | None
    profile: str
    metadata: MBankFileMetadata | None
    account_currency: str | None


def validate_import_readiness(
    check: ImportReadinessCheck,
) -> tuple[str | None, dict[str, Any]]:
    """Return ``(i18n_key, params)`` when import must be blocked, else ``(None, {})``."""
    if check.target_account_id is None:
        return "import.select_account_hint", {}
    if check.expense_cat_id is None:
        return "import.select_expense_cat_hint", {}
    if check.income_cat_id is None:
        return "import.select_income_cat_hint", {}
    if (
        check.profile in (MBANK_PROFILE, WISE_PROFILE)
        and check.metadata
        and check.metadata.currency
    ):
        file_currency = check.metadata.currency.upper()
        account_currency = (check.account_currency or "").upper()
        if account_currency and file_currency != account_currency:
            return (
                "import.currency_mismatch_block",
                {"file": check.metadata.currency, "account": check.account_currency},
            )
    return None, {}


def currency_mismatch_warning(
    *,
    file_currency: str,
    account_currency: str,
) -> bool:
    """Return True when mBank file currency differs from the target account."""
    return file_currency.upper() != account_currency.upper()


# ── mBank preprocessor ───────────────────────────────────────────────────────


@dataclass
class MBankFileMetadata:
    client_name: str
    account_type: str
    currency: str
    account_number: str  # raw, e.g. "55 1140 2004 0000 3302 7888 6836"
    account_number_digits: str  # digits only, e.g. "55114020040000330278886836"
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

        def get(key: str) -> str:
            return MBankPreprocessor._value_after_key(lines, key)

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
                clean_header = ";".join(col.lstrip("#").strip() for col in line.split(";"))
                data_lines = [clean_header]
                for body_line in lines[i + 1 :]:
                    stripped = body_line.strip()
                    if not stripped or stripped.startswith("Niniejszy dokument"):
                        break
                    data_lines.append(stripped)
                return "\n".join(data_lines)
        return None

    @staticmethod
    def is_mbank_file(content: str) -> bool:
        """Quick heuristic — check if the file looks like an mBank export."""
        return is_mbank_content(content)


class WisePreprocessor:
    """Parses Wise (TransferWise) CSV statement exports.

    Wise files are plain CSV with a fixed header row starting with
    ``TransferWise ID``. Metadata (currency, period) is derived from rows.
    """

    _HEADER_MARKER = "TransferWise ID"

    @staticmethod
    def is_wise_file(content: str) -> bool:
        return WisePreprocessor._HEADER_MARKER in content[:512] or is_wise_content(content)

    @staticmethod
    def extract_metadata(content: str) -> MBankFileMetadata:
        reader = csv.DictReader(io.StringIO(content))
        currency = ""
        holder = ""
        dates: list[datetime.date] = []
        for row in reader:
            if not currency:
                currency = (row.get("Currency") or "").strip()
            if not holder:
                holder = (row.get("Card Holder Full Name") or "").strip()
            date_raw = (row.get("Date") or "").strip()
            if date_raw:
                try:
                    dates.append(_parse_date(date_raw))
                except ImportError_:
                    continue
        date_from = min(dates) if dates else None
        date_to = max(dates) if dates else None
        return MBankFileMetadata(
            client_name=holder,
            account_type="Wise",
            currency=currency,
            account_number="",
            account_number_digits="",
            date_from=date_from,
            date_to=date_to,
        )


def _build_wise_description(raw: dict[str, str]) -> str:
    """Prefer merchant/payee over Wise's verbose Polish card descriptions."""
    merchant = (raw.get("Merchant") or "").strip()
    if merchant:
        return merchant
    payee = (raw.get("Payee Name") or "").strip()
    if payee:
        return payee
    return (raw.get("Description") or "").strip()


def _apply_wise_descriptions(rows: list[ParsedRow]) -> list[ParsedRow]:
    updated: list[ParsedRow] = []
    for row in rows:
        description = _build_wise_description(row.raw)
        if description and description != row.description:
            updated.append(
                ParsedRow(
                    date=row.date,
                    amount=row.amount,
                    description=description,
                    raw=row.raw,
                    notes=row.notes,
                )
            )
        else:
            updated.append(row)
    return updated


# ── Wise QIF preprocessor ────────────────────────────────────────────────────

_QIF_RECORD_END = "^"


@dataclass
class QifRecord:
    """One ``^``-terminated QIF record, fields keyed by their leading letter."""

    date: str = ""
    amount: str = ""
    payee: str = ""
    reference: str = ""
    memo: str = ""

    def is_empty(self) -> bool:
        return not (self.date or self.amount or self.payee or self.reference or self.memo)

    def as_raw(self) -> dict[str, str]:
        """Row dict mirroring the CSV path's ``ParsedRow.raw`` shape."""
        raw = {
            "date": self.date,
            "amount": self.amount,
            "payee": self.payee,
            "reference": self.reference,
            "memo": self.memo,
        }
        return {key: value for key, value in raw.items() if value}


def iter_qif_records(content: str) -> Iterable[QifRecord]:
    """Split QIF *content* into records, ignoring ``!Type:`` header lines."""
    record = QifRecord()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        if stripped == _QIF_RECORD_END:
            if not record.is_empty():
                yield record
            record = QifRecord()
            continue
        field_letter, value = stripped[0], stripped[1:].strip()
        if field_letter == "D":
            record.date = value
        elif field_letter == "T":
            record.amount = value
        elif field_letter == "P":
            record.payee = value
        elif field_letter == "N":
            record.reference = value
        elif field_letter == "M":
            record.memo = value
        # Other QIF letters (C cleared, L category, A address) are not used.
    if not record.is_empty():
        yield record


class WiseQifPreprocessor:
    """Parses Wise QIF statement exports.

    Wise offers QIF alongside CSV for the same statement, but the QIF carries
    far less: ``D`` date (US ``MM/DD/YYYY``), ``T`` amount, ``P`` payee,
    ``N`` Wise transaction id and ``M`` memo, separated by ``^``. QIF is not
    CSV, so this path bypasses ``parse_csv`` entirely instead of routing
    through a mapping.

    Two fields the CSV has are simply absent, as the real export confirms
    (``tests/e2e/fixtures/import/wise/jpy-travel-sample.qif``):

    * **No currency.** Nothing in the file names it, so
      :meth:`extract_metadata` leaves it empty — see the method for what that
      costs.
    * **No per-transaction memo.** ``M`` holds the card holder and last four
      (``Jan Kowalski 1234``), identical on every card row, or a copy of the
      payee on top-ups. It describes the card, not the transaction, so it is
      never persisted as notes.
    """

    _DATE_FORMAT = "%m/%d/%Y"

    @staticmethod
    def is_wise_qif(content: str) -> bool:
        """Quick heuristic — check if the file looks like a Wise QIF export."""
        return is_wise_qif_content(content)

    @staticmethod
    def parse(content: str) -> ImportResult:
        """Parse QIF records into ``ParsedRow`` objects (positive = income)."""
        result = ImportResult()
        for index, record in enumerate(iter_qif_records(content), start=1):
            if not record.date or not record.amount:
                result.skipped += 1
                continue
            try:
                date = _parse_date(record.date, WiseQifPreprocessor._DATE_FORMAT)
                amount = _parse_amount(
                    record.amount,
                    decimal_separator=".",
                    thousands_separator=",",
                )
            except ImportError_ as exc:
                result.errors.append(f"QIF record {index}: {exc}")
                continue
            # Payee only: ``M`` is the card identity, so falling back to it
            # would put the holder's name in the ledger. An empty description
            # is the lesser evil, and the real export always fills ``P``.
            result.rows.append(
                ParsedRow(
                    date=date,
                    amount=amount,
                    description=record.payee,
                    raw=record.as_raw(),
                )
            )
        return result

    @staticmethod
    def extract_metadata(content: str) -> MBankFileMetadata:
        """Derive the Wise metadata banner fields from the QIF records.

        Only the period is recoverable. **Currency is left empty because the
        format has none** — Wise puts it in the download filename
        (``statement_<id>_JPY_<from>_<to>.qif``), not the content.

        That has a cost the CSV path does not pay: ``validate_import_readiness``
        skips its currency-mismatch block on a falsy currency, so importing a
        JPY QIF into a PLN account is not stopped. Empty is still the correct
        value — inventing a currency would risk blocking a *correct* import —
        but the guard cannot cover this path until the filename is threaded
        through parsing.
        """
        dates: list[datetime.date] = []
        for record in iter_qif_records(content):
            if record.date:
                with contextlib.suppress(ImportError_):
                    dates.append(_parse_date(record.date, WiseQifPreprocessor._DATE_FORMAT))
        return MBankFileMetadata(
            client_name="",
            account_type="Wise",
            currency="",
            account_number="",
            account_number_digits="",
            date_from=min(dates) if dates else None,
            date_to=max(dates) if dates else None,
        )


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

    opis = _clean(raw.get("Opis operacji", ""))
    tytul = _clean(raw.get("Tytuł", ""))
    payee = _clean(raw.get("Nadawca/Odbiorca", ""))

    if payee and tytul:
        return f"{payee} — {tytul}"
    if payee:
        return payee
    if tytul:
        return tytul
    return opis


# ── Date format auto-detection ───────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d",  # ISO: 2024-03-15
    "%d.%m.%Y",  # PL / EU: 15.03.2024
    "%d/%m/%Y",  # 15/03/2024
    "%m/%d/%Y",  # US: 03/15/2024
    "%d-%m-%Y",  # 15-03-2024
    "%Y%m%d",  # compact: 20240315
]


def _parse_date(value: str, fmt: str = "") -> datetime.date:
    value = value.strip()
    formats = [fmt] if fmt else _DATE_FORMATS
    for candidate in formats:
        try:
            return datetime.datetime.strptime(value, candidate).date()
        except ValueError:
            continue
    raise ImportError_(f"Cannot parse date: {value!r}")


def _parse_amount(
    value: str,
    *,
    decimal_separator: str = "",
    thousands_separator: str = "",
) -> Decimal:
    """Parse amount string, handling Polish/EU number formats."""
    cleaned = value.strip().replace("\xa0", "")
    # Remove currency symbols
    cleaned = re.sub(r"[A-Z]{3}$", "", cleaned).strip()
    if thousands_separator:
        cleaned = cleaned.replace(thousands_separator, "")
    else:
        cleaned = cleaned.replace(" ", "")

    if decimal_separator == ",":
        if thousands_separator != ".":
            cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")
    elif decimal_separator == ".":
        if thousands_separator != ",":
            cleaned = cleaned.replace(",", "")
    else:
        # Auto: PL format 1 234,56 or EU 1.234,56 → 1234.56
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ImportError_(f"Cannot parse amount: {value!r}") from exc


# ── Column name aliases ──────────────────────────────────────────────────────

_DATE_ALIASES = {
    "date",
    "data",
    "data księgowania",
    "data ksiegowania",
    "data transakcji",
    "data operacji",
    "transaction date",
}
_AMOUNT_ALIASES = {"amount", "kwota", "wartość", "value", "transaction amount", "kwota operacji"}
_DESC_ALIASES = {"description", "opis", "tytuł", "title", "tytul", "opis operacji", "details"}
_PAYEE_ALIASES = {"payee", "odbiorca", "nadawca", "merchant", "counterparty"}
_COUNTERPARTY_ALIASES = {
    "counterparty account",
    "numer rachunku",
    "numer konta",
    "account number",
    "iban",
}


def counterparty_account_raw(raw: dict[str, str]) -> str:
    """Return counterparty account from mBank or generic CSV row fields."""
    return (
        raw.get("Numer rachunku", "").strip()
        or raw.get("Numer konta", "").strip()
        or raw.get("counterparty_account", "").strip()
    )


_DEBIT_ALIASES = {"debit", "wydatki", "obciążenie", "wypłata", "money out"}
_CREDIT_ALIASES = {"credit", "przychody", "uznanie", "wpłata", "money in"}


def _norm(name: str) -> str:
    return name.strip().lower()


def _detect_column(headers: list[str], aliases: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if _norm(h) in aliases:
            return i
    return None


def detect_column_mapping(headers: list[str]) -> ColumnMapping:
    """Guess a ``ColumnMapping`` from header aliases (may be incomplete)."""
    return ColumnMapping(
        date=_detect_column(headers, _DATE_ALIASES),
        amount=_detect_column(headers, _AMOUNT_ALIASES),
        description=_detect_column(headers, _DESC_ALIASES),
        payee=_detect_column(headers, _PAYEE_ALIASES),
        counterparty_account=_detect_column(headers, _COUNTERPARTY_ALIASES),
        debit=_detect_column(headers, _DEBIT_ALIASES),
        credit=_detect_column(headers, _CREDIT_ALIASES),
    )


def detect_delimiter(content: str) -> str:
    """Pick the most frequent delimiter among comma, semicolon, and tab."""
    sample = content[:2048]
    counts = {d: sample.count(d) for d in (",", ";", "\t")}
    return max(counts, key=lambda d: counts[d])


def inspect_csv(
    content: str,
    *,
    delimiter: str = "",
    sample_limit: int = 10,
) -> CsvInspection:
    """Inspect CSV structure for the mapping step (headers + sample rows)."""
    delim = delimiter or detect_delimiter(content)
    reader = csv.reader(io.StringIO(content), delimiter=delim)
    try:
        headers = next(reader)
    except StopIteration:
        return CsvInspection(delimiter=delim, headers=[], detected_mapping=ColumnMapping())

    headers = [h.strip() for h in headers]
    sample_rows: list[list[str]] = []
    for i, row in enumerate(reader):
        if i >= sample_limit:
            break
        sample_rows.append(list(row))
    return CsvInspection(
        delimiter=delim,
        headers=headers,
        sample_rows=sample_rows,
        detected_mapping=detect_column_mapping(headers),
    )


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class ParsedRow:
    date: datetime.date
    amount: Decimal  # positive = income, negative = expense
    description: str
    raw: dict[str, str]
    notes: str = ""


@dataclass
class ImportResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0


# ── CSV parser ───────────────────────────────────────────────────────────────


class ImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def parse_queued_file(
        self,
        content: str,
        profile: str,
        *,
        mapping: ColumnMapping | None = None,
    ) -> ParseQueuedFileResult:
        """Parse queued CSV content, auto-detecting a bank profile when generic.

        Bank-specific branches are registered in ``import_profiles.BANK_PROFILES``.
        Add a new ``elif resolved_profile == …`` arm only when a real fixture and
        preprocessor exist (see ``tests/e2e/fixtures/import/README.md``).

        When *mapping* is provided (generic path), it overrides alias detection.
        Failed mBank parses fall back to generic + mapping instead of a dead end.
        """
        resolved_profile = profile
        if profile == GENERIC_PROFILE:
            detected = detect_bank_profile(content)
            if detected is not None:
                resolved_profile = detected

        if resolved_profile == MBANK_PROFILE:
            if not MBankPreprocessor.is_mbank_file(content):
                # Fall back to generic + mapping (plan open Q2).
                return self._parse_generic_with_mapping(
                    content,
                    mapping=mapping,
                    profile=GENERIC_PROFILE,
                )
            data_section = MBankPreprocessor.extract_data_section(content)
            if data_section is None:
                return self._parse_generic_with_mapping(
                    content,
                    mapping=mapping,
                    profile=GENERIC_PROFILE,
                )
            metadata = MBankPreprocessor.extract_metadata(content)
            result = self.parse_csv(data_section, delimiter=";")
            if not result.rows:
                return self._parse_generic_with_mapping(
                    content,
                    mapping=mapping,
                    profile=GENERIC_PROFILE,
                )
            return ParseQueuedFileResult(
                profile=resolved_profile,
                rows=result.rows,
                errors=result.errors,
                metadata=metadata,
                ok=True,
            )

        if resolved_profile == WISE_PROFILE:
            if WiseQifPreprocessor.is_wise_qif(content):
                return self._parse_wise_qif(content)
            if not WisePreprocessor.is_wise_file(content):
                return self._parse_generic_with_mapping(
                    content,
                    mapping=mapping,
                    profile=GENERIC_PROFILE,
                )
            metadata = WisePreprocessor.extract_metadata(content)
            result = self.parse_csv(content, delimiter=",")
            if not result.rows:
                return self._parse_generic_with_mapping(
                    content,
                    mapping=mapping,
                    profile=GENERIC_PROFILE,
                )
            rows = _apply_wise_descriptions(result.rows)
            return ParseQueuedFileResult(
                profile=resolved_profile,
                rows=rows,
                errors=result.errors,
                metadata=metadata,
                ok=True,
            )

        # Future bank profiles: branch here (one bank per PR, fixture-backed).

        return self._parse_generic_with_mapping(
            content,
            mapping=mapping,
            profile=resolved_profile,
        )

    def _parse_wise_qif(self, content: str) -> ParseQueuedFileResult:
        """Parse a Wise QIF upload.

        Unlike the CSV branches there is no generic fallback: a QIF that fails
        to yield rows is not CSV, so handing it to the column-mapping step
        would only show the user a garbled table.
        """
        result = WiseQifPreprocessor.parse(content)
        if not result.rows:
            return ParseQueuedFileResult(
                profile=WISE_PROFILE,
                errors=result.errors,
                error_key="import.qif_no_rows",
                error_params={"skipped": result.skipped},
            )
        return ParseQueuedFileResult(
            profile=WISE_PROFILE,
            rows=result.rows,
            errors=result.errors,
            metadata=WiseQifPreprocessor.extract_metadata(content),
            ok=True,
        )

    def _parse_generic_with_mapping(
        self,
        content: str,
        *,
        mapping: ColumnMapping | None,
        profile: str,
    ) -> ParseQueuedFileResult:
        inspection = inspect_csv(content)
        effective = mapping if mapping is not None else inspection.detected_mapping
        mapping_errors = effective.validation_errors()
        if mapping_errors:
            return ParseQueuedFileResult(
                profile=profile,
                errors=mapping_errors,
                needs_mapping=True,
                inspection=inspection,
                column_mapping=effective,
            )

        result = self.parse_csv(
            content,
            delimiter=inspection.delimiter,
            mapping=effective,
        )
        if not result.rows:
            return ParseQueuedFileResult(
                profile=profile,
                rows=result.rows,
                errors=result.errors or mapping_errors,
                needs_mapping=True,
                error_key="import.no_rows" if not result.errors else None,
                error_params={"skipped": result.skipped} if not result.errors else {},
                inspection=inspection,
                column_mapping=effective,
            )
        return ParseQueuedFileResult(
            profile=profile,
            rows=result.rows,
            errors=result.errors,
            ok=True,
            inspection=inspection,
            column_mapping=effective,
        )

    def parse_csv(
        self,
        content: str,
        *,
        delimiter: str = "",
        mapping: ColumnMapping | None = None,
    ) -> ImportResult:
        """Parse CSV content into ParsedRow objects.

        Supports:
        - Single amount column (negative = expense by default)
        - Separate debit / credit columns
        - Explicit ``ColumnMapping`` (falls back to header-alias detection)
        - Auto-detects delimiter (comma, semicolon, tab)
        """
        result = ImportResult()

        delim = delimiter or detect_delimiter(content)
        reader = csv.DictReader(io.StringIO(content), delimiter=delim)
        if not reader.fieldnames:
            result.errors.append("CSV has no headers.")
            return result

        headers = list(reader.fieldnames)
        effective = mapping if mapping is not None else detect_column_mapping(headers)

        date_col = effective.date
        amount_col = effective.amount
        desc_col = effective.description
        notes_col = effective.notes
        payee_col = effective.payee
        counterparty_col = effective.counterparty_account
        debit_col = effective.debit
        credit_col = effective.credit

        structural = effective.validation_errors() if mapping is not None else []
        if mapping is None:
            # Legacy alias path: description optional; amount OR debit/credit required.
            if date_col is None:
                result.errors.append(f"Cannot find a date column. Headers: {headers}")
                return result
            if amount_col is None and debit_col is None and credit_col is None:
                result.errors.append(
                    f"Cannot find an amount/debit/credit column. Headers: {headers}"
                )
                return result
        elif structural:
            result.errors.extend(structural)
            return result

        date_key = headers[date_col] if date_col is not None else None
        amount_key = headers[amount_col] if amount_col is not None else None
        desc_key = headers[desc_col] if desc_col is not None else None
        notes_key = headers[notes_col] if notes_col is not None else None
        payee_key = headers[payee_col] if payee_col is not None else None
        counterparty_key = headers[counterparty_col] if counterparty_col is not None else None
        debit_key = headers[debit_col] if debit_col is not None else None
        credit_key = headers[credit_col] if credit_col is not None else None

        if date_key is None:
            result.errors.append(f"Cannot find a date column. Headers: {headers}")
            return result

        for line_no, row in enumerate(reader, start=2):
            try:
                date = _parse_date(row.get(date_key, ""), effective.date_format)

                if amount_key:
                    raw_amount = row.get(amount_key, "").strip()
                    if not raw_amount:
                        result.skipped += 1
                        continue
                    amount = _parse_amount(
                        raw_amount,
                        decimal_separator=effective.decimal_separator,
                        thousands_separator=effective.thousands_separator,
                    )
                    if not effective.amounts_negative_for_expenses:
                        amount = -amount
                else:
                    # Separate debit/credit columns
                    raw_debit = row.get(debit_key or "", "").strip() if debit_key else ""
                    raw_credit = row.get(credit_key or "", "").strip() if credit_key else ""
                    debit = (
                        _parse_amount(
                            raw_debit,
                            decimal_separator=effective.decimal_separator,
                            thousands_separator=effective.thousands_separator,
                        )
                        if raw_debit
                        else Decimal("0")
                    )
                    credit = (
                        _parse_amount(
                            raw_credit,
                            decimal_separator=effective.decimal_separator,
                            thousands_separator=effective.thousands_separator,
                        )
                        if raw_credit
                        else Decimal("0")
                    )
                    amount = credit - debit  # positive = income

                description = row.get(desc_key, "").strip() if desc_key else ""
                notes = row.get(notes_key, "").strip() if notes_key else ""
                payee = row.get(payee_key, "").strip() if payee_key else ""
                counterparty = row.get(counterparty_key, "").strip() if counterparty_key else ""
                raw = dict(row)
                if payee:
                    raw["payee"] = payee
                    if not description:
                        description = payee
                if counterparty:
                    raw["counterparty_account"] = counterparty
                result.rows.append(
                    ParsedRow(
                        date=date,
                        amount=amount,
                        description=description,
                        raw=raw,
                        notes=notes,
                    )
                )

            except (ImportError_, KeyError) as exc:
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
                default_income_category_id
                if tx_type == TransactionType.INCOME
                else default_expense_category_id
            )
            creates.append(
                TransactionCreate(
                    account_id=account_id,
                    category_id=cat_id,
                    amount=abs(row.amount),
                    type=tx_type,
                    date=row.date,
                    description=row.description,
                    notes=row.notes,
                )
            )
        return creates

    async def apply_categorisation_rules(
        self,
        creates: list[TransactionCreate],
    ) -> list[TransactionCreate]:
        """Override category_id from matching active rules (import-time only).

        Internal transfers are skipped. Manual edits after import are never
        overwritten because rules are not re-applied outside this path.
        """
        if not creates:
            return creates

        rules = await RuleService(self.session).list(active_only=True)
        if not rules:
            return creates

        payee_ids = {c.payee_id for c in creates if c.payee_id is not None}
        payee_names: dict[int, str] = {}
        if payee_ids:
            result = await self.session.execute(select(Payee).where(Payee.id.in_(payee_ids)))
            payee_names = {p.id: p.name for p in result.scalars()}

        updated: list[TransactionCreate] = []
        for create in creates:
            if create.is_internal_transfer or create.type == TransactionType.TRANSFER:
                updated.append(create)
                continue
            payee_name = payee_names.get(create.payee_id) if create.payee_id else None
            matched_category_id: int | None = None
            for rule in rules:
                if RuleService.matches(
                    rule.pattern,
                    payee_name=payee_name,
                    description=create.description,
                    match_mode=rule.match_mode,
                ):
                    matched_category_id = rule.category_id
                    break
            if matched_category_id is not None and matched_category_id != create.category_id:
                updated.append(create.model_copy(update={"category_id": matched_category_id}))
            else:
                updated.append(create)
        return updated

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
            counterparty_raw = counterparty_account_raw(row.raw)
            counterparty_digits = re.sub(r"\D", "", counterparty_raw)
            if counterparty_digits and counterparty_digits in known:
                creates.append(
                    TransactionCreate(
                        account_id=account_id,
                        category_id=None,
                        payee_id=payee_id,
                        amount=abs(row.amount),
                        type=TransactionType.TRANSFER,
                        date=row.date,
                        description=description,
                        is_internal_transfer=True,
                    )
                )
            else:
                tx_type = TransactionType.INCOME if row.amount >= 0 else TransactionType.EXPENSE
                cat_id = (
                    default_income_category_id
                    if tx_type == TransactionType.INCOME
                    else default_expense_category_id
                )
                creates.append(
                    TransactionCreate(
                        account_id=account_id,
                        category_id=cat_id,
                        payee_id=payee_id,
                        amount=abs(row.amount),
                        type=tx_type,
                        date=row.date,
                        description=description,
                    )
                )
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
    ) -> tuple[list[TransactionCreate], list[TransactionCreate]]:
        """Remove creates that already exist in the database.

        Returns ``(unique_creates, skipped_creates)``. A create is skipped when
        the same (account, date, amount, description) already exists.
        """
        unique: list[TransactionCreate] = []
        skipped: list[TransactionCreate] = []
        for create in creates:
            is_dupe = await self.find_duplicate(
                account_id=create.account_id,
                date=create.date,
                amount=create.amount,
                description=create.description,
            )
            if is_dupe:
                skipped.append(create)
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
            for tx_b in candidates[i + 1 :]:
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

    def record_import_run(
        self,
        *,
        account_id: int,
        filename: str,
        profile: str,
        imported_count: int,
        skipped_count: int,
        row_date_min: datetime.date | None,
        row_date_max: datetime.date | None,
    ) -> ImportRun:
        """Stage an ``ImportRun`` on the session (caller owns the commit)."""
        run = ImportRun(
            account_id=account_id,
            filename=filename,
            profile=profile,
            imported_count=imported_count,
            skipped_count=skipped_count,
            row_date_min=row_date_min,
            row_date_max=row_date_max,
        )
        self.session.add(run)
        return run

    async def list_recent_runs(self, *, limit: int = 20) -> list[ImportRun]:
        """Return the most recent import runs (newest first)."""
        result = await self.session.execute(
            select(ImportRun)
            .options(selectinload(ImportRun.account))
            .order_by(ImportRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
