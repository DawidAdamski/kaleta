# SPDX-License-Identifier: AGPL-3.0-or-later
"""A family of its own for a script a test runs in a subprocess.

A script (``scripts/seed.py``, ``scripts/reset_demo.py``) works in a family of
an instance and under the data key a member's passphrase opens
(``scripts/data_passphrase.py``). :func:`script_family` builds that instance
in a fresh database beside the suite's: a registry, one family migrated by
Alembic, and — while encryption is on — an owner whose sealed key is the
suite's own ``TEST_DATA_KEY``, so what the script writes, the test reads back
under the key every test runs under.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import kaleta.models  # noqa: F401 — register every table
from kaleta.config import settings
from kaleta.crypto import KdfParams, create_key_material
from kaleta.db.tenant_context import TenantContext, current_tenant
from kaleta.models.tenant import Tenant, TenantMember
from kaleta.schemas.identity import Identity
from kaleta.services.local_identity_service import LocalIdentityService, subject_of
from kaleta.services.setup_service import upgrade_public_to_head
from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService
from tests.conftest import TEST_DATA_KEY
from tests.suite_database import fresh_database_url

TEST_PASSPHRASE = "test-data-passphrase"
OWNER_EMAIL = "script@example.com"
OWNER_PASSWORD = "script-owner-password"
#: Cheap on purpose: these keys guard throwaway databases, and each script run derives once.
_FAST_KDF = KdfParams(time_cost=1, memory_kib=8 * 1024, parallelism=1)


@dataclass(frozen=True)
class ScriptFamily:
    url: str
    family: TenantContext
    #: Extra environment for the script: the database, and the passphrase.
    env: dict[str, str] = field(default_factory=dict)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session on the family's schema; the engine is disposed on the way out."""
        engine = create_async_engine(self.url, poolclass=NullPool)
        translated = engine.execution_options(schema_translate_map={None: self.family.schema})
        session = async_sessionmaker(translated, expire_on_commit=False)()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()


def script_family(name: str) -> ScriptFamily:
    """A fresh ``<suite database>_<name>`` holding one family; synchronous."""
    url = fresh_database_url(name)
    upgrade_public_to_head(url)
    family = asyncio.run(_provision(url))
    env = {"KALETA_DB_URL": url}
    if settings.encryption_enabled:
        env["KALETA_DATA_PASSPHRASE"] = TEST_PASSPHRASE
    return ScriptFamily(url=url, family=family, env=env)


async def _provision(url: str) -> TenantContext:
    engine = create_async_engine(url, poolclass=NullPool)
    public = async_sessionmaker(engine, expire_on_commit=False)

    def _tenant_session() -> AsyncSession:
        ctx = current_tenant()
        if ctx is None:
            msg = "no family to open a session in"
            raise RuntimeError(msg)
        translated = engine.execution_options(schema_translate_map={None: ctx.schema})
        return async_sessionmaker(translated, expire_on_commit=False)()

    try:
        async with public() as session:
            row = await LocalIdentityService(session).create(
                OWNER_EMAIL, OWNER_PASSWORD, admin=True
            )
            service = TenantService(
                session,
                provisioner=AlembicSchemaProvisioner(url, public),
                tenant_session=_tenant_session,
            )
            membership = await service.membership_for_sign_in(
                Identity(subject=subject_of(row.id), email=OWNER_EMAIL, email_verified=True)
            )
            if settings.encryption_enabled:
                await _hold_the_test_key(session, membership.member, membership.tenant)
        return membership.context()
    finally:
        await engine.dispose()


async def _hold_the_test_key(session: AsyncSession, member: TenantMember, tenant: Tenant) -> None:
    material, _private_key = create_key_material(
        TEST_PASSPHRASE, dek=TEST_DATA_KEY.dek, recovery_code=None, params=_FAST_KDF
    )
    member.public_key = material.public_key
    member.private_key_wrapped = material.private_key_wrapped
    member.private_key_salt = material.private_key_salt
    member.kdf_params = material.kdf_params
    member.dek_sealed = material.dek_sealed
    tenant.key_version = TEST_DATA_KEY.version
    await session.commit()
