# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core-CRUD service domain-error toasts resolve a translation key.

A follow-up cohort slice of ``errors-i18n-message-keys`` (the first cohort
lives in ``test_error_i18n.py``, the transaction cohort in
``test_error_i18n_transactions.py``, the funds cohort in
``test_error_i18n_funds_cohort.py``). ``RuleService``,
``SubscriptionService``, ``CategoryService``, ``BudgetService`` and
``AccountService`` now carry ``message_key`` + ``params`` on their
user-facing raises, so the toast renders ``t(message_key, **params)`` in the
session's language while logs, event capture and the API keep reading the
English ``exc.message`` (see ``KaletaError`` and
``views.error_handling._notify_with_event``).

Covers: KAL-ERR-005
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import ConflictError, KaletaError, NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.categorisation_rule import CategorisationRuleUpdate
from kaleta.schemas.category import CategoryCreate
from kaleta.services.account_service import AccountService
from kaleta.services.budget_service import BudgetService
from kaleta.services.category_service import CategoryService
from kaleta.services.rule_service import RuleService
from kaleta.services.subscription_service import SubscriptionService
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every core-cohort key with a representative set of params — the
#: placeholder names must match what the raise sites pass.
_CORE_COHORT: dict[str, dict[str, object]] = {
    "errors.rule.pattern_empty": {},
    "errors.rule.only_contains_mode": {},
    "errors.rule.rule_not_found": {"rule_id": 999_999},
    "errors.rule.category_not_found": {"category_id": 42},
    "errors.subscription.candidate_needs_account": {},
    "errors.subscription.planned_needs_name": {},
    "errors.subscription.planned_needs_positive_amount": {},
    "errors.subscription.not_found": {"sub_id": 7},
    "errors.category.parent_not_found": {"parent_id": 999_999},
    "errors.category.type_must_match_parent": {
        "category_type": "expense",
        "parent_type": "income",
    },
    "errors.category.name_exists": {"name": "Food"},
    "errors.category.subscriptions_root_protected": {},
    "errors.budget.year_required": {},
    "errors.account.ambiguous_external_number": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestCoreCohortKeysInterpolate:
    def test_both_locales_carry_every_cohort_key(self) -> None:
        for key in _CORE_COHORT:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _CORE_COHORT.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeCoreToastReadsInEachLanguage:
    """The representative core-CRUD errors — literals from KAL-ERR-005."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.budget.year_required")
        assert text == "Należy wybrać co najmniej jeden rok"

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.budget.year_required")
        assert text == "At least one year must be selected"

    def test_polish_message_with_param(self) -> None:
        text = _resolve("pl", "errors.rule.rule_not_found").format(rule_id=7)
        assert text == "Nie znaleziono reguły kategoryzacji 7."


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestMigratedCohortRaisesCarryWorkingKeys:
    """Drive a real raise from each of the five core-CRUD services."""

    async def test_rule_missing_rule_carries_its_key(self, session: AsyncSession) -> None:
        svc = RuleService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.update(999_999, CategorisationRuleUpdate())
        _assert_localizes(missing.value, "errors.rule.rule_not_found")
        # The English fallback is untouched — logs and the API still read it.
        assert missing.value.message == "Categorisation rule 999999 not found."

    async def test_subscription_missing_sub_carries_its_key(self, session: AsyncSession) -> None:
        svc = SubscriptionService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.refile(999_999, None)
        _assert_localizes(missing.value, "errors.subscription.not_found")
        assert missing.value.message == "Subscription id=999999 not found"

    async def test_category_missing_parent_carries_its_key(self, session: AsyncSession) -> None:
        svc = CategoryService(session)
        with pytest.raises(NotFoundError) as missing:
            await svc.create(
                CategoryCreate(name="Orphan", type=CategoryType.EXPENSE, parent_id=999_999)
            )
        _assert_localizes(missing.value, "errors.category.parent_not_found")
        assert missing.value.message == "Parent category id=999999 not found"

    async def test_budget_no_year_carries_its_key(self, session: AsyncSession) -> None:
        svc = BudgetService(session)
        with pytest.raises(ValidationError) as no_year:
            await svc.load_annual_plan_grid([])
        _assert_localizes(no_year.value, "errors.budget.year_required")
        assert no_year.value.message == "At least one year must be selected"

    async def test_account_ambiguous_number_carries_its_key(self, session: AsyncSession) -> None:
        svc = AccountService(session)
        first = await svc.create(
            AccountCreate(name="PKO One", type=AccountType.CHECKING, balance=Decimal("0.00"))
        )
        second = await svc.create(
            AccountCreate(name="PKO Two", type=AccountType.CHECKING, balance=Decimal("0.00"))
        )
        # Two accounts whose external numbers end with the same digits — the
        # ambiguity the importer refuses to resolve.
        await svc.save_external_number(first.id, "0011112222")
        await svc.save_external_number(second.id, "0011112222")
        with pytest.raises(ConflictError) as ambiguous:
            await svc.find_by_external_number("0011112222")
        _assert_localizes(ambiguous.value, "errors.account.ambiguous_external_number")
        assert ambiguous.value.message == "More than one account matches that account number."


class TestResolveToastTextForCoreCohort:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_a_migrated_cohort_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the key reproduces the English fallback exactly.
        exc = ValidationError(
            "ignored fallback",
            message_key="errors.budget.year_required",
        )
        assert resolve_toast_text(exc) == "At least one year must be selected"
