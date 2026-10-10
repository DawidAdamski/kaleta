# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tenant context: sessions follow it, and without it there is no session.

Covers: KAL-TEN-001, KAL-TEN-002, KAL-TEN-003, KAL-TEN-004
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from kaleta.auth.providers import RegistryAuthProvider, set_auth_provider
from kaleta.auth.revocation_cache import RevocationCache
from kaleta.auth.sign_in import SignInFlow
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import (
    TenantContext,
    TenantContextMissingError,
    current_tenant,
    install_tenant_resolver,
    use_tenant,
)
from kaleta.exceptions import UnauthorizedError
from kaleta.models.account import Account, AccountType
from kaleta.schemas.identity import Identity
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database


@pytest.fixture
async def hosted(tmp_path: Path) -> AsyncIterator[str]:
    async with multi_tenant_database() as url:
        yield url


async def _provision(url: str, n: int) -> TenantContext:
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=MetadataProvisioner(url))
        await service.provision(identity(n))
        membership = await service.get_member_by_subject(identity(n).subject)
    assert membership is not None
    return membership.context()


async def _account_names() -> list[str]:
    async with AsyncSessionFactory() as session:
        return list((await session.execute(select(Account.name))).scalars().all())


async def _add_account(name: str) -> Account:
    async with AsyncSessionFactory() as session:
        account = Account(name=name, type=AccountType.CHECKING, currency="PLN")
        session.add(account)
        await session.commit()
        await session.refresh(account)
        return account


# ── Sessions follow the context ───────────────────────────────────────────────


async def test_each_session_reads_and_writes_its_own_tenant_schema(hosted: str) -> None:
    """Covers: KAL-TEN-002"""
    a = await _provision(hosted, 1)
    b = await _provision(hosted, 2)
    assert a.schema != b.schema

    with use_tenant(a):
        await _add_account("Main Checking")
        await _add_account("Only in A")
    with use_tenant(b):
        await _add_account("Main Checking")

    with use_tenant(a):
        assert sorted(await _account_names()) == ["Main Checking", "Only in A"]
    with use_tenant(b):
        assert await _account_names() == ["Main Checking"]


async def test_the_schema_is_rewritten_into_the_statement_not_the_search_path(hosted: str) -> None:
    """Covers: KAL-TEN-002 — schema_translate_map on the engine the session is bound to."""
    a = await _provision(hosted, 1)
    with use_tenant(a):
        session = AsyncSessionFactory()
    try:
        bind = session.bind
        assert bind is not None
        # SQLAlchemy keeps an internal alias of the `None` key beside it.
        assert bind.get_execution_options()["schema_translate_map"][None] == a.schema
    finally:
        await session.close()


async def test_raw_sql_in_a_tenant_session_never_reaches_another_tenant(hosted: str) -> None:
    """Covers: KAL-TEN-002 — unqualified SQL is outside the translate map's reach.

    SQLite would look an unqualified name up in every attached database, so a
    tenant's connection attaches only that tenant; PostgreSQL finds no tenant
    table on the default search path and errors. Either way, never A's rows.
    """
    a = await _provision(hosted, 1)
    b = await _provision(hosted, 2)
    with use_tenant(a):
        await _add_account("Only in A")
    with use_tenant(b):
        await _add_account("Only in B")
        async with AsyncSessionFactory() as session:
            try:
                names = list((await session.execute(text("SELECT name FROM accounts"))).scalars())
            except DBAPIError:
                names = []
    assert "Only in A" not in names


# ── Fail closed ───────────────────────────────────────────────────────────────


async def test_no_tenant_context_means_no_session(hosted: str) -> None:
    """Covers: KAL-TEN-003"""
    await _provision(hosted, 1)
    assert current_tenant() is None
    with pytest.raises(TenantContextMissingError):
        AsyncSessionFactory()


async def test_a_resolver_that_finds_nothing_still_means_no_session(hosted: str) -> None:
    """Covers: KAL-TEN-003"""
    install_tenant_resolver(lambda: None)
    with pytest.raises(TenantContextMissingError):
        AsyncSessionFactory()


async def test_the_resolver_supplies_the_tenant_for_ui_events(hosted: str) -> None:
    """Covers: KAL-TEN-002 — websocket events pass no middleware; the resolver stands in."""
    a = await _provision(hosted, 1)
    with use_tenant(a):
        await _add_account("From the resolver")
    install_tenant_resolver(lambda: a)
    assert await _account_names() == ["From the resolver"]


