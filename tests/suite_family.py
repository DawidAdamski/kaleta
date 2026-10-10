# SPDX-License-Identifier: AGPL-3.0-or-later
"""The family every test runs in: one registry, one tenant schema (ADR-38).

The suite's database is laid out as every instance is — a ``public`` registry
and one schema per family. The first session on a fresh database signs the
suite's administrator up and provisions their family through the real
``TenantService`` path; later sessions find both, migrate the schema to head
and empty its tables, keeping only the owner's ``users`` row (the registry's
member points at it).

Tests that build registries of their own (``tests.tenancy_helpers``) do so in
a companion database, so they never drop this family.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import create_engine, text

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.base import Base
from kaleta.db.tenant_context import TenantContext
from kaleta.db.tenant_schemas import quote_schema
from kaleta.schemas.identity import Identity
from kaleta.services.local_identity_service import LocalIdentityService, subject_of
from kaleta.services.setup_service import _sync_url, upgrade_public_to_head, upgrade_to_head
from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService

SUITE_EMAIL = "suite@example.com"
SUITE_PASSWORD = "suite-family-password"


@dataclass(frozen=True)
class SuiteFamily:
    context: TenantContext
    #: The administrator's ``local:<id>`` subject, which the registry's member row carries.
    subject: str


async def _provision(url: str) -> SuiteFamily:
    AsyncSessionFactory.configure(url)
    try:
        async with AsyncSessionFactory.public() as public:
            identities = LocalIdentityService(public)
            row = await identities.get_by_email(SUITE_EMAIL)
            if row is None:
                row = await identities.create(SUITE_EMAIL, SUITE_PASSWORD, admin=True)
            service = TenantService(
                public, provisioner=AlembicSchemaProvisioner(url, AsyncSessionFactory.public)
            )
            membership = await service.membership_for_sign_in(
                Identity(subject=subject_of(row.id), email=SUITE_EMAIL, email_verified=True)
            )
        return SuiteFamily(membership.context(), subject_of(row.id))
    finally:
        # The connections belong to this loop, which ends here; the proxy is
        # left configured for the tests, as it was on import.
        await AsyncSessionFactory.dispose()
        AsyncSessionFactory.configure(url, debug=settings.debug)


def _empty_family_tables(url: str, family: TenantContext) -> None:
    """Every row a test left committed goes; the owner's ``users`` row stays."""
    schema = quote_schema(family.schema)
    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "users"]
    engine = create_engine(_sync_url(url))
    try:
        with engine.begin() as conn:
            names = ", ".join(f'{schema}."{name}"' for name in tables)
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
            conn.execute(
                text(f"DELETE FROM {schema}.users WHERE id <> :owner"),
                {"owner": family.member_user_id},
            )
    finally:
        engine.dispose()


def bootstrap_suite_family(url: str) -> SuiteFamily:
    """The suite's family on ``url``: provisioned once, migrated and emptied every session."""
    upgrade_public_to_head(url)
    family = asyncio.run(_provision(url))
    # Idempotent: a current schema costs a version check.
    upgrade_to_head(url, schema=family.context.schema)
    _empty_family_tables(url, family.context)
    return family
