# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two families unlocked in one process never cross keys or rows.

The horizontal-scaling plan's top safety requirement, proven without a cluster.
Posture 1 puts several families on one pod (sticky sessions), so that pod's
process holds more than one family's unlocked data key at once. Each request
must resolve its tenant schema and data key strictly from *its own* context
(the ``ContextVar``s behind ``use_tenant`` / ``use_data_key``), never from
"whatever this process last unlocked". This test drives two families
concurrently on one event loop and asserts:

* each concurrent read returns only its own family's rows, every time, and
* reading one family's rows under the other family's key fails to decrypt
  rather than returning anything.

Covers: KAL-ENC-011
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from kaleta.auth.providers import RegistryAuthProvider
from kaleta.crypto import DataKey
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import EncryptionError
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.local_identity_service import LocalIdentityService
from tests.household_helpers import (
    PASSWORD,
    Member,
    add_payees,
    household_database,
    payee_names,
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
        # Distinct accounts, distinct data keys — the whole point.
        assert alpha.member.tenant_id != bravo.member.tenant_id
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
            assert await payee_names(family.member, family.key) == family.payees

    # gather wraps each coroutine in its own Task, which runs in its own copy of
    # the context: if tenant/key leaked across tasks, one of these would read
    # the other family's payees (or fail to decrypt) on some iteration.
    await asyncio.gather(_read_repeatedly(alpha), _read_repeatedly(bravo))


async def test_one_familys_key_cannot_read_the_others_rows(
    two_families: tuple[Family, Family],
) -> None:
    """Family A's key over family B's ciphertext rejects, never returns data.

    Covers: KAL-ENC-011
    """
    alpha, bravo = two_families

    # Sanity: each key reads its own family's rows.
    assert await payee_names(alpha.member, alpha.key) == alpha.payees
    assert await payee_names(bravo.member, bravo.key) == bravo.payees

    # Bravo's rows, but Alpha's key: the AES-GCM tag over Bravo's ciphertext
    # rejects Alpha's key. Fails closed — no plaintext, Alpha's or Bravo's.
    with pytest.raises(EncryptionError):
        await payee_names(bravo.member, alpha.key)
    with pytest.raises(EncryptionError):
        await payee_names(alpha.member, bravo.key)