async def test_the_public_session_cannot_see_tenant_rows(hosted: str) -> None:
    """Covers: KAL-TEN-003

    The registry database has no ``accounts`` outside the tenant schemas, so
    the query errors; were there ever an ``accounts`` table in ``public`` it
    would answer from that. Neither answer may contain a tenant's row.
    """
    a = await _provision(hosted, 1)
    with use_tenant(a):
        await _add_account("Private")
    async with AsyncSessionFactory.public() as session:
        try:
            names = list((await session.execute(select(Account.name))).scalars())
        except DBAPIError:
            names = []
    assert "Private" not in names


def test_a_context_refuses_a_schema_name_it_did_not_mint() -> None:
    """Covers: KAL-TEN-003"""
    for bad in ("public; DROP TABLE x", "t_ABC", "t_0123456789abc", "tenant", ""):
        with pytest.raises(ValueError, match="Not a Kaleta schema name"):
            TenantContext(tenant_id=1, schema=bad)


# ── Attribution ───────────────────────────────────────────────────────────────


async def test_new_rows_are_attributed_to_the_acting_member(hosted: str) -> None:
    a = await _provision(hosted, 1)
    assert a.member_user_id is not None
    with use_tenant(a):
        account = await _add_account("Who added me")
    assert account.user_id == a.member_user_id


async def test_an_explicit_user_id_is_left_alone(hosted: str) -> None:
    a = await _provision(hosted, 1)
    with use_tenant(a):
        async with AsyncSessionFactory() as session:
            account = Account(name="Explicit", type=AccountType.CHECKING, currency="PLN")
            account.user_id = None
            session.add(account)
            account.user_id = a.member_user_id
            await session.commit()
            assert account.user_id == a.member_user_id


# ── API tokens name their tenant ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("kt_7_" + "A" * 43, 7),
        ("kt_123456_abcDEF-_0123456789abcdef", 123456),
        ("kt_0_" + "A" * 43, None),
        ("kt_07_" + "A" * 43, None),
        ("kt_7_short", None),
        ("kt__" + "A" * 43, None),
        ("kt_7_" + "A" * 40 + "!!!", None),
        ("A" * 43, None),
        ("", None),
    ],
)
def test_tenant_id_from_token(raw: str, expected: int | None) -> None:
    """Covers: KAL-TEN-004"""
    assert ApiTokenService.tenant_id_from_token(raw) == expected


async def test_a_minted_token_carries_its_tenant(hosted: str) -> None:
    """Covers: KAL-TEN-004"""
    a = await _provision(hosted, 1)
    assert a.member_user_id is not None
    with use_tenant(a):
        async with AsyncSessionFactory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=a.member_user_id, label="cli"
            )
    assert raw.startswith(f"kt_{a.tenant_id}_")
    assert ApiTokenService.tenant_id_from_token(raw) == a.tenant_id


# ── Revocation cache ──────────────────────────────────────────────────────────


async def test_revocation_watermarks_are_kept_per_tenant(hosted: str) -> None:
    """User 1 of one household is not user 1 of another."""
    a = await _provision(hosted, 1)
    b = await _provision(hosted, 2)
    assert a.member_user_id == b.member_user_id  # each schema numbers from 1
    assert a.member_user_id is not None
    from kaleta.services.auth_service import AuthService

    with use_tenant(a):
        async with AsyncSessionFactory() as session:
            await AuthService(session).revoke_sessions(a.member_user_id)

    cache = RevocationCache()
    with use_tenant(a):
        assert await cache.valid_from(a.member_user_id) is not None
    with use_tenant(b):
        assert await cache.valid_from(b.member_user_id) is None


# ── Sign-in flow ──────────────────────────────────────────────────────────────


class _RecordingProvider(RegistryAuthProvider):
    name = "supabase"

    def __init__(self) -> None:
        self.signed_out: list[Identity] = []

    async def sign_out(self, identity: Identity) -> None:
        self.signed_out.append(identity)


async def test_first_sign_in_provisions_and_opens_the_session_for_that_tenant(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    provider = _RecordingProvider()
    set_auth_provider(provider)
    try:
        async with AsyncSessionFactory.public() as public:
            service = TenantService(public, provisioner=MetadataProvisioner(hosted))
            signed_in = await SignInFlow(service).complete(identity(1))
    finally:
        set_auth_provider(None)

    assert signed_in.tenant is not None
    assert signed_in.tenant.auth_subject == identity(1).subject
    assert signed_in.tenant.email == "member1@example.com"
    assert signed_in.username == "member1@example.com"
    assert signed_in.tenant.schema.startswith("t_")
    assert provider.signed_out == [identity(1)]


async def test_an_unverified_identity_cannot_sign_in(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=MetadataProvisioner(hosted))
        with pytest.raises(UnauthorizedError):
            await SignInFlow(service).complete(identity(1, verified=False))
