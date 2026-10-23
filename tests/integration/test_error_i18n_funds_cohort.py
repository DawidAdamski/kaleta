# SPDX-License-Identifier: AGPL-3.0-or-later
"""Funds/salary/debt service domain-error toasts resolve a translation key.

A follow-up cohort slice of ``errors-i18n-message-keys`` (the first cohort
lives in ``test_error_i18n.py``, the transaction cohort in
``test_error_i18n_transactions.py``). ``ReserveFundService``, ``GiftService``,
``SalaryService`` and ``PersonalLoanService`` now carry ``message_key`` +
``params`` on their user-facing raises, so the toast renders
``t(message_key, **params)`` in the session's language while logs, event
capture and the API keep reading the English ``exc.message`` (see
``KaletaError`` and ``views.error_handling._notify_with_event``).

Covers: KAL-ERR-004
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
from kaleta.models.personal_loan import LoanDirection
from kaleta.schemas.personal_loan import PersonalLoanCreate
from kaleta.schemas.reserve_fund import GoalContribution
from kaleta.services.gift_service import GiftService
from kaleta.services.personal_loan_service import PersonalLoanService
from kaleta.services.reserve_fund_service import ReserveFundService
from kaleta.services.salary_service import SalaryService
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every funds-cohort key with a representative set of params — the
#: placeholder names must match what the raise sites pass.
_FUNDS_COHORT: dict[str, dict[str, object]] = {
    "errors.reserve_fund.multiplier_required_for_spending_target": {},
    "errors.reserve_fund.fund_not_found": {"fund_id": 999_999},
    "errors.reserve_fund.only_goal_contributes": {},
    "errors.reserve_fund.goal_already_closed": {},
    "errors.reserve_fund.goal_no_backing_account": {},
    "errors.reserve_fund.account_to_itself": {},
    "errors.reserve_fund.account_not_found": {"account_id": 42},
    "errors.reserve_fund.same_currency_required": {},
    "errors.gift.not_found": {"gift_id": 999_999},
    "errors.gift.transaction_not_found": {"transaction_id": 7},
    "errors.gift.only_expense_pays": {},
    "errors.gift.transaction_pays_another": {},
    "errors.salary.window_at_least_one_month": {},
    "errors.salary.override_not_negative": {},
    "errors.salary.source_target_differ": {},
    "errors.salary.account_not_found": {"account_id": 42},
    "errors.personal_loan.link_ambiguous": {},
    "errors.personal_loan.transaction_taken": {"transaction_id": 7},
    "errors.personal_loan.transaction_not_found": {"transaction_id": 999_999},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestFundsCohortKeysInterpolate:
    def test_both_locales_carry_every_cohort_key(self) -> None:
        for key in _FUNDS_COHORT:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _FUNDS_COHORT.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeFundsToastReadsInEachLanguage:
    """The representative reserve-fund error — literals from KAL-ERR-004."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.reserve_fund.fund_not_found").format(fund_id=999_999)
        assert text == "Nie znaleziono funduszu rezerwowego 999999."

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.reserve_fund.fund_not_found").format(fund_id=999_999)
        assert text == "Reserve fund 999999 not found."


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestMigratedCohortRaisesCarryWorkingKeys:
    """Drive a real raise from each of the four cohort services."""

    async def test_reserve_fund_missing_fund_carries_its_key(self, session: AsyncSession) -> None:
        svc = ReserveFundService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.contribute(
                999_999,
                GoalContribution(
                    amount=Decimal("10.00"),
                    from_account_id=1,
                    date=datetime.date(2026, 1, 1),
                ),
            )
        _assert_localizes(missing.value, "errors.reserve_fund.fund_not_found")
        # The English fallback is untouched — logs and the API still read it.
        assert missing.value.message == "Reserve fund 999999 not found."

    async def test_gift_missing_gift_carries_its_key(self, session: AsyncSession) -> None:
        svc = GiftService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.delete(999_999)
        _assert_localizes(missing.value, "errors.gift.not_found")
        assert missing.value.message == "Gift 999999 not found"

    async def test_salary_zero_window_carries_its_key(self, session: AsyncSession) -> None:
        svc = SalaryService(session)
        with pytest.raises(ValidationError) as bad_window:
            await svc.income_by_month(window_months=0)
        _assert_localizes(bad_window.value, "errors.salary.window_at_least_one_month")
        assert bad_window.value.message == "Income window must span at least one month."

    async def test_personal_loan_missing_transaction_carries_its_key(
        self, session: AsyncSession
    ) -> None:
        svc = PersonalLoanService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.create_loan(
                PersonalLoanCreate(
                    counterparty_id=1,
                    direction=LoanDirection.OUTGOING,
                    principal=Decimal("100.00"),
                    opened_at=datetime.date(2026, 1, 1),
                    transaction_id=999_999,
                )
            )
        _assert_localizes(missing.value, "errors.personal_loan.transaction_not_found")
        assert missing.value.message == "Transaction 999999 not found"


class TestResolveToastTextForFundsCohort:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_a_migrated_cohort_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the key reproduces the English fallback exactly.
        exc = ValidationError(
            "ignored fallback",
            message_key="errors.salary.source_target_differ",
        )
        assert resolve_toast_text(exc) == "Salary source and target accounts must differ."
