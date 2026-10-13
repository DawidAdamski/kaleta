# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two families unlocked in one process never cross keys or rows.

The horizontal-scaling plan's top safety requirement, proven without a cluster.
Posture 1 puts several families on one pod (sticky sessions), so that pod's
process holds more than one family's unlocked data key at once. A request must
resolve its tenant schema and data key strictly from *its own* context, never
from "whatever this process last unlocked".

These tests read exactly as a request does: only the per-task ``TenantContext``
is set (``use_tenant``), and its ``key_ring`` slot is filled from the process
``KeyRing`` keyed by *that* member — the same resolution the auth layer does.
No key is injected through the explicit-key ContextVar (``use_data_key``), so
the decrypting read genuinely exercises ``current_data_key()``'s resolution
from the context. That is what makes this a guard against the anti-pattern the
plan forbids: were ``current_data_key()`` to read a process-global
"last unlocked key" instead of the context, one of the two interleaved tasks
would get the wrong key and fail. (Verified: stubbing that resolution to a
module global turns the concurrent test red — see the plan's Slice 2 note.)

Covers: KAL-ENC-011
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from kaleta.auth.providers import RegistryAuthProvider
from kaleta.crypto import DataKey
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import EncryptionError
from kaleta.models.payee import Payee
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.local_identity_service import LocalIdentityService
from tests.household_helpers import (
    PASSWORD,
    Member,
    add_payees,
    household_database,
    set_up_passphrase,
    sign_in,
)

_ALPHA_PAYEES = ["Alpha Grocer", "Alpha Fuel"]
_BRAVO_PAYEES = ["Bravo Bakery"]


@dataclass
class Family:
    member: Member
    key: DataKey
    payees: list[str]


async def _read_payees_under_key(member: Member, key: DataKey | None) -> list[str]:
    """Read ``member``'s payees with ``key`` resolved the way a request resolves it.

    Only the tenant context is set; the data key rides on ``TenantContext.key_ring``
    (what the auth layer fills), not on the explicit-key ContextVar. So the
    decrypting read goes through ``current_data_key()``'s context resolution.
    """
    with use_tenant(member.context(key)):
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(Payee.name).order_by(Payee.id))
            return list(result.scalars().all())


async def _read_own_payees(member: Member) -> list[str]:
    """Read as a live request would: the key comes from the process ``KeyRing``."""
    return await _read_payees_under_key(member, member.unlocked_key())


async def _new_family(url: str, email: str, passphrase: str, payees: list[str]) -> Family:
    """A brand-new owner (hence a family of their own), unlocked, with ``payees``."""
    result = await RegistryAuthProvider().sign_up(email, PASSWORD)
    assert result.identity is not None
    member = await sign_in(url, email)
    key = await set_up_passphrase(member, passphrase)
    assert key is not None  # a new family's owner gets the account's data key
    await add_payees(member, key, *payees)
    return Family(member=member, key=key, payees=payees)


async def _open_registration() -> None:
    """Let a second owner sign up: the first sign-up closes registration."""
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_registration_mode(RegistrationMode.OPEN)


@pytest.fixture
async def two_families() -> AsyncIterator[tuple[Family, Family]]:
    async with household_database() as url:
        alpha = await _new_family(
            url, "alpha@example.com", "alpha family passphrase", _ALPHA_PAYEES
        )
        await _open_registration()
        bravo = await _new_family(
            url, "bravo@example.com", "bravo family passphrase", _BRAVO_PAYEES
        )
        # Distinct accounts, schemas and data keys — the whole point.
        assert alpha.member.tenant_id != bravo.member.tenant_id
        assert alpha.member.schema != bravo.member.schema
        assert alpha.key.dek != bravo.key.dek
        yield alpha, bravo


async def test_concurrent_reads_never_cross_families(
    two_families: tuple[Family, Family],
) -> None:
    """Two families read at the same time each see only their own payees.

    Covers: KAL-ENC-011
    """
    alpha, bravo = two_families

    async def _read_repeatedly(family: Family) -> None:
        for _ in range(25):
            await asyncio.sleep(0)  # yield so the two tasks actually interleave
            assert await _read_own_payees(family.member) == family.payees

    # gather wraps each coroutine in its own Task, which runs in its own copy of
    # the context, and the asyncpg await yields between them: if tenant or key
    # resolution leaked across tasks, one of these would read the other family's
    # payees (or fail to decrypt) on some iteration.
    await asyncio.gather(_read_repeatedly(alpha), _read_repeatedly(bravo))


async def test_one_familys_key_cannot_read_the_others_rows(
    two_families: tuple[Family, Family],
) -> None:
    """Family A's key over family B's ciphertext rejects, never returns data.

    Covers: KAL-ENC-011
    """
    alpha, bravo = two_families

    # Sanity: resolved from the process KeyRing, each family reads its own rows.
    assert await _read_own_payees(alpha.member) == alpha.payees
    assert await _read_own_payees(bravo.member) == bravo.payees

    # Bravo's rows, but Alpha's key in the context: the AES-GCM tag over Bravo's
    # ciphertext rejects Alpha's key. ``match`` pins the wrong-key (InvalidTag)
    # branch, not the unknown-format or version-mismatch ones. Fails closed —
    # no plaintext, Alpha's or Bravo's.
    with pytest.raises(EncryptionError, match="Could not decrypt"):
        await _read_payees_under_key(bravo.member, alpha.key)
    with pytest.raises(EncryptionError, match="Could not decrypt"):
        await _read_payees_under_key(alpha.member, bravo.key)
