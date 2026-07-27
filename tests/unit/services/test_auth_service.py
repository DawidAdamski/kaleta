# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for AuthService password hashing and login flows."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.user import User
from kaleta.services.auth_service import PLACEHOLDER_USERNAME, AuthService


@pytest.fixture
def auth(session: AsyncSession) -> AuthService:
    return AuthService(session)


class TestAuthServicePasswordHashing:
    def test_hash_password_returns_argon2_string(self, auth: AuthService) -> None:
        hashed = auth.hash_password("secret-pass")
        assert hashed.startswith("$argon2")

    def test_verify_password_accepts_correct_password(self, auth: AuthService) -> None:
        password = "my-secure-password"
        hashed = auth.hash_password(password)
        assert auth.verify_password(password, hashed) is True

    def test_verify_password_rejects_wrong_password(self, auth: AuthService) -> None:
        hashed = auth.hash_password("correct")
        assert auth.verify_password("wrong", hashed) is False

    def test_verify_password_rejects_invalid_hash(self, auth: AuthService) -> None:
        assert auth.verify_password("anything", "not-a-valid-hash") is False

    def test_same_password_produces_different_hashes(self, auth: AuthService) -> None:
        password = "repeatable"
        assert auth.hash_password(password) != auth.hash_password(password)


class TestAuthServiceAccountLifecycle:
    @pytest.mark.asyncio
    async def test_auth_state_no_user(self, auth: AuthService) -> None:
        assert await auth.auth_state() == "no_user"

    @pytest.mark.asyncio
    async def test_create_user_and_authenticate(self, auth: AuthService) -> None:
        await auth.create_user("alice", "password-one")
        assert await auth.auth_state() == "ready"
        user = await auth.authenticate("alice", "password-one")
        assert user is not None
        assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_authenticate_rejects_wrong_password(self, auth: AuthService) -> None:
        await auth.create_user("alice", "password-one")
        assert await auth.authenticate("alice", "wrong") is None

    @pytest.mark.asyncio
    async def test_authenticate_rejects_placeholder_user(self, auth: AuthService) -> None:
        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        assert await auth.auth_state() == "placeholder"
        assert await auth.authenticate(PLACEHOLDER_USERNAME, "not-used") is None

    @pytest.mark.asyncio
    async def test_secure_placeholder_updates_credentials(self, auth: AuthService) -> None:
        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        user = await auth.secure_placeholder("owner", "new-password-123")
        assert user.username == "owner"
        assert await auth.auth_state() == "ready"
        assert await auth.authenticate("owner", "new-password-123") is not None


class TestAuthServiceResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password_updates_hash(self, auth: AuthService) -> None:
        """Covers: KAL-AUTH-007"""
        await auth.create_user("alice", "old-password-1")
        user = await auth.reset_password("new-password-9")
        assert user.username == "alice"
        assert await auth.authenticate("alice", "new-password-9") is not None
        assert await auth.authenticate("alice", "old-password-1") is None

    @pytest.mark.asyncio
    async def test_reset_password_rejects_short_password(self, auth: AuthService) -> None:
        await auth.create_user("alice", "old-password-1")
        with pytest.raises(ValidationError, match="at least 8"):
            await auth.reset_password("short")

    @pytest.mark.asyncio
    async def test_reset_password_no_user(self, auth: AuthService) -> None:
        with pytest.raises(NotFoundError, match="first-run bootstrap"):
            await auth.reset_password("new-password-9")

    @pytest.mark.asyncio
    async def test_reset_password_multiple_users(self, auth: AuthService) -> None:
        await auth.create_user("alice", "old-password-1")
        auth.session.add(User(username="bob", password_hash=auth.hash_password("other-password")))
        await auth.session.commit()
        with pytest.raises(ConflictError, match="Multiple users"):
            await auth.reset_password("new-password-9")

    @pytest.mark.asyncio
    async def test_reset_password_refuses_placeholder(self, auth: AuthService) -> None:
        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        with pytest.raises(NotFoundError, match="No real user"):
            await auth.reset_password("new-password-9")


class TestAuthServiceApiBootstrap:
    @pytest.mark.asyncio
    async def test_ensure_creates_api_user_when_empty(self, auth: AuthService) -> None:
        from kaleta.services.auth_service import API_BOOTSTRAP_USERNAME

        user = await auth.ensure_api_bootstrap_user()
        assert user.username == API_BOOTSTRAP_USERNAME
        assert await auth.auth_state() == "ready"

    @pytest.mark.asyncio
    async def test_ensure_converts_placeholder(self, auth: AuthService) -> None:
        from kaleta.services.auth_service import API_BOOTSTRAP_USERNAME

        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        user = await auth.ensure_api_bootstrap_user()
        assert user.username == API_BOOTSTRAP_USERNAME

    @pytest.mark.asyncio
    async def test_ensure_keeps_existing_user(self, auth: AuthService) -> None:
        await auth.create_user("owner", "password-123")
        user = await auth.ensure_api_bootstrap_user()
        assert user.username == "owner"
