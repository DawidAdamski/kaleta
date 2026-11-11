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
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.exceptions import ValidationError
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.account_service import AccountService
from kaleta.services.import_profiles import MBANK_PROFILE
from kaleta.services.import_rule_service import ImportRuleService
from kaleta.services.import_service import (
    ImportReadinessCheck,
    ImportService,
    MBankFileMetadata,
    ParseQueuedFileResult,
    build_known_account_digits,
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


@dataclass(frozen=True, slots=True)
class SkippedRow:
    """A parsed row that is not imported, and why (``SKIP_DUPLICATE``)."""

    create: TransactionCreate
    reason: str


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

        kept: list[tuple[TransactionCreate, str | None]] = []
        skipped: list[SkippedRow] = []
        for create, new_payee in drafts:
            if options.skip_duplicates and await imports.find_duplicate(
                account_id=create.account_id,
                date=create.date,
                amount=create.amount,
                description=create.description,
            ):
                skipped.append(SkippedRow(create=create, reason=SKIP_DUPLICATE))
            else:
                kept.append((create, new_payee))

        categorised = await imports.apply_categorisation_rules(
            [create for create, _ in kept],
            new_payee_names=[new_payee for _, new_payee in kept],
        )
        rows = [
            PlannedRow(create=create, new_payee=new_payee)
            for create, (_, new_payee) in zip(categorised, kept, strict=True)
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

    async def apply(self, plan: ImportPlan) -> ImportOutcome:
        """Write the plan and commit once; on any error roll everything back."""
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
        )
