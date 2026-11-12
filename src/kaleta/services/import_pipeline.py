# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import of one parsed bank statement: build a plan, then apply it once.

The import page used to glue these steps together itself; the REST API may
not import views, so it had nothing to call. ``ImportPipeline`` is that glue
as a service:

- :meth:`ImportPipeline.build` — resolve the account, check readiness, turn the
  parsed rows into transactions (payees and own-account transfers for mBank),
  mark duplicates and apply the categorisation rules. It writes **nothing**:
  payees that do not exist yet are only named.
- :meth:`ImportPipeline.apply` — create those payees, the rows, the import run
  and the statement's account number, then commit **once**. Any failure rolls
  all of it back.

Parsing (``ImportService.parse_queued_file``) stays a step of its own: the page
parses on upload and re-parses as the mapping changes, long before an import.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import zlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.db.tenant_context import current_tenant
from kaleta.exceptions import ConflictError, PayloadTooLargeError, ValidationError
from kaleta.models.import_run import ImportRun
from kaleta.models.payee import Payee
from kaleta.models.transaction import TransactionType
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.account_service import AccountService
from kaleta.services.import_profiles import GENERIC_PROFILE, MBANK_PROFILE
from kaleta.services.import_rule_service import ImportRuleService
from kaleta.services.import_service import (
    ColumnMapping,
    ImportReadinessCheck,
    ImportService,
    MBankFileMetadata,
    ParseQueuedFileResult,
    build_known_account_digits,
    decode_upload,
    validate_import_readiness,
)
from kaleta.services.payee_service import PayeeService
from kaleta.services.transaction_service import (
    DEFAULT_TRANSFER_PAIRING_DAYS,
    TransactionService,
)

#: English text of the readiness keys ``validate_import_readiness`` returns.
#: The page shows the translated key; the text is what a log or an API reads.
_READINESS_MESSAGES = {
    "import.select_account_hint": "Select a target account.",
    "import.select_expense_cat_hint": "Select a default expense category.",
    "import.select_income_cat_hint": "Select a default income category.",
    "import.currency_mismatch_block": (
        "Import blocked: file currency ({file}) does not match account currency ({account})."
    ),
}

#: Why a parsed row was not imported.
SKIP_DUPLICATE = "duplicate"

#: Mapping fields that make a saved filename rule's mapping worth applying —
#: the same test the import page uses before it trusts a rule's columns.
_MAPPING_FIELDS = ("date", "amount", "description", "payee", "debit", "credit")

#: Domain separation for the file digest: the app secret is used for other
#: things, and a digest keyed with it directly would share that key.
_FILE_HMAC_CONTEXT = b"kaleta/import-run/file-hmac/v1"

AccountSource = Literal["explicit", "rule", "number"]


def upload_exceeds_limit(size_bytes: int, cap_bytes: int | None = None) -> bool:
    """Whether an upload of ``size_bytes`` is over ``settings.max_upload_bytes``."""
    cap = settings.max_upload_bytes if cap_bytes is None else cap_bytes
    return size_bytes > cap


@dataclass(frozen=True, slots=True)
class ImportOptions:
    """What the caller decides about one file; the rest comes from the file."""

    filename: str
    #: The target account. ``None`` resolves it: filename rule, then mBank number.
    account_id: int | None = None
    expense_category_id: int | None = None
    income_category_id: int | None = None
    skip_duplicates: bool = True
    #: Widens the returned transfer-review window (the user's pairing setting).
    pairing_days: int = DEFAULT_TRANSFER_PAIRING_DAYS


@dataclass(frozen=True, slots=True)
class AccountResolution:
    """Which account a file goes to, and why."""

    account_id: int | None
    source: AccountSource | None
    rule_id: int | None = None
    #: The account the statement's own number points to, whatever won. The page
    #: uses it to tell an automatic match from a rule (``default_remember_mapping``).
    number_account_id: int | None = None


@dataclass(frozen=True, slots=True)
class PlannedRow:
    """One transaction to create; ``new_payee`` names a payee ``apply`` must create."""

    create: TransactionCreate
    new_payee: str | None = None
    #: The parsed row it came from (0-based), for a caller that reports per row.
    row_index: int = -1


