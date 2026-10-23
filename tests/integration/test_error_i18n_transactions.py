# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transaction-service domain-error toasts resolve a translation key.

A follow-up slice of ``errors-i18n-message-keys`` (the first cohort lives in
``test_error_i18n.py``). ``TransactionService`` now carries ``message_key`` +
``params`` on its user-facing raises, so the toast renders
``t(message_key, **params)`` in the session's language while logs, event
capture and the API keep reading the English ``exc.message`` (see
``KaletaError`` and ``views.error_handling._notify_with_event``).

Covers: KAL-ERR-002
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import KaletaError, NotFoundError, ValidationError
from kaleta.schemas.transaction import TransactionSplitCreate
from kaleta.services.transaction_service import TransactionService
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every transaction cohort key with a representative set of params — the
#: placeholder names must match what the raise sites pass.
_TRANSACTION_COHORT: dict[str, dict[str, object]] = {
    "errors.transaction.transfer_needs_two_rows": {},
    "errors.transaction.not_found": {},
    "errors.transaction.not_found_id": {"transaction_id": 999_999},
    "errors.transaction.transfer_needs_both_directions": {},
    "errors.transaction.category_not_found": {"category_id": 42},
    "errors.transaction.only_income_expense_categories": {},
    "errors.transaction.split_category_per_line": {},
    "errors.transaction.category_type_mismatch": {"category_type": "income"},
    "errors.transaction.outgoing_leg_not_income": {},
    "errors.transaction.incoming_leg_not_expense": {},
    "errors.transaction.transfer_different_accounts": {},
    "errors.transaction.transfer_currency_mismatch": {},
    "errors.transaction.transfer_amount_mismatch": {},
    "errors.transaction.already_linked": {"transaction_id": 7},
    "errors.transaction.split_cannot_be_transfer": {},
    "errors.transaction.split_needs_at_least_one": {},
    "errors.transaction.split_sum_mismatch": {
        "amount": Decimal("100.00"),
        "remaining": Decimal("-3.50"),
    },
    "errors.transaction.split_amount_needs_splits": {},
    "errors.transaction.type_requires_category": {"transaction_type": "Income"},
    "errors.transaction.stale_write_by_member": {"changed_by": "ania"},
    "errors.transaction.stale_write_elsewhere": {},
    "errors.transaction.transfer_leg_needs_direction": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestTransactionCohortKeysInterpolate:
    def test_both_locales_carry_every_transaction_key(self) -> None:
        for key in _TRANSACTION_COHORT:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _TRANSACTION_COHORT.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeTransactionToastReadsInEachLanguage:
    """The representative transfer-pairing error — literals from KAL-ERR-002."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.transaction.transfer_needs_two_rows")
        assert text == "Przelew wymaga dwóch różnych transakcji."

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.transaction.transfer_needs_two_rows")
        assert text == "A transfer needs two different transactions."

    def test_interpolated_polish_message(self) -> None:
        text = _resolve("pl", "errors.transaction.split_sum_mismatch").format(
            amount=Decimal("100.00"), remaining=Decimal("-3.50")
        )
        assert text == "Kwoty pozycji muszą sumować się do 100.00; pozostało -3.50."


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestMigratedTransactionRaisesCarryWorkingKeys:
    """Drive the real transaction-service raises and resolve their keys."""

    async def test_same_row_transfer_carries_its_key(self, session: AsyncSession) -> None:
        svc = TransactionService(session)
        with pytest.raises(ValidationError) as same:
            await svc.pair_as_transfer(1, 1)
        _assert_localizes(same.value, "errors.transaction.transfer_needs_two_rows")
        # The English fallback is untouched — logs and the API still read it.
        assert same.value.message == "A transfer needs two different transactions."

    async def test_missing_row_pairing_carries_its_key(self, session: AsyncSession) -> None:
        # ``pair_as_transfer`` is also reached directly from the import view's
        # "accept transfer pair" (ImportService.accept_transfer_pair), where a
        # suggested row deleted before the click surfaces this toast.
        svc = TransactionService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.pair_as_transfer(999_999, 888_888)
        _assert_localizes(missing.value, "errors.transaction.not_found_id")
        assert missing.value.message == "Transaction 999999 not found."

    def test_split_sum_mismatch_carries_its_key(self) -> None:
        with pytest.raises(ValidationError) as mismatch:
            TransactionService._validate_split_sum(
                Decimal("100.00"), [TransactionSplitCreate(amount=Decimal("103.50"))]
            )
        _assert_localizes(mismatch.value, "errors.transaction.split_sum_mismatch")
        assert mismatch.value.message == "Split amounts must sum to 100.00; -3.50 remaining."
        # The Polish toast renders the same interpolated figures.
        pl = _resolve("pl", "errors.transaction.split_sum_mismatch").format(
            **(mismatch.value.params or {})
        )
        assert pl == "Kwoty pozycji muszą sumować się do 100.00; pozostało -3.50."


class TestResolveToastTextForTransactions:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_a_migrated_transaction_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the key reproduces the English fallback exactly.
        exc = ValidationError(
            "ignored fallback",
            message_key="errors.transaction.transfer_needs_two_rows",
        )
        assert resolve_toast_text(exc) == "A transfer needs two different transactions."
