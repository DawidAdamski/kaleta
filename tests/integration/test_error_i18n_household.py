# SPDX-License-Identifier: AGPL-3.0-or-later
"""Household-sharing service domain-error toasts resolve a translation key.

A follow-up slice of ``errors-i18n-message-keys`` (the first cohort lives in
``test_error_i18n.py``; the transaction, funds, irregular-item and core-CRUD
cohorts in their own ``test_error_i18n_*`` modules). ``HouseholdService``,
``HouseholdRekey`` and ``HouseholdInvitations`` now carry ``message_key`` +
``params`` on their user-facing raises, so the toast renders
``t(message_key, **params)`` in the session's language while logs, event
capture and the API keep reading the English ``exc.message`` (see
``KaletaError`` and ``views.error_handling._notify_with_event``).

Household flows need a signed-in membership and tenant wiring to drive end to
end, so the two guards reachable from an in-memory membership
(``_require_active`` → ``membership_pending`` and ``_require_owner`` →
``only_owner``) are driven as real raises; every household key is additionally
covered by the both-locales presence and locale-format tables below.

Covers: KAL-ERR-006
"""

from __future__ import annotations

import json
import pathlib

import pytest

import kaleta.i18n
from kaleta.exceptions import KaletaError, UnauthorizedError
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus, TenantRole
from kaleta.services.household_service import HouseholdService
from kaleta.services.tenant_service import TenantMembership
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every household key with a representative set of params — the placeholder
#: names must match what the raise sites pass.
_HOUSEHOLD: dict[str, dict[str, object]] = {
    "errors.household.member_no_key_to_seal": {},
    "errors.household.household_rekeying_already": {},
    "errors.household.key_not_current": {},
    "errors.household.not_a_member": {},
    "errors.household.invite_email_required": {},
    "errors.household.email_belongs_to_other_account": {},
    "errors.household.already_a_member": {},
    "errors.household.household_full": {"max_members": 10},
    "errors.household.only_pending_can_be_approved": {},
    "errors.household.member_no_passphrase": {},
    "errors.household.member_key_changed": {},
    "errors.household.only_pending_can_be_declined": {},
    "errors.household.hand_over_before_leaving": {},
    "errors.household.only_active_can_be_removed": {},
    "errors.household.already_the_owner": {},
    "errors.household.only_active_can_be_owner": {},
    "errors.household.reset_not_a_member": {},
    "errors.household.owner_key_cannot_reset": {},
    "errors.household.name_required": {},
    "errors.household.name_too_long": {"max_length": 100},
    "errors.household.account_being_set_up": {},
    "errors.household.member_no_account": {},
    "errors.household.household_gone": {},
    "errors.household.member_not_found": {},
    "errors.household.household_rekeying": {},
    "errors.household.membership_pending": {},
    "errors.household.only_owner": {},
    "errors.household.unlock_first": {},
    "errors.household.email_has_login": {},
    "errors.household.invitation_just_used": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestHouseholdKeysInterpolate:
    def test_both_locales_carry_every_household_key(self) -> None:
        for key in _HOUSEHOLD:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _HOUSEHOLD.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeHouseholdToastReadsInEachLanguage:
    """The representative household errors — literals from KAL-ERR-006."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.household.invite_email_required")
        assert text == "Podaj adres e-mail."

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.household.invite_email_required")
        assert text == "Enter an e-mail address."

    def test_polish_message_with_param(self) -> None:
        text = _resolve("pl", "errors.household.household_full").format(max_members=10)
        assert text == "Gospodarstwo może mieć najwyżej 10 członków, wliczając zaproszenia."


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


def _membership(status: TenantMemberStatus, role: TenantRole) -> TenantMembership:
    """An in-memory membership — enough for the status/role guards, no DB."""
    member = TenantMember(status=status, role=role)
    return TenantMembership(member=member, tenant=Tenant())


class TestMigratedHouseholdRaisesCarryWorkingKeys:
    """Drive the two guard raises reachable from an in-memory membership."""

    async def test_pending_member_op_carries_membership_pending_key(self) -> None:
        # A pending member listing the household hits ``_require_active`` first.
        service = HouseholdService(
            public=None,  # type: ignore[arg-type]  # the guard raises before any DB use
            me=_membership(TenantMemberStatus.PENDING, TenantRole.MEMBER),
        )
        with pytest.raises(UnauthorizedError) as pending:
            await service.members()
        _assert_localizes(pending.value, "errors.household.membership_pending")
        assert pending.value.message == "Your membership is waiting for the owner's approval."

    async def test_non_owner_invite_carries_only_owner_key(self) -> None:
        # An active non-owner inviting hits ``_require_owner`` first.
        service = HouseholdService(
            public=None,  # type: ignore[arg-type]  # the guard raises before any DB use
            me=_membership(TenantMemberStatus.ACTIVE, TenantRole.MEMBER),
        )
        with pytest.raises(UnauthorizedError) as not_owner:
            await service.invite("someone@example.com")
        _assert_localizes(not_owner.value, "errors.household.only_owner")
        assert not_owner.value.message == "Only the household's owner can do this."


class TestResolveToastTextForHousehold:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_a_migrated_household_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the key reproduces the English fallback exactly.
        exc = UnauthorizedError(
            "ignored fallback",
            message_key="errors.household.only_owner",
        )
        assert resolve_toast_text(exc) == "Only the household's owner can do this."
