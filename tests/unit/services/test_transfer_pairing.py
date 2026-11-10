# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for transfer pairing: the guards, the suggester and accept-all."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType, TransferDirection
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import (
    TransactionCreate,
    TransactionSplitCreate,
    TransactionUpdate,
)
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.import_service import ImportService
from kaleta.services.transaction_service import (
    DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    DEFAULT_TRANSFER_PAIRING_DAYS,
)
from kaleta.views.settings.constants import (
    DEFAULT_TRANSFER_AMOUNT_TOLERANCE as SETTINGS_TOLERANCE,
)
from kaleta.views.settings.constants import (
    DEFAULT_TRANSFER_PAIRING_DAYS as SETTINGS_PAIRING_DAYS,
)

DAY = datetime.date(2026, 7, 1)


class _Ledger:
    """Two PLN accounts, one EUR account and a category per direction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.svc = TransactionService(session)
        self.mbank = 0
        self.pko = 0
        self.wise_eur = 0
        self.spend = 0
        self.earn = 0

    async def setup(self) -> _Ledger:
        accounts = AccountService(self.session)
        self.mbank = (
            await accounts.create(AccountCreate(name="mBank", type=AccountType.CHECKING))
        ).id
        self.pko = (await accounts.create(AccountCreate(name="PKO", type=AccountType.CHECKING))).id
        self.wise_eur = (
            await accounts.create(
                AccountCreate(name="Wise EUR", type=AccountType.CHECKING, currency="EUR")
            )
        ).id
        categories = CategoryService(self.session)
        self.spend = (
            await categories.create(CategoryCreate(name="Other", type=CategoryType.EXPENSE))
        ).id
        self.earn = (
            await categories.create(CategoryCreate(name="Inflow", type=CategoryType.INCOME))
        ).id
        return self

    async def row(
        self,
        account_id: int,
        tx_type: TransactionType,
        amount: str = "500.00",
        day: datetime.date = DAY,
        **extra: object,
    ) -> int:
        category_id: int | None = None
        if tx_type == TransactionType.EXPENSE:
            category_id = self.spend
        elif tx_type == TransactionType.INCOME:
            category_id = self.earn
        data: dict[str, object] = {
            "account_id": account_id,
            "category_id": category_id,
            "amount": Decimal(amount),
            "type": tx_type,
            "date": day,
            "description": "row",
            "is_internal_transfer": tx_type == TransactionType.TRANSFER,
            "transfer_direction": (
                TransferDirection.OUT if tx_type == TransactionType.TRANSFER else None
            ),
        }
        data.update(extra)
        return (await self.svc.create(TransactionCreate.model_validate(data))).id


@pytest.fixture
async def ledger(session: AsyncSession) -> _Ledger:
    return await _Ledger(session).setup()


# ── TransactionService.pair_as_transfer guards ───────────────────────────────


class TestPairAsTransferGuards:
    async def test_same_row_twice_is_rejected(self, ledger: _Ledger) -> None:
        tx = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        with pytest.raises(ValidationError):
            await ledger.svc.pair_as_transfer(tx, tx)

    async def test_missing_row_is_not_found(self, ledger: _Ledger) -> None:
        tx = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        with pytest.raises(NotFoundError):
            await ledger.svc.pair_as_transfer(tx, 9999)

    async def test_same_account_is_rejected(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.mbank, TransactionType.INCOME)
        with pytest.raises(ValidationError, match="different accounts"):
            await ledger.svc.pair_as_transfer(out, inc)

    async def test_different_amounts_are_rejected(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "500.00")
        inc = await ledger.row(ledger.pko, TransactionType.INCOME, "499.00")
        with pytest.raises(ValidationError, match="same amount"):
            await ledger.svc.pair_as_transfer(out, inc)

    async def test_tolerance_allows_a_grosz(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "500.00")
        inc = await ledger.row(ledger.pko, TransactionType.INCOME, "499.99")
        out_leg, in_leg = await ledger.svc.pair_as_transfer(
            out, inc, amount_tolerance=Decimal("0.01")
        )
        assert out_leg.linked_transaction_id == in_leg.id

    async def test_two_expenses_are_rejected(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        other = await ledger.row(ledger.pko, TransactionType.EXPENSE)
        with pytest.raises(ValidationError, match="incoming leg"):
            await ledger.svc.pair_as_transfer(out, other)

    async def test_income_as_outgoing_leg_is_rejected(self, ledger: _Ledger) -> None:
        inc = await ledger.row(ledger.mbank, TransactionType.INCOME)
        out = await ledger.row(ledger.pko, TransactionType.EXPENSE)
        with pytest.raises(ValidationError, match="outgoing leg"):
            await ledger.svc.pair_as_transfer(inc, out)

    async def test_cross_currency_is_rejected(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.wise_eur, TransactionType.INCOME)
        with pytest.raises(ValidationError, match="currencies"):
            await ledger.svc.pair_as_transfer(out, inc)

    async def test_already_linked_row_conflicts(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        await ledger.svc.pair_as_transfer(out, inc)
        other = await ledger.row(ledger.pko, TransactionType.INCOME)
        with pytest.raises(ConflictError):
            await ledger.svc.pair_as_transfer(out, other)

    async def test_split_row_is_rejected(self, ledger: _Ledger) -> None:
        out = await ledger.row(
            ledger.mbank,
            TransactionType.EXPENSE,
            category_id=None,
            is_split=True,
            splits=[
                TransactionSplitCreate(category_id=ledger.spend, amount=Decimal("500.00")),
            ],
        )
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        with pytest.raises(ValidationError, match="split"):
            await ledger.svc.pair_as_transfer(out, inc)

    async def test_flagged_transfer_leg_pairs_with_income(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.TRANSFER)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        _, in_leg = await ledger.svc.pair_as_transfer(out, inc)
        assert in_leg.type == TransactionType.TRANSFER
        assert in_leg.category_id is None


class TestPairSelectedAsTransfer:
    async def test_income_picked_first_still_goes_in(self, ledger: _Ledger) -> None:
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        await ledger.svc.pair_selected_as_transfer(inc, out)
        out_leg = await ledger.svc.get(out)
        assert out_leg is not None
        assert out_leg.type == TransactionType.TRANSFER
        assert out_leg.linked_transaction_id == inc

    async def test_two_incomes_are_rejected(self, ledger: _Ledger) -> None:
        first = await ledger.row(ledger.mbank, TransactionType.INCOME)
        second = await ledger.row(ledger.pko, TransactionType.INCOME)
        with pytest.raises(ValidationError):
            await ledger.svc.pair_selected_as_transfer(first, second)

    async def test_missing_row_is_not_found(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        with pytest.raises(NotFoundError):
            await ledger.svc.pair_selected_as_transfer(out, 9999)


# ── ImportService.suggest_transfer_pairs ────────────────────────────────────


class TestSuggestTransferPairs:
    async def test_orients_expense_out_and_income_in(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        # Income created first, so id order alone would get the direction wrong.
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        [pair] = await ImportService(session).suggest_transfer_pairs()
        assert (pair.outgoing_id, pair.incoming_id) == (out, inc)
        assert pair.outgoing_account == "mBank"
        assert pair.incoming_account == "PKO"
        assert pair.amount == Decimal("500.00")
        assert pair.currency == "PLN"

    async def test_ignores_rows_outside_the_window(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        await ledger.row(ledger.mbank, TransactionType.EXPENSE, day=DAY)
        await ledger.row(ledger.pko, TransactionType.INCOME, day=DAY + datetime.timedelta(days=4))
        imports = ImportService(session)
        assert await imports.suggest_transfer_pairs(max_days_apart=3) == []
        assert len(await imports.suggest_transfer_pairs(max_days_apart=4)) == 1

    async def test_ignores_same_direction_same_account_and_other_currency(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        await ledger.row(ledger.pko, TransactionType.EXPENSE)
        await ledger.row(ledger.mbank, TransactionType.INCOME, "80.00")
        await ledger.row(ledger.mbank, TransactionType.EXPENSE, "80.00")
        await ledger.row(ledger.wise_eur, TransactionType.INCOME)
        assert await ImportService(session).suggest_transfer_pairs() == []

    async def test_each_row_in_one_pair_closest_date_wins(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        far = await ledger.row(ledger.pko, TransactionType.INCOME, day=DAY)
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, day=DAY + _days(2))
        near = await ledger.row(ledger.pko, TransactionType.INCOME, day=DAY + _days(3))
        [pair] = await ImportService(session).suggest_transfer_pairs()
        assert (pair.outgoing_id, pair.incoming_id) == (out, near)
        assert far not in (pair.outgoing_id, pair.incoming_id)

    async def test_date_bounds_limit_the_rows(self, ledger: _Ledger, session: AsyncSession) -> None:
        await ledger.row(ledger.mbank, TransactionType.EXPENSE, day=DAY)
        await ledger.row(ledger.pko, TransactionType.INCOME, day=DAY)
        imports = ImportService(session)
        assert await imports.suggest_transfer_pairs(date_from=DAY + _days(1)) == []
        assert await imports.suggest_transfer_pairs(date_to=DAY - _days(1)) == []
        assert len(await imports.suggest_transfer_pairs(date_from=DAY, date_to=DAY)) == 1

    async def test_dismissal_holds_either_way_round_and_is_idempotent(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        imports = ImportService(session)
        await imports.dismiss_transfer_pair(inc, out)
        await imports.dismiss_transfer_pair(out, inc)
        assert await imports.suggest_transfer_pairs() == []


# ── ImportService.detect_and_link_transfers (accept all) ─────────────────────


class TestDetectAndLinkTransfers:
    async def test_links_flagged_transfer_legs(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        first = await ledger.row(ledger.mbank, TransactionType.TRANSFER)
        second = await ledger.row(ledger.pko, TransactionType.TRANSFER, day=DAY + _days(1))
        assert await ImportService(session).detect_and_link_transfers() == 1
        leg = await ledger.svc.get(first)
        assert leg is not None
        assert leg.linked_transaction_id == second

    async def test_links_ordinary_income_and_expense(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        assert await ImportService(session).detect_and_link_transfers() == 1
        for tx_id, partner in ((out, inc), (inc, out)):
            leg = await ledger.svc.get(tx_id)
            assert leg is not None
            assert leg.type == TransactionType.TRANSFER
            assert leg.is_internal_transfer is True
            assert leg.linked_transaction_id == partner

    async def test_skips_dismissed_pairs_and_counts_zero(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        imports = ImportService(session)
        await imports.dismiss_transfer_pair(out, inc)
        assert await imports.detect_and_link_transfers() == 0
        leg = await ledger.svc.get(out)
        assert leg is not None
        assert leg.type == TransactionType.EXPENSE

    async def test_already_linked_rows_are_left_alone(
        self, ledger: _Ledger, session: AsyncSession
    ) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        await ledger.svc.pair_as_transfer(out, inc)
        await ledger.row(ledger.pko, TransactionType.INCOME)
        assert await ImportService(session).detect_and_link_transfers() == 0


# ── TransactionService: the pairing's service home ──────────────────────────


class TestTransactionServicePairing:
    async def test_suggestions_carry_account_ids_and_leg_amounts(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "3123.86")
        inc = await ledger.row(ledger.pko, TransactionType.INCOME, "3123.86", day=DAY + _days(2))
        [pair] = await ledger.svc.suggest_transfer_pairs()
        assert (pair.outgoing_id, pair.incoming_id) == (out, inc)
        assert (pair.outgoing_account_id, pair.incoming_account_id) == (ledger.mbank, ledger.pko)
        assert pair.outgoing_amount == pair.incoming_amount == Decimal("3123.86")

    async def test_one_tolerance_for_pairing_by_hand_and_accepting(self, ledger: _Ledger) -> None:
        assert Decimal("0.01") == DEFAULT_TRANSFER_AMOUNT_TOLERANCE
        assert SETTINGS_TOLERANCE is DEFAULT_TRANSFER_AMOUNT_TOLERANCE
        assert SETTINGS_PAIRING_DAYS == DEFAULT_TRANSFER_PAIRING_DAYS == 3
        # pair_as_transfer used to default to 0: a grosz apart now pairs by default.
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "500.00")
        inc = await ledger.row(ledger.pko, TransactionType.INCOME, "499.99")
        out_leg, _ = await ledger.svc.pair_as_transfer(out, inc)
        assert out_leg.linked_transaction_id == inc
        far_out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "500.00")
        far_in = await ledger.row(ledger.pko, TransactionType.INCOME, "499.98")
        with pytest.raises(ValidationError, match="same amount"):
            await ledger.svc.accept_transfer_pair(far_out, far_in)

    async def test_dismiss_checks_the_rows_exist(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        with pytest.raises(NotFoundError):
            await ledger.svc.dismiss_transfer_pair(out, 9999)
        with pytest.raises(ValidationError):
            await ledger.svc.dismiss_transfer_pair(out, out)

    async def test_pairing_a_linked_pair_again_changes_nothing(self, ledger: _Ledger) -> None:
        # Two import-typed transfer legs, the higher id the outgoing one: re-pairing
        # must not fall back to "lower id goes out" and flip them.
        inc = await ledger.row(ledger.pko, TransactionType.TRANSFER, transfer_direction="in")
        out = await ledger.row(ledger.mbank, TransactionType.TRANSFER)
        out_leg, in_leg = await ledger.svc.pair_as_transfer(out, inc)
        stamp = (out_leg.updated_at, in_leg.updated_at)
        again_out, again_in = await ledger.svc.pair_selected_as_transfer(inc, out)
        assert (again_out.id, again_in.id) == (out, inc)
        assert again_out.transfer_direction == TransferDirection.OUT
        assert (again_out.updated_at, again_in.updated_at) == stamp


class TestUpdateLinksBothSides:
    """``TransactionService.update`` → ``_apply_link_update`` / ``_link_by_update``."""

    async def test_linked_row_turned_into_transfer_writes_its_partner(
        self, ledger: _Ledger
    ) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        # A half link, as a client could leave one before links were checked.
        inc = await ledger.row(ledger.pko, TransactionType.INCOME, linked_transaction_id=out)
        await ledger.svc.update(inc, TransactionUpdate(type=TransactionType.TRANSFER))
        out_leg = await ledger.svc.get(out)
        in_leg = await ledger.svc.get(inc)
        assert out_leg is not None and in_leg is not None
        assert out_leg.type == TransactionType.TRANSFER
        assert out_leg.linked_transaction_id == inc
        assert (out_leg.transfer_direction, in_leg.transfer_direction) == (
            TransferDirection.OUT,
            TransferDirection.IN,
        )

    async def test_linked_row_turned_into_transfer_is_validated(self, ledger: _Ledger) -> None:
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE, "500.00")
        inc = await ledger.row(
            ledger.pko, TransactionType.INCOME, "400.00", linked_transaction_id=out
        )
        with pytest.raises(ValidationError, match="same amount"):
            await ledger.svc.update(inc, TransactionUpdate(type=TransactionType.TRANSFER))

    async def test_link_moved_to_another_account_reads_that_currency(self, ledger: _Ledger) -> None:
        """``_link_by_update`` re-reads the account when the same PUT moves the row.

        Without the re-read the check would compare PKO (PLN) with mBank (PLN)
        and pass; the row is really going to the EUR account.
        """
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        with pytest.raises(ValidationError, match="currencies"):
            await ledger.svc.update(
                inc, TransactionUpdate(account_id=ledger.wise_eur, linked_transaction_id=out)
            )

    async def test_link_moved_to_a_missing_account_is_not_found(self, ledger: _Ledger) -> None:
        """``_link_by_update``: the new account is gone → ``account_not_found``."""
        out = await ledger.row(ledger.mbank, TransactionType.EXPENSE)
        inc = await ledger.row(ledger.pko, TransactionType.INCOME)
        with pytest.raises(NotFoundError) as caught:
            await ledger.svc.update(
                inc, TransactionUpdate(account_id=999_999, linked_transaction_id=out)
            )
        assert caught.value.message_key == "errors.transaction.account_not_found"


class TestTransferReviewWindow:
    def test_widens_the_imported_span_by_the_window(self) -> None:
        window = ImportService.transfer_review_window(
            [DAY + _days(5), DAY, DAY + _days(2)], max_days_apart=3
        )
        assert window == (DAY - _days(3), DAY + _days(8))

    def test_nothing_imported_has_no_window(self) -> None:
        assert ImportService.transfer_review_window([], max_days_apart=3) is None


def _days(n: int) -> datetime.timedelta:
    return datetime.timedelta(days=n)