@dataclass(frozen=True, slots=True)
class SkippedRow:
    """A parsed row that is not imported, and why (``SKIP_DUPLICATE``)."""

    create: TransactionCreate
    reason: str
    row_index: int = -1


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """Everything ``apply`` writes, computed by ``build``. No ORM objects."""

    account_id: int
    filename: str
    profile: str
    rows: list[PlannedRow]
    skipped: list[SkippedRow]
    #: Payees to create, in first-seen order, each once.
    new_payee_names: list[str]
    #: The statement's own account number, saved on the account (mBank).
    account_number_digits: str | None
    resolution: AccountResolution
    #: Every parsed row's span, widened by the pairing window.
    transfer_window: tuple[datetime.date, datetime.date] | None


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """What ``apply`` stored. (``ImportResult`` is taken: the parser's result.)"""

    imported_count: int
    skipped: list[SkippedRow]
    import_run_id: int
    transfer_window: tuple[datetime.date, datetime.date] | None
    created_payee_count: int = 0
    account_id: int = 0
    saved_account_number: str | None = field(default=None)
    #: How many rows were skipped. Equals ``len(skipped)`` except on a replay
    #: (``replayed``), which has the stored count but not the rows themselves.
    skipped_count: int = 0
    #: A repeat of an earlier request with the same ``Idempotency-Key``.
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class PreviewRow:
    """One parsed row as an import would store it — or skip it."""

    row_index: int
    date: datetime.date
    amount: Decimal
    type: TransactionType
    description: str
    category_id: int | None
    payee_name: str | None
    duplicate: bool


class ImportPipeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── account resolution ───────────────────────────────────────────────────

    async def resolve_account(
        self,
        *,
        filename: str,
        profile: str,
        metadata: MBankFileMetadata | None,
        account_id: int | None = None,
    ) -> AccountResolution:
        """Explicit account, else the filename rule's, else the mBank number's.

        An explicit account is taken as given, with no lookups. Otherwise the
        statement number is looked up for every mBank file — even when a rule
        wins — so ``number_account_id`` can say whether both agree. An
        ambiguous number raises ``ConflictError`` (``find_by_external_number``).
        """
        if account_id is not None:
            return AccountResolution(account_id=account_id, source="explicit")
        number_account_id = await self._number_match(profile, metadata)
        rule = await ImportRuleService(self.session).match(filename)
        if rule is not None and rule.account_id is not None:
            return AccountResolution(
                account_id=rule.account_id,
                source="rule",
                rule_id=rule.id,
                number_account_id=number_account_id,
            )
        if number_account_id is not None:
            return AccountResolution(
                account_id=number_account_id,
                source="number",
                number_account_id=number_account_id,
            )
        return AccountResolution(account_id=None, source=None)

    async def _number_match(self, profile: str, metadata: MBankFileMetadata | None) -> int | None:
        if profile != MBANK_PROFILE or metadata is None or not metadata.account_number_digits:
            return None
        digits = metadata.account_number_digits
        matched = await AccountService(self.session).find_by_external_number(digits[-10:])
        return matched.id if matched is not None else None

    # ── build: read-only ─────────────────────────────────────────────────────

    async def build(self, parsed: ParseQueuedFileResult, options: ImportOptions) -> ImportPlan:
        """Steps 2–6 of an import, writing nothing; raises what the page shows.

        Readiness (account, both default categories, the file's currency) is
        checked as ``validate_import_readiness`` does and raised as a
        ``ValidationError`` carrying the same i18n key and params.
        """
        resolution = await self.resolve_account(
            filename=options.filename,
            profile=parsed.profile,
            metadata=parsed.metadata,
            account_id=options.account_id,
        )
        accounts = AccountService(self.session)
        account = (
            await accounts.get(resolution.account_id) if resolution.account_id is not None else None
        )
        error_key, error_params = validate_import_readiness(
            ImportReadinessCheck(
                target_account_id=account.id if account is not None else None,
                expense_cat_id=options.expense_category_id,
                income_cat_id=options.income_category_id,
                profile=parsed.profile,
                metadata=parsed.metadata,
                account_currency=account.currency if account is not None else None,
            )
        )
        if error_key is not None:
            raise ValidationError(
                _READINESS_MESSAGES.get(error_key, error_key).format(**error_params),
                message_key=error_key,
                params=error_params,
            )
        if (
            account is None
            or options.expense_category_id is None
            or options.income_category_id is None
        ):  # readiness above already refused each of these
            raise ValidationError(_READINESS_MESSAGES["import.select_account_hint"])

        imports = ImportService(self.session)
        account_number = (
            parsed.metadata.account_number_digits
            if parsed.metadata is not None and parsed.metadata.account_number_digits
            else None
        )
        if parsed.profile == MBANK_PROFILE:
            # Read on every build: an earlier file in the same batch, or
            # Settings, may have stored a number since the caller looked.
            known = build_known_account_digits(
                a.external_account_number for a in await accounts.list()
            )
            drafts = await imports.draft_creates_with_payees(
                parsed.rows,
                account_id=account.id,
                default_expense_category_id=options.expense_category_id,
                default_income_category_id=options.income_category_id,
                known_account_digits=known,
                target_account_digits=account_number or account.external_account_number,
            )
        else:
            drafts = [
                (create, None)
                for create in imports.to_transaction_creates(
                    parsed.rows,
                    account_id=account.id,
                    default_expense_category_id=options.expense_category_id,
                    default_income_category_id=options.income_category_id,
                )
            ]

        kept: list[tuple[int, TransactionCreate, str | None]] = []
        skipped: list[SkippedRow] = []
        # One draft per parsed row, in order, so the position is the row index.
        for index, (create, new_payee) in enumerate(drafts):
            if options.skip_duplicates and await imports.find_duplicate(
                account_id=create.account_id,
                date=create.date,
                amount=create.amount,
                description=create.description,
            ):
                skipped.append(SkippedRow(create=create, reason=SKIP_DUPLICATE, row_index=index))
            else:
                kept.append((index, create, new_payee))

        categorised = await imports.apply_categorisation_rules(
            [create for _, create, _ in kept],
            new_payee_names=[new_payee for _, _, new_payee in kept],
        )
        rows = [
            PlannedRow(create=create, new_payee=new_payee, row_index=index)
            for create, (index, _, new_payee) in zip(categorised, kept, strict=True)
        ]
        new_payee_names = list(dict.fromkeys(r.new_payee for r in rows if r.new_payee))
        return ImportPlan(
            account_id=account.id,
            filename=options.filename,
            profile=parsed.profile,
            rows=rows,
            skipped=skipped,
            new_payee_names=new_payee_names,
            account_number_digits=account_number if parsed.profile == MBANK_PROFILE else None,
            resolution=resolution,
            transfer_window=ImportService.transfer_review_window(
                (row.date for row in parsed.rows), max_days_apart=options.pairing_days
            ),
        )

    # ── apply: one transaction ───────────────────────────────────────────────

    async def apply(
        self,
        plan: ImportPlan,
        *,
        idempotency_key: str | None = None,
        file_hmac: str | None = None,
    ) -> ImportOutcome:
        """Write the plan and commit once; on any error roll everything back.

        ``idempotency_key`` and ``file_hmac`` are stored on the import run, so
        a repeated API request is replayed and the same file is recognised.
        """
        try:
            payees = PayeeService(self.session)
            payee_ids: dict[str, int] = {}
            for name in plan.new_payee_names:
                payee_ids[name] = (await payees.match_or_create_from_name(name)).id
            creates = [
                row.create.model_copy(update={"payee_id": payee_ids[row.new_payee]})
                if row.new_payee is not None
                else row.create
                for row in plan.rows
            ]
            dates = [c.date for c in creates]
            run = ImportService(self.session).record_import_run(
                account_id=plan.account_id,
                filename=plan.filename,
                profile=plan.profile,
                imported_count=len(creates),
                skipped_count=len(plan.skipped),
                row_date_min=min(dates) if dates else None,
                row_date_max=max(dates) if dates else None,
            )
            run.idempotency_key = idempotency_key
            run.file_hmac = file_hmac
            count = await TransactionService(self.session).create_bulk(creates, commit=False)
            if plan.account_number_digits:
                await AccountService(self.session).save_external_number(
                    plan.account_id, plan.account_number_digits, commit=False
                )
            await self.session.flush()
            run_id = run.id
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return ImportOutcome(
            imported_count=count,
            skipped=plan.skipped,
            import_run_id=run_id,
            transfer_window=plan.transfer_window,
            created_payee_count=len(payee_ids),
            account_id=plan.account_id,
            saved_account_number=plan.account_number_digits,
            skipped_count=len(plan.skipped),
        )

    # ── one uploaded file, as the REST API receives it ───────────────────────

    async def parse_upload(self, raw: bytes, filename: str) -> ParseQueuedFileResult:
        """Decode and parse an uploaded statement, as the import page would.

        The bank profile is detected from the content. A generic CSV is parsed
        with the column mapping of the filename rule that matches, if it saved
        one; without it the columns are guessed from the headers. A file that
        still needs a mapping, or that yields no rows, is a ``ValidationError``
        — for a CSV the message lists the headers that were found.
        """
        content, _ = decode_upload(raw)
        mapping: ColumnMapping | None = None
        rule = await ImportRuleService(self.session).match(filename)
        if rule is not None and rule.column_mapping:
            saved = ColumnMapping.from_dict(dict(rule.column_mapping))
            if any(getattr(saved, name) is not None for name in _MAPPING_FIELDS):
                mapping = saved
        parsed = ImportService(self.session).parse_queued_file(
            content, GENERIC_PROFILE, mapping=mapping, filename=filename, raw=raw
        )
        if parsed.ok and parsed.rows:
            return parsed
        if parsed.needs_mapping and parsed.inspection is not None:
            headers = parsed.inspection.headers
            raise ValidationError(
                "The CSV columns could not be mapped and no saved mapping matches "
                f"{filename!r}. Detected headers: {', '.join(headers) or '(none)'}. "
                "Save a mapping for this filename on the import page first.",
                code="import_needs_mapping",
                params={"headers": headers},
            )
        detail = "; ".join(parsed.errors[:3]) if parsed.errors else "no rows"
        raise ValidationError(
            f"The file could not be read as a bank statement ({detail}).",
            code="import_unreadable",
            message_key=parsed.error_key,
            params=parsed.error_params,
        )

    @staticmethod
    def file_digest(raw: bytes) -> str:
        """A keyed HMAC-SHA256 of the file, hex: same file, same digest.

        Keyed with the app secret (domain-separated), so the digest stored on
        the import run says nothing about the statement to someone without it.
        """
        key = hmac.new(settings.secret_key.encode(), _FILE_HMAC_CONTEXT, hashlib.sha256).digest()
        return hmac.new(key, raw, hashlib.sha256).hexdigest()

    async def run_for_idempotency_key(self, key: str) -> ImportRun | None:
        result = await self.session.execute(
            select(ImportRun).where(ImportRun.idempotency_key == key).order_by(ImportRun.id)
        )
        return result.scalars().first()

    async def run_for_file(self, account_id: int, digest: str) -> ImportRun | None:
        result = await self.session.execute(
            select(ImportRun)
            .where(ImportRun.account_id == account_id, ImportRun.file_hmac == digest)
            .order_by(ImportRun.id)
        )
        return result.scalars().first()

    async def lock_account(self, account_id: int) -> None:
        """Hold a transaction-scoped advisory lock on (family, account).

        Two imports into one account then run one after the other, so both
        cannot pass the duplicate check before either has written. ``apply``'s
        commit (or a rollback) releases it.
        """
        ctx = current_tenant()
        family = ctx.schema if ctx is not None else "public"
        family_key = zlib.crc32(family.encode()) & 0x7FFFFFFF
        await self.session.execute(select(func.pg_advisory_xact_lock(family_key, account_id)))

    @staticmethod
    def check_row_cap(parsed: ParseQueuedFileResult, max_rows: int | None = None) -> None:
        cap = settings.api_import_max_rows if max_rows is None else max_rows
        if len(parsed.rows) > cap:
            raise PayloadTooLargeError(
                f"The file has {len(parsed.rows)} rows; one request may import at most {cap}."
            )

    async def preview_upload(self, raw: bytes, options: ImportOptions) -> ImportPlan:
        """Parse and build, writing nothing (``dry_run``)."""
        parsed = await self.parse_upload(raw, options.filename)
        self.check_row_cap(parsed)
        return await self.build(parsed, options)

    async def import_upload(
        self,
        raw: bytes,
        options: ImportOptions,
        *,
        idempotency_key: str | None = None,
        allow_reimport: bool = False,
    ) -> ImportOutcome:
        """Parse, build and apply one uploaded file, under the account's lock.

        A repeated ``idempotency_key`` replays the run it created. The same
        file again for the same account is a ``ConflictError`` naming the
        earlier run, unless ``allow_reimport``.
        """
        try:
            if idempotency_key is not None:
                earlier = await self.run_for_idempotency_key(idempotency_key)
                if earlier is not None:
                    return self._replay(earlier, options.pairing_days)
            parsed = await self.parse_upload(raw, options.filename)
            self.check_row_cap(parsed)
            resolution = await self.resolve_account(
                filename=options.filename,
                profile=parsed.profile,
                metadata=parsed.metadata,
                account_id=options.account_id,
            )
            digest = self.file_digest(raw)
            if resolution.account_id is not None:
                await self.lock_account(resolution.account_id)
                if idempotency_key is not None:
                    # A twin request may have finished while this one waited.
                    earlier = await self.run_for_idempotency_key(idempotency_key)
                    if earlier is not None:
                        return self._replay(earlier, options.pairing_days)
                if not allow_reimport:
                    same_file = await self.run_for_file(resolution.account_id, digest)
                    if same_file is not None:
                        raise ConflictError(
                            f"This file was already imported into this account "
                            f"(import run {same_file.id}). Pass allow_reimport=true "
                            "to import it again.",
                            code="duplicate_file",
                            params={"import_run_id": same_file.id},
                        )
            plan = await self.build(parsed, options)
        except BaseException:
            await self.session.rollback()
            raise
        return await self.apply(plan, idempotency_key=idempotency_key, file_hmac=digest)

    @staticmethod
    def _replay(run: ImportRun, pairing_days: int) -> ImportOutcome:
        dates = [d for d in (run.row_date_min, run.row_date_max) if d is not None]
        return ImportOutcome(
            imported_count=run.imported_count,
            skipped=[],
            import_run_id=run.id,
            transfer_window=ImportService.transfer_review_window(
                dates, max_days_apart=pairing_days
            ),
            account_id=run.account_id,
            skipped_count=run.skipped_count,
            replayed=True,
        )

    async def preview_rows(self, plan: ImportPlan) -> list[PreviewRow]:
        """Every parsed row of ``plan``, kept or skipped, in file order."""
        payee_ids = {r.create.payee_id for r in plan.rows if r.create.payee_id is not None}
        payee_ids |= {s.create.payee_id for s in plan.skipped if s.create.payee_id is not None}
        names: dict[int, str] = {}
        if payee_ids:
            result = await self.session.execute(select(Payee).where(Payee.id.in_(payee_ids)))
            names = {p.id: p.name for p in result.scalars()}

        def _row(create: TransactionCreate, index: int, new: str | None, dup: bool) -> PreviewRow:
            payee = new if new is not None else names.get(create.payee_id or -1)
            return PreviewRow(
                row_index=index,
                date=create.date,
                amount=create.amount,
                type=create.type,
                description=create.description,
                category_id=create.category_id,
                payee_name=payee,
                duplicate=dup,
            )

        rows = [_row(r.create, r.row_index, r.new_payee, False) for r in plan.rows]
        rows += [_row(s.create, s.row_index, None, True) for s in plan.skipped]
        return sorted(rows, key=lambda r: r.row_index)
