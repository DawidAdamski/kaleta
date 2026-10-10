# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KeyService`` over the suite family's member rows — the passphrase flows end to end.

Covers: KAL-ENC-002, KAL-ENC-003, KAL-ENC-004, KAL-ENC-005, KAL-ENC-006, KAL-ENC-007
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.crypto import KdfParams, key_ring
from kaleta.db.tenant_context import set_tenant
from kaleta.db.types import TEXT_FORMAT_AES_GCM, install_data_key_resolver, use_data_key
from kaleta.exceptions import ConflictError, TenantLockedError, ValidationError
from kaleta.models.payee import Payee
from kaleta.models.tenant import TenantMember, TenantMemberStatus, TenantRole
from kaleta.models.user import User
from kaleta.services.key_service import KeyService, TenantKeyStore, open_family_data_key
from tests.conftest import SUITE_FAMILY, family_table

PASSPHRASE = "correct horse battery"
OTHER = "another long passphrase"
FAST = KdfParams(time_cost=1, memory_kib=8 * 1024, parallelism=1)
BROWSER = "browser-1"


@pytest.fixture(autouse=True)
def _encrypted_and_locked(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Encryption on and no key anywhere: only what the service opens is there."""
    monkeypatch.setattr(settings, "encryption", "passphrase")
    install_data_key_resolver(None)
    # The family's context, without the key the suite's own carries.
    set_tenant(replace(SUITE_FAMILY, key_ring=None))
    key_ring.clear()
    yield
    key_ring.clear()


OWNER = SUITE_FAMILY.member_user_id or 0


def _service(session: AsyncSession, user_id: int = OWNER) -> KeyService:
    # The test's session reaches `public` too: registry models name it.
    return KeyService(
        TenantKeyStore(session, SUITE_FAMILY.tenant_id, user_id), session, params=FAST
    )


async def _second_member(session: AsyncSession) -> int:
    """Another member of the suite family (rolled back with the test)."""
    user = User(username="second@example.com", email="second@example.com")
    session.add(user)
    await session.flush()
    session.add(
        TenantMember(
            tenant_id=SUITE_FAMILY.tenant_id,
            auth_subject="local:second",
            email="second@example.com",
            role=TenantRole.MEMBER,
            status=TenantMemberStatus.ACTIVE,
            user_id=user.id,
        )
    )
    await session.flush()
    return user.id


async def test_setup_creates_the_key_and_unlocks_the_browser(session: AsyncSession) -> None:
    """Covers: KAL-ENC-002"""
    service = _service(session)
    assert await service.status() == "setup_required"

    setup = await service.setup(BROWSER, PASSPHRASE)

    assert len(setup.recovery_code.replace("-", "")) == 26
    assert await service.status() == "ready"
    assert await service.has_recovery()
    entry = key_ring.get(BROWSER)
    assert entry is not None
    assert entry.member_ref == f"tenant:{SUITE_FAMILY.tenant_id}:user:{OWNER}"
    assert entry.data_key == setup.data_key


async def test_setup_twice_is_refused(session: AsyncSession) -> None:
    service = _service(session)
    await service.setup(BROWSER, PASSPHRASE)
    with pytest.raises(ConflictError):
        await service.setup(BROWSER, OTHER)


async def test_short_passphrase_and_login_password_are_refused(session: AsyncSession) -> None:
    service = _service(session)
    with pytest.raises(ValidationError):
        await service.setup(BROWSER, "too short")
    with pytest.raises(ValidationError):
        await service.setup(BROWSER, PASSPHRASE, login_password_matches=True)
    assert await service.status() == "setup_required"


async def test_setup_encrypts_the_data_already_there(session: AsyncSession) -> None:
    """An install switched on after the fact: plaintext rows become ciphertext."""
    settings.encryption = "off"
    session.add(Payee(name="Biedronka"))
    await session.commit()
    settings.encryption = "passphrase"

    setup = await _service(session).setup(BROWSER, PASSPHRASE)

    raw = (await session.execute(text(f"SELECT name FROM {family_table('payees')}"))).scalar_one()
    assert bytes(raw)[0] == TEXT_FORMAT_AES_GCM
    assert b"Biedronka" not in bytes(raw)
    session.expire_all()
    with use_data_key(setup.data_key):
        found = await session.execute(select(Payee).where(Payee.name_bidx.is_not(None)))
        payee = found.scalar_one()
        assert payee.name == "Biedronka"


async def test_unlock_with_the_passphrase(session: AsyncSession) -> None:
    """Covers: KAL-ENC-003"""
    service = _service(session)
    setup = await service.setup(None, PASSPHRASE)
    assert key_ring.get(BROWSER) is None

    unlocked = await service.unlock(BROWSER, PASSPHRASE)

    assert unlocked.data_key == setup.data_key
    assert key_ring.get(BROWSER) is not None


async def test_wrong_passphrase_does_not_unlock(session: AsyncSession) -> None:
    """Covers: KAL-ENC-004"""
    service = _service(session)
    await service.setup(None, PASSPHRASE)

    with pytest.raises(ValidationError):
        await service.unlock(BROWSER, OTHER)
    assert key_ring.get(BROWSER) is None


async def test_recovery_code_sets_a_new_passphrase_and_is_replaced(session: AsyncSession) -> None:
    """Covers: KAL-ENC-005"""
    service = _service(session)
    setup = await service.setup(None, PASSPHRASE)

    fresh = await service.recover(BROWSER, setup.recovery_code, OTHER)

    assert key_ring.get(BROWSER) is not None
    assert fresh != setup.recovery_code
    with pytest.raises(ValidationError):
        await service.unlock("browser-2", PASSPHRASE)
    assert (await service.unlock("browser-2", OTHER)).data_key == setup.data_key
    with pytest.raises(ValidationError):
        await service.recover("browser-3", setup.recovery_code, PASSPHRASE)
    await service.recover("browser-3", fresh, PASSPHRASE)


async def test_wrong_recovery_code_is_refused(session: AsyncSession) -> None:
    service = _service(session)
    await service.setup(None, PASSPHRASE)
    with pytest.raises(ValidationError):
        await service.recover(BROWSER, "0000-0000-0000-0000-0000-000000", OTHER)
    assert key_ring.get(BROWSER) is None


async def test_change_passphrase_keeps_the_recovery_code(session: AsyncSession) -> None:
    """Covers: KAL-ENC-006"""
    service = _service(session)
    setup = await service.setup(None, PASSPHRASE)

    with pytest.raises(ValidationError):
        await service.change_passphrase(OTHER, "yet another passphrase")
    await service.change_passphrase(PASSPHRASE, OTHER)

    with pytest.raises(ValidationError):
        await service.unlock(BROWSER, PASSPHRASE)
    assert (await service.unlock(BROWSER, OTHER)).data_key == setup.data_key
    await service.recover("browser-2", setup.recovery_code, "the third passphrase")


async def test_regenerating_the_recovery_code_retires_the_old_one(session: AsyncSession) -> None:
    service = _service(session)
    setup = await service.setup(None, PASSPHRASE)

    fresh = await service.regenerate_recovery_code(PASSPHRASE)

    with pytest.raises(ValidationError):
        await service.recover(BROWSER, setup.recovery_code, OTHER)
    await service.recover(BROWSER, fresh, OTHER)


async def test_lock_forgets_the_key(session: AsyncSession) -> None:
    """Covers: KAL-ENC-007"""
    service = _service(session)
    await service.setup(BROWSER, PASSPHRASE)

    KeyService.lock(BROWSER)

    assert key_ring.get(BROWSER) is None
    session.add(Payee(name="Lidl"))
    with pytest.raises(TenantLockedError):
        await session.flush()


async def test_a_second_member_waits_for_the_key(session: AsyncSession) -> None:
    await _service(session).setup(None, PASSPHRASE)
    second = _service(session, user_id=await _second_member(session))

    await second.setup(None, OTHER)

    assert await second.status() == "awaiting_key"
    with pytest.raises(ConflictError):
        await second.unlock(BROWSER, OTHER)


async def test_scripts_open_the_key_with_any_holders_passphrase(session: AsyncSession) -> None:
    setup = await _service(session).setup(None, PASSPHRASE)

    tenant_id = SUITE_FAMILY.tenant_id
    assert await open_family_data_key(session, session, tenant_id, PASSPHRASE) == setup.data_key
    with pytest.raises(ValidationError):
        await open_family_data_key(session, session, tenant_id, OTHER)
