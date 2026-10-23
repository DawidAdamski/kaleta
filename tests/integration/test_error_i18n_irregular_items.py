# SPDX-License-Identifier: AGPL-3.0-or-later
"""Irregular-fund-service domain-error toasts resolve a translation key.

A follow-up slice of ``errors-i18n-message-keys`` (the first cohort lives in
``test_error_i18n.py``; the transaction cohort in
``test_error_i18n_transactions.py``). ``IrregularItemService`` now carries
``message_key`` + ``params`` on its user-facing raises, so the toast renders
``t(message_key, **params)`` in the session's language while logs, event
capture and the API keep reading the English ``exc.message`` (see
``KaletaError`` and ``views.error_handling._notify_with_event``).

Covers: KAL-ERR-003
"""

from __future__ import annotations

import datetime
import json
import pathlib
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import KaletaError, NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.irregular_item import IrregularPaymentCreate
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundKind
from kaleta.services import AccountService, ReserveFundService
from kaleta.services.irregular_item_service import IrregularItemService
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every irregular-item cohort key with a representative set of params — the
#: placeholder names must match what the raise sites pass.
_IRREGULAR_COHORT: dict[str, dict[str, object]] = {
    "errors.irregular_item.fund_not_found": {"fund_id": 123},
    "errors.irregular_item.not_irregular_fund": {},
    "errors.irregular_item.item_not_found": {"item_id": 7},
    "errors.irregular_item.fund_needs_account": {},
    "errors.irregular_item.add_item_before_planning": {},
    "errors.irregular_item.source_must_differ": {},
    "errors.irregular_item.account_not_found": {},
    "errors.irregular_item.transfer_already_planned": {},
    "errors.irregular_item.planned_transfer_not_found": {},
    "errors.irregular_item.fund_no_account": {},
    "errors.irregular_item.item_other_fund": {},
    "errors.irregular_item.payment_needs_category": {},
    "errors.irregular_item.transaction_not_found": {"transaction_id": 55},
    "errors.irregular_item.only_expense_is_payment": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestIrregularCohortKeysInterpolate:
    def test_both_locales_carry_every_irregular_key(self) -> None:
        for key in _IRREGULAR_COHORT:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _IRREGULAR_COHORT.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeIrregularToastReadsInEachLanguage:
    """The representative irregular-fund errors — literals from KAL-ERR-003."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.irregular_item.payment_needs_category")
        assert text == "Wybierz kategorię płatności."

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.irregular_item.payment_needs_category")
        assert text == "Choose a category for the payment."

    def test_interpolated_polish_message(self) -> None:
        text = _resolve("pl", "errors.irregular_item.fund_not_found").format(fund_id=123)
        assert text == "Nie znaleziono funduszu 123."


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestMigratedIrregularRaisesCarryWorkingKeys:
    """Drive the real irregular-item-service raises and resolve their keys."""

    async def test_missing_fund_carries_its_key(self, session: AsyncSession) -> None:
        svc = IrregularItemService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.plan(123)
        _assert_localizes(missing.value, "errors.irregular_item.fund_not_found")
        # The English fallback is untouched — logs and the API still read it.
        assert missing.value.message == "Fund 123 not found."

    async def test_payment_without_category_carries_its_key(self, session: AsyncSession) -> None:
        account = await AccountService(session).create(
            AccountCreate(
                name="Konto funduszu", type=AccountType.SAVINGS, balance=Decimal("1500.00")
            )
        )
        fund = await ReserveFundService(session).create(
            ReserveFundCreate(
                name="Wydatki nieregularne",
                kind=ReserveFundKind.IRREGULAR,
                target_amount=Decimal("3000.00"),
                backing_account_id=account.id,
            )
        )
        svc = IrregularItemService(session)
        with pytest.raises(ValidationError) as missing:
            # No item and no category → the service cannot pick one.
            await svc.record_payment(
                fund.id,
                IrregularPaymentCreate(
                    item_id=None,
                    amount=Decimal("100.00"),
                    date=datetime.date(2026, 10, 5),
                    category_id=None,
                ),
            )
        _assert_localizes(missing.value, "errors.irregular_item.payment_needs_category")
        assert missing.value.message == "Choose a category for the payment."
        # The Polish toast renders the same sentence.
        assert _resolve("pl", "errors.irregular_item.payment_needs_category") == (
            "Wybierz kategorię płatności."
        )


class TestResolveToastTextForIrregularItems:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_a_migrated_irregular_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the key reproduces the English fallback exactly.
        exc = ValidationError(
            "ignored fallback",
            message_key="errors.irregular_item.payment_needs_category",
        )
        assert resolve_toast_text(exc) == "Choose a category for the payment."
